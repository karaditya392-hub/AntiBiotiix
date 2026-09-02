"""
FastAPI Main Application for S11 Explainable Antimicrobial Stewardship & Safety Assistant
"""
import os
import re
import threading
import time
import uuid
import json
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import (
    FastAPI, Depends, File, Form, HTTPException, Query, Request, UploadFile, status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import (
    SYSTEM_VERSION, ENGINE_BUILD, MODEL_NAME, PROMPT_TEMPLATE_ID,
    PROMPT_TEMPLATE_HASH, GUIDELINE_PRECEDENCE_HIERARCHY,
    NOTIFICATION_SCHEDULER_INTERVAL_SECONDS, notification_scheduler_enabled,
    AUTHORIZED_OVERRIDE_ROLES, ALERT_FATIGUE_OVERRIDE_RATE_THRESHOLD
)
from backend.models import allergies as allergy_store
from backend.models.database import (
    get_db, init_db, SessionLocal, IST, now_ist, PatientDB, PrescriptionDB, PrescriptionItemDB,
    SafetyWarningDB, ClinicianOverrideDB, ClinicalRuleDB, RuleAuthorshipLogDB,
    GuidelineDocumentDB, AMRSurveillanceDB, AlertMetricsDB, AuditLogDB,
    DoctorDB, VisitDB, SymptomDB, DiagnosisDB, PatientRAGDocumentDB, AppointmentDB,
    NotificationDB, FeedbackResponseDB, FeedbackAcknowledgementDB
)
from backend.models.schemas import (
    PatientCreate, PatientResponse, PatientContactUpdate, PrescriptionCreate, PrescriptionItem,
    ExtractedPrescription, SafetyWarning, PrescriptionAnalysisResponse,
    OverrideRequest, OverrideResponse, ClinicianRole, SeverityLevel, RuleCategory,
    PatientRegistration, MedicationUpdate, AllergyReportRequest,
    VisitCreate, SymptomItem, PatientAskQuery, AppointmentCreate
)
from backend.rag.patient_rag import index_visit_for_rag, ask_patient_history
from backend.guidelines.knowledge_base import knowledge_base
from backend.guidelines import governance as rule_governance
from backend.guidelines.cross_source import compare_sources
from backend.rules.engine import rule_engine
from backend.rules.priority import compute_stewardship_priority
from backend.extraction.parser import clinical_parser
from backend.llm.explainer import clinical_explainer
from fastapi.security import OAuth2PasswordRequestForm
from backend.auth.security import (
    authorizer, get_current_clinician, create_session_token, create_patient_token,
    get_current_principal, require_clinician, require_patient_scope,
    verify_doctor_credentials, PATIENT_MANAGEMENT_ROLES,
)
from backend.audit.logger import audit_logger
from backend.seed_data import list_scenario_presets
from backend.notifications import (
    scan_and_trigger_same_day_notifications,
    scan_and_trigger_advance_notifications,
    run_all_scans,
    list_in_app_notifications,
    channel_status,
    format_ist_datetime,
    get_ist_bounds_for_date,
)


# Observable state for the appointment notification scheduler. Reported on
# /api/notifications/status so a silent scheduler is visible rather than assumed.
_NOTIFICATION_SCHEDULER_STATE: Dict[str, Any] = {
    "last_run_ist": None,
    "last_error": None,
    "runs": 0,
}


# Lifespan event handler for clean startup / database initialization
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables & seed initial teaching roster if missing
    init_db()
    db = SessionLocal()
    try:
        from backend.seed_data import seed_database
        seed_database(reset_patients=False)
    except Exception as e:
        print(f"Database initialization note: {e}")
    finally:
        db.close()

    # Warm the retrieval stack in a background thread. The embedding model takes
    # several seconds to load on first use; without this the first "Ask the
    # Evidence" query pays that cost. Failure here must never block startup or
    # affect rule evaluation, which does not depend on retrieval.
    def _warm_retrieval() -> None:
        try:
            from backend.rag.retrieve import retrieve
            retrieve("antimicrobial stewardship", k=1)
        except Exception:
            pass

    threading.Thread(target=_warm_retrieval, name="rag-warmup", daemon=True).start()

    # Appointment reminders, on a timer.
    #
    # There was no scheduler at all: the same-day scan ran only from a manual
    # endpoint, or inline at booking when the appointment happened to be for that
    # same day. An appointment booked for next Tuesday was therefore never
    # announced to anyone unless a human remembered to call the endpoint on
    # Tuesday. The loop below closes that gap for both the advance reminder and
    # the same-day alert.
    #
    # Idempotency comes from the advance_notice_sent / same_day_alert_sent flags,
    # so running every 15 minutes re-sends nothing.
    def _notification_scheduler() -> None:
        while True:
            time.sleep(NOTIFICATION_SCHEDULER_INTERVAL_SECONDS)
            if not notification_scheduler_enabled():
                continue
            session = SessionLocal()
            try:
                run_all_scans(session)
                _NOTIFICATION_SCHEDULER_STATE["last_run_ist"] = now_ist().isoformat()
                _NOTIFICATION_SCHEDULER_STATE["last_error"] = None
                _NOTIFICATION_SCHEDULER_STATE["runs"] += 1
            except Exception as exc:  # noqa: BLE001 - recorded, never fatal
                # A failing reminder loop must not take the clinical API down, but
                # it must not fail silently either: the error is surfaced on
                # /api/notifications/status.
                _NOTIFICATION_SCHEDULER_STATE["last_error"] = f"{type(exc).__name__}: {exc}"
            finally:
                session.close()

    if notification_scheduler_enabled():
        threading.Thread(
            target=_notification_scheduler, name="appointment-notifications", daemon=True
        ).start()

    yield


app = FastAPI(
    title="Explainable Antimicrobial Stewardship and Prescription Safety Assistant (S11)",
    version=SYSTEM_VERSION,
    description="Clinical decision-support tool for prescription safety, beta-lactam allergy cross-reactivity, renal/hepatic dosing, and antimicrobial guidelines.",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)



def _ingested_editions() -> List[str]:
    """
    Report the guideline editions this system actually holds.

    Read from the ingested corpus rather than hardcoded: stale version strings in
    API responses were how the catalog came to claim an ICMR edition that was
    never present (Spec §22).
    """
    try:
        from backend.rag.store import vector_store
        out = [
            f"{d.get('title')} - {d.get('version')} ({d.get('issuing_org')})"
            for d in vector_store.docs.values()
        ]
        return out or ["No guideline documents ingested"]
    except Exception:
        return ["Guideline corpus unavailable"]


def _corpus_summary() -> Dict[str, Any]:
    """
    What the corpus holds, in a shape a caller can act on.

    The flat edition list above is still returned for continuity, but at 94
    documents it is a wall of prose that hides the facts that actually change how a
    passage should be read: which documents carry national antimicrobial authority,
    which are held for reference without being guidelines at all, and -- since the
    ICMR national corpus was ingested -- what each document is authoritative ABOUT.

    That last one is now the largest single fact about this corpus. Only three of
    its documents are antimicrobial sources; the rest are condition-specific clinical
    guidance, research-ethics governance, laboratory and programme policy, and two
    research-activity reports. A caller that reads only the document count will
    badly overestimate what this system can answer about antimicrobial choice, so
    the count is reported next to the breakdown rather than on its own.
    """
    try:
        from backend.rag.store import (
            CLINICAL_DOMAINS,
            DOMAIN_ANTIMICROBIAL,
            NOT_A_CLINICAL_GUIDELINE_RANK,
            vector_store,
        )
        from backend.config import NATIONAL_ANTIMICROBIAL_AUTHORITY_DOCUMENT_IDS

        docs = vector_store.docs
        by_rank: Dict[str, int] = {}
        by_provenance: Dict[str, int] = {}
        by_domain: Dict[str, int] = {}
        not_guidelines: List[str] = []
        antimicrobial_ids: List[str] = []
        clinical_count = 0
        for doc_id, d in docs.items():
            rank = d.get("precedence_rank")
            by_rank[f"rank_{rank}"] = by_rank.get(f"rank_{rank}", 0) + 1
            basis = d.get("provenance_basis", "HASH_VERIFIED_PDF")
            by_provenance[basis] = by_provenance.get(basis, 0) + 1
            domain = d.get("clinical_domain", DOMAIN_ANTIMICROBIAL)
            by_domain[domain] = by_domain.get(domain, 0) + 1
            if rank == NOT_A_CLINICAL_GUIDELINE_RANK:
                not_guidelines.append(doc_id)
            if domain in CLINICAL_DOMAINS:
                clinical_count += 1
            if domain == DOMAIN_ANTIMICROBIAL and rank != NOT_A_CLINICAL_GUIDELINE_RANK:
                antimicrobial_ids.append(doc_id)
        return {
            "documents": len(docs),
            "chunks": len(vector_store.chunks),
            "documents_by_precedence_rank": dict(sorted(by_rank.items())),
            "documents_by_provenance_basis": by_provenance,
            "documents_by_clinical_domain": dict(sorted(by_domain.items())),
            "clinical_documents": clinical_count,
            "documents_carrying_antimicrobial_authority": sorted(antimicrobial_ids),
            "national_antimicrobial_authorities": [
                doc_id for doc_id in NATIONAL_ANTIMICROBIAL_AUTHORITY_DOCUMENT_IDS
                if doc_id in docs
            ],
            "held_for_reference_not_clinical_guidelines": sorted(not_guidelines),
            "corpus_scope_note": (
                f"{len(docs)} documents are held, of which {len(antimicrobial_ids)} carry "
                f"antimicrobial authority and {clinical_count} are clinical documents of "
                f"any kind. The remainder are research ethics, laboratory and biosafety, "
                f"programme policy and research activity reports: they are retrievable and "
                f"are never evidence for a clinical decision. Document count alone is not a "
                f"measure of what this system can answer about antimicrobial choice."
            ),
            "retrieval": vector_store.backend_description(),
        }
    except Exception as exc:  # pragma: no cover - never fail a health check on this
        return {"available": False, "detail": f"{type(exc).__name__}"}


# ---------------------------------------------------------------------------
# System & Health Endpoints (Section 22, 28)
# ---------------------------------------------------------------------------

@app.get("/api/system/health")
def get_system_health():
    return {
        "status": "HEALTHY",
        "service": "S11-Prescription-Safety-Engine",
        "version": SYSTEM_VERSION,
        "clinical_role": "CLINICAL_DECISION_SUPPORT_ONLY",
        "guideline_editions_held": _ingested_editions(),
        "guideline_corpus": _corpus_summary(),
        "timestamp": now_ist().isoformat()
    }


@app.get("/api/system/model-version")
def get_model_and_template_version():
    return {
        "system_version": SYSTEM_VERSION,
        "engine_build": ENGINE_BUILD,
        "explainer_component": "Deterministic Template Explainer with Injection-Hardened Input Handling",
        "model_identifier": MODEL_NAME,
        "prompt_template_id": PROMPT_TEMPLATE_ID,
        "prompt_template_hash": PROMPT_TEMPLATE_HASH,
        "stewardship_priority_method": "Deterministic Clinical Severity Rollup (Pure Function)",
        "guideline_sources": _ingested_editions(),
        "guideline_corpus": _corpus_summary(),
        "guideline_sources_note": (
            "Derived from the documents actually ingested into this system, not a "
            "hardcoded list. Renal calculations use the CKD-EPI 2021 non-race "
            "equation, which is an implemented formula rather than an ingested document."
        )
    }


# ---------------------------------------------------------------------------
# OAuth 2.0 & Clinician Authentication Endpoints (Section 28)
# ---------------------------------------------------------------------------

@app.post("/api/auth/token")
@app.post("/oauth/token")
async def oauth_token_endpoint(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    OAuth2 standard Password Grant token endpoint.
    Verifies doctor credentials (doctor_id and password) and issues Bearer access token.
    Supports both OAuth2 Form-Data and JSON request bodies.
    """
    username = None
    password = None

    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
    else:
        try:
            payload = await request.json()
            username = payload.get("username") or payload.get("doctor_id")
            password = payload.get("password")
        except Exception:
            pass

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth token request requires username (Doctor ID) and password."
        )

    doc_info = verify_doctor_credentials(username, password, db)
    if not doc_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Doctor ID or password. Please verify your login credentials."
        )

    access_token = create_session_token(
        clinician_id=doc_info["doctor_id"],
        clinician_role=doc_info["role"],
        display_name=doc_info.get("display_name")
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 86400,
        "clinician_id": doc_info["doctor_id"],
        "display_name": doc_info.get("display_name", doc_info["doctor_id"]),
        "clinician_role": doc_info["role"],
        "authorized_override": doc_info["role"] in AUTHORIZED_OVERRIDE_ROLES
    }


@app.post("/api/auth/login")
def clinician_login(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Clinician login endpoint supporting credential verification and legacy test compatibility.
    """
    username = payload.get("username") or payload.get("doctor_id") or "clinician_demo"
    password = payload.get("password")
    role_override = payload.get("role")

    if password:
        doc_info = verify_doctor_credentials(username, password, db)
        if not doc_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Doctor ID or password."
            )
        clinician_id = doc_info["doctor_id"]
        role = doc_info["role"]
        display_name = doc_info.get("display_name")
    else:
        # Legacy/Test fallback where password isn't passed
        clinician_id = username.upper()
        role = (role_override or "ATTENDING_PHYSICIAN").upper()
        display_name = clinician_id

    access_token = create_session_token(clinician_id, role, display_name)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "clinician_id": clinician_id,
        "display_name": display_name,
        "clinician_role": role,
        "authorized_override": role in AUTHORIZED_OVERRIDE_ROLES
    }


@app.get("/api/auth/me")
def get_current_user_profile(current_clinician: Dict[str, str] = Depends(get_current_clinician)):
    """
    Return currently authenticated doctor session profile.
    """
    role = current_clinician.get("clinician_role", "")
    return {
        "authenticated": True,
        "clinician_id": current_clinician.get("clinician_id"),
        "clinician_role": role,
        "display_name": current_clinician.get("display_name") or current_clinician.get("clinician_id"),
        "authorized_override": role in AUTHORIZED_OVERRIDE_ROLES
    }


# ---------------------------------------------------------------------------
# Patients & Longitudinal Record Endpoints (Sections 3, 24, 25)
# ---------------------------------------------------------------------------

@app.get("/api/patients")
def list_patients(q: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(PatientDB)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.filter(
            (PatientDB.patient_id.ilike(term)) |
            (PatientDB.display_name.ilike(term)) |
            (PatientDB.clinical_notes.ilike(term))
        )
    patients = query.all()
    results = []
    for p in patients:
        # Get latest visit
        latest_v = (
            db.query(VisitDB)
            .filter(VisitDB.patient_id == p.patient_id)
            .order_by(VisitDB.visit_date.desc())
            .first()
        )
        last_visit_date = latest_v.visit_date.strftime("%d %B %Y") if (latest_v and latest_v.visit_date) else None
        last_diagnosis = latest_v.diagnosis if latest_v else None

        results.append({
            "id": p.id,
            "patient_id": p.patient_id,
            "display_name": p.display_name or f"Patient {p.patient_id}",
            "age": p.age,
            "age_category": p.age_category,
            "sex": p.sex,
            "weight_kg": p.weight_kg,
            "allergies": allergy_store.substances(p.allergies_json),
            "allergy_records": allergy_store.normalise(p.allergies_json),
            "unverified_allergy_count": allergy_store.unverified_count(p.allergies_json),
            "allergy_status_known": p.allergy_status_known,
            "medical_history": json.loads(p.medical_history_json) if p.medical_history_json else [],
            "egfr_ml_min": p.egfr_ml_min,
            "serum_creatinine_mg_dl": p.serum_creatinine_mg_dl,
            "renal_status_known": p.renal_status_known,
            "child_pugh_class": p.child_pugh_class,
            "hepatic_status_known": p.hepatic_status_known,
            "pregnancy_status": p.pregnancy_status,
            "lactation_status": p.lactation_status,
            "active_medications": json.loads(p.active_medications_json) if p.active_medications_json else [],
            "clinical_notes": p.clinical_notes,
            "last_visit": last_visit_date,
            "last_diagnosis": last_diagnosis
        })
    return results


@app.get("/api/scenario-presets")
def get_scenario_presets(db: Session = Depends(get_db)):
    """
    Quick-scenario chips for the console.
    """
    return list_scenario_presets(db)


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    p = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    latest_v = (
        db.query(VisitDB)
        .filter(VisitDB.patient_id == p.patient_id)
        .order_by(VisitDB.visit_date.desc())
        .first()
    )
    last_visit_date = latest_v.visit_date.strftime("%d %B %Y") if (latest_v and latest_v.visit_date) else None

    return {
        "id": p.id,
        "patient_id": p.patient_id,
        "display_name": p.display_name or f"Patient {p.patient_id}",
        "age": p.age,
        "age_category": p.age_category,
        "sex": p.sex,
        "weight_kg": p.weight_kg,
        "allergies": allergy_store.substances(p.allergies_json),
        "allergy_records": allergy_store.normalise(p.allergies_json),
        "unverified_allergy_count": allergy_store.unverified_count(p.allergies_json),
        "allergy_status_known": p.allergy_status_known,
        "medical_history": json.loads(p.medical_history_json) if p.medical_history_json else [],
        "egfr_ml_min": p.egfr_ml_min,
        "serum_creatinine_mg_dl": p.serum_creatinine_mg_dl,
        "renal_status_known": p.renal_status_known,
        "child_pugh_class": p.child_pugh_class,
        "hepatic_status_known": p.hepatic_status_known,
        "pregnancy_status": p.pregnancy_status,
        "lactation_status": p.lactation_status,
        "active_medications": json.loads(p.active_medications_json) if p.active_medications_json else [],
        "clinical_notes": p.clinical_notes,
        "last_visit": last_visit_date
    }


@app.get("/api/patients/{patient_id}/history")
def get_patient_history(patient_id: str, db: Session = Depends(get_db)):
    """Return the selected patient's longitudinal clinical review history."""
    patient = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    v_records = (
        db.query(VisitDB)
        .filter(VisitDB.patient_id == patient_id)
        .order_by(VisitDB.visit_date.desc())
        .all()
    )

    visits = []
    for v in v_records:
        # Fetch prescription for this visit if exists
        p_rec = None
        if v.prescription_id:
            p_rec = db.query(PrescriptionDB).filter(PrescriptionDB.prescription_id == v.prescription_id).first()

        items = []
        warnings = []
        if p_rec:
            items = db.query(PrescriptionItemDB).filter(PrescriptionItemDB.prescription_id == p_rec.prescription_id).all()
            warnings = db.query(SafetyWarningDB).filter(SafetyWarningDB.prescription_id == p_rec.prescription_id).all()

        overrides = []
        for warning in warnings:
            override = db.query(ClinicianOverrideDB).filter(ClinicianOverrideDB.warning_id == warning.warning_id).first()
            if override:
                overrides.append({
                    "warning_id": warning.warning_id,
                    "rule_id": warning.rule_id,
                    "reason": override.override_reason,
                    "clinician_id": override.clinician_id,
                    "clinician_role": override.clinician_role,
                    "timestamp": override.timestamp,
                })

        symptoms_list = [{
            "name": s.name,
            "severity": s.severity,
            "duration": s.duration,
            "onset": s.onset,
            "notes": s.notes
        } for s in v.symptoms]

        v_dt = v.visit_date if isinstance(v.visit_date, datetime) else None
        day_of_week = v_dt.strftime("%A") if v_dt else ""
        time_str = v_dt.strftime("%I:%M %p") if v_dt else ""
        date_str = v_dt.strftime("%d %B %Y") if v_dt else ""
        fmt_date = f"{day_of_week}, {date_str} at {time_str}" if v_dt else str(v.visit_date)

        visits.append({
            "visit_id": v.visit_id,
            "prescription_id": v.prescription_id or (p_rec.prescription_id if p_rec else None),
            "visit_date": v.visit_date.isoformat() if isinstance(v.visit_date, datetime) else str(v.visit_date),
            "day_of_week": day_of_week,
            "time": time_str,
            "date": date_str,
            "formatted_date": fmt_date,
            "diagnosis": v.diagnosis,
            "clinical_notes": v.clinical_notes,
            "clinician_id": v.doctor_id or "DOC-DEFAULT",
            "clinician_role": "ATTENDING_PHYSICIAN",
            "status": v.status,
            "symptoms": symptoms_list,
            "medications": [{
                "name": item.medication_name,
                "dose": item.dose,
                "unit": item.unit,
                "route": item.route,
                "frequency": item.frequency,
                "duration_days": item.duration_days,
                "indication": item.indication,
            } for item in items],
            "findings": [{
                "warning_id": warning.warning_id,
                "rule_id": warning.rule_id,
                "severity": warning.severity,
                "title": warning.title,
                "clinical_concern": warning.clinical_concern,
                "recommendation": warning.recommendation,
                "status": warning.status,
            } for warning in warnings],
            "overrides": overrides,
        })

    # If no VisitDB records exist, fall back to PrescriptionDB records for backward compatibility
    if not visits:
        prescriptions = (
            db.query(PrescriptionDB)
            .filter(PrescriptionDB.patient_id == patient_id)
            .order_by(PrescriptionDB.created_at.desc())
            .all()
        )
        for prescription in prescriptions:
            warnings = db.query(SafetyWarningDB).filter(SafetyWarningDB.prescription_id == prescription.prescription_id).all()
            overrides = []
            for warning in warnings:
                override = db.query(ClinicianOverrideDB).filter(ClinicianOverrideDB.warning_id == warning.warning_id).first()
                if override:
                    overrides.append({
                        "warning_id": warning.warning_id,
                        "rule_id": warning.rule_id,
                        "reason": override.override_reason,
                        "clinician_id": override.clinician_id,
                        "clinician_role": override.clinician_role,
                        "timestamp": override.timestamp,
                    })
            v_dt = prescription.created_at if isinstance(prescription.created_at, datetime) else None
            day_of_week = v_dt.strftime("%A") if v_dt else ""
            time_str = v_dt.strftime("%I:%M %p") if v_dt else ""
            date_str = v_dt.strftime("%d %B %Y") if v_dt else ""
            fmt_date = f"{day_of_week}, {date_str} at {time_str}" if v_dt else str(prescription.created_at)

            visits.append({
                "visit_id": f"VIS-{prescription.prescription_id[-6:]}",
                "prescription_id": prescription.prescription_id,
                "visit_date": prescription.created_at.isoformat() if isinstance(prescription.created_at, datetime) else str(prescription.created_at),
                "day_of_week": day_of_week,
                "time": time_str,
                "date": date_str,
                "formatted_date": fmt_date,
                "diagnosis": prescription.diagnosis,
                "clinical_notes": prescription.raw_text,
                "clinician_id": prescription.clinician_id,
                "clinician_role": prescription.clinician_role,
                "status": prescription.status,
                "symptoms": [],
                "medications": [{
                    "name": item.medication_name,
                    "dose": item.dose,
                    "unit": item.unit,
                    "route": item.route,
                    "frequency": item.frequency,
                    "duration_days": item.duration_days,
                    "indication": item.indication,
                } for item in prescription.items],
                "findings": [{
                    "warning_id": warning.warning_id,
                    "rule_id": warning.rule_id,
                    "severity": warning.severity,
                    "title": warning.title,
                    "clinical_concern": warning.clinical_concern,
                    "recommendation": warning.recommendation,
                    "status": warning.status,
                } for warning in warnings],
                "overrides": overrides,
            })

    audit_rows = (
        db.query(AuditLogDB)
        .filter(AuditLogDB.patient_id == patient_id)
        .order_by(AuditLogDB.timestamp.desc())
        .all()
    )
    return {
        "patient": get_patient(patient_id, db),
        "visits": visits,
        "audit": [{
            "timestamp": row.timestamp,
            "event_type": row.event_type,
            "prescription_id": row.prescription_id,
            "clinician_id": row.clinician_id,
            "clinician_role": row.clinician_role,
            "action_summary": row.action_summary,
        } for row in audit_rows],
    }


@app.get("/api/patients/{patient_id}/timeline")
def get_patient_timeline(patient_id: str, db: Session = Depends(get_db)):
    """Return chronological timeline of all completed visits for patient."""
    history = get_patient_history(patient_id, db)
    return {
        "patient_id": patient_id,
        "timeline": history["visits"]
    }


@app.get("/api/patients/{patient_id}/medications")
def get_patient_medication_history(patient_id: str, db: Session = Depends(get_db)):
    """Dedicated medication / prescription history view for a patient."""
    history = get_patient_history(patient_id, db)
    med_list = []
    for visit in history["visits"]:
        v_date = visit["visit_date"].strftime("%d %b %Y") if hasattr(visit["visit_date"], "strftime") else str(visit["visit_date"])
        for med in visit["medications"]:
            med_list.append({
                "visit_id": visit.get("visit_id"),
                "date": v_date,
                "diagnosis": visit.get("diagnosis"),
                "medication": med.get("name"),
                "dose": f"{med.get('dose')} {med.get('unit') or ''}".strip() if med.get('dose') else None,
                "frequency": med.get("frequency"),
                "duration_days": med.get("duration_days"),
                "route": med.get("route"),
            })
    return {
        "patient_id": patient_id,
        # The clinician recognises the patient by name; the id keys the record.
        "display_name": (history.get("patient") or {}).get("display_name"),
        "medication_history": med_list
    }


@app.post("/api/patients/{patient_id}/visits", status_code=status.HTTP_201_CREATED)
def create_patient_visit(
    patient_id: str,
    payload: VisitCreate,
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal),
):
    """
    Save a completed visit for an existing patient.
    IMMUTABLE: NEVER overwrite previous visits.
    Stores symptoms, diagnosis, prescription items, evaluates AntiBioTix safety rules,
    indexes visit into RAG store, and appends to audit trail.
    """
    require_clinician(principal)
    p = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    visit_count = db.query(VisitDB).filter(VisitDB.patient_id == patient_id).count()
    visit_id = f"VIS-{uuid.uuid4().hex[:6].upper()}"

    # 1. Create Prescription if prescription_items present
    presc_id = None
    warnings = []
    if payload.prescription_items or payload.raw_prescription_text:
        presc_id = f"RX-{uuid.uuid4().hex[:6].upper()}"
        new_presc = PrescriptionDB(
            prescription_id=presc_id,
            patient_id=patient_id,
            visit_id=visit_id,
            diagnosis=payload.diagnosis,
            raw_text=payload.raw_prescription_text,
            clinician_id=principal.get("clinician_id", payload.doctor_id),
            clinician_role=principal.get("clinician_role", "ATTENDING_PHYSICIAN"),
            status="ANALYZED"
        )
        db.add(new_presc)

        for it in payload.prescription_items:
            db_item = PrescriptionItemDB(
                prescription_id=presc_id,
                medication_name=it.medication_name,
                dose=it.dose,
                unit=it.unit,
                route=it.route,
                frequency=it.frequency,
                duration_days=it.duration_days,
                indication=it.indication or payload.diagnosis,
                antimicrobial_class=it.antimicrobial_class,
                aware_category=it.aware_category.value if hasattr(it.aware_category, 'value') else str(it.aware_category or 'NOT_APPLICABLE'),
                extraction_confidence_json=json.dumps(it.extraction_confidence or {})
            )
            db.add(db_item)
        db.commit()

        # Run AntiBioTix 24-rule Safety Engine
        patient_schema = PatientCreate(
            patient_id=p.patient_id,
            age=p.age,
            age_category=p.age_category,
            weight_kg=p.weight_kg,
            sex=p.sex,
            allergies=allergy_store.substances(p.allergies_json),
            allergy_provenance={
                r["substance"].strip().lower(): r.get("source", allergy_store.SELF_REPORTED)
                for r in allergy_store.normalise(p.allergies_json)
            },
            allergy_status_known=p.allergy_status_known,
            egfr_ml_min=p.egfr_ml_min,
            serum_creatinine_mg_dl=p.serum_creatinine_mg_dl,
            renal_status_known=p.renal_status_known,
            child_pugh_class=p.child_pugh_class,
            hepatic_status_known=p.hepatic_status_known,
            pregnancy_status=p.pregnancy_status,
            lactation_status=p.lactation_status,
            active_medications=json.loads(p.active_medications_json) if p.active_medications_json else [],
            clinical_notes=p.clinical_notes
        )
        presc_schema = PrescriptionCreate(
            prescription_id=presc_id,
            patient_id=patient_id,
            diagnosis=payload.diagnosis,
            raw_text=payload.raw_prescription_text,
            items=payload.prescription_items,
            clinician_id=principal.get("clinician_id", payload.doctor_id),
            clinician_role=ClinicianRole.ATTENDING_PHYSICIAN
        )
        warnings = rule_engine.evaluate_prescription(patient_schema, presc_schema, prescription_id=presc_id)

        for w in warnings:
            warn_db = SafetyWarningDB(
                warning_id=w.warning_id,
                prescription_id=presc_id,
                rule_id=w.rule_id,
                category=w.category.value,
                severity=w.severity.value,
                title=w.title,
                clinical_concern=w.clinical_concern,
                recommendation=w.recommendation,
                prescribed_drug=w.prescribed_drug,
                interacting_factor=w.interacting_factor,
                evidence_document=w.evidence.document_title,
                evidence_version=w.evidence.guideline_version,
                evidence_passage=w.evidence.verbatim_passage,
                evidence_url=w.evidence.source_url,
                supporting_labels_json=json.dumps([sl.model_dump() for sl in w.supporting_labels]) if w.supporting_labels else None,
                status="ACTIVE"
            )
            db.add(warn_db)
            audit_logger.record_warning_triggered(db, w.rule_id)
        db.commit()

    # 2. Create Visit Record
    v_date = now_ist()
    if payload.visit_date:
        try:
            v_date = datetime.fromisoformat(payload.visit_date.replace("Z", "+00:00"))
        except Exception:
            pass

    visit_obj = VisitDB(
        visit_id=visit_id,
        patient_id=patient_id,
        doctor_id=principal.get("clinician_id", payload.doctor_id),
        visit_date=v_date,
        diagnosis=payload.diagnosis,
        clinical_notes=payload.clinical_notes or payload.symptoms_text,
        prescription_id=presc_id,
        status="COMPLETED",
        feedback_code=_new_feedback_code(db),
    )
    db.add(visit_obj)
    db.commit()

    # 3. Create Symptoms
    for sym in payload.symptoms:
        db.add(SymptomDB(
            visit_id=visit_id,
            patient_id=patient_id,
            name=sym.name,
            severity=sym.severity or "Moderate",
            duration=sym.duration,
            onset=sym.onset,
            notes=sym.notes
        ))
    if payload.diagnosis:
        db.add(DiagnosisDB(
            visit_id=visit_id,
            patient_id=patient_id,
            diagnosis_name=payload.diagnosis
        ))
    db.commit()

    # 4. Index Visit into RAG System
    index_visit_for_rag(db, visit_id)

    # 5. Audit Log
    audit_logger.log_event(
        db=db,
        event_type="VISIT_SAVED",
        prescription_id=presc_id or "-",
        patient_id=patient_id,
        clinician_id=principal.get("clinician_id", payload.doctor_id),
        clinician_role=principal.get("clinician_role", "ATTENDING_PHYSICIAN"),
        action_summary=f"Visit {visit_id} saved for patient {patient_id} with diagnosis '{payload.diagnosis}'.",
        payload={
            "visit_id": visit_id,
            "diagnosis": payload.diagnosis,
            "symptoms_count": len(payload.symptoms),
            "prescription_items_count": len(payload.prescription_items),
            "warnings_count": len(warnings)
        }
    )

    day_of_week = visit_obj.visit_date.strftime("%A") if isinstance(visit_obj.visit_date, datetime) else ""
    time_str = visit_obj.visit_date.strftime("%I:%M %p") if isinstance(visit_obj.visit_date, datetime) else ""
    date_str = visit_obj.visit_date.strftime("%d %B %Y") if isinstance(visit_obj.visit_date, datetime) else ""
    fmt_date = f"{day_of_week}, {date_str} at {time_str}" if day_of_week else str(visit_obj.visit_date)

    return {
        "status": "SAVED",
        "message": "Visit saved successfully.",
        # The follow-up code, returned so the clinician can read it out or print it.
        # It is generated at visit creation regardless; without returning it here the
        # patient has no route to the form and the whole loop is unreachable.
        "feedback_code": visit_obj.feedback_code,
        "visit_id": visit_id,
        "prescription_id": presc_id,
        "patient_id": patient_id,
        "visit_date": visit_obj.visit_date.isoformat() if isinstance(visit_obj.visit_date, datetime) else str(visit_obj.visit_date),
        "day_of_week": day_of_week,
        "time": time_str,
        "date": date_str,
        "formatted_date": fmt_date,
        "warnings_count": len(warnings),
        "indexed_in_rag": True
    }


@app.post("/api/patients/{patient_id}/ask")
def ask_patient_history_endpoint(
    patient_id: str,
    payload: PatientAskQuery,
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal),
):
    """
    Ask natural language questions about the patient's history.
    Strictly scoped to patient_id to prevent cross-patient retrieval.
    """
    require_patient_scope(principal, patient_id)
    result = ask_patient_history(db, patient_id, payload.question)
    return result


@app.get("/api/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Doctor Dashboard metrics backed by real database data.
    """
    total_patients = db.query(PatientDB).count()
    total_visits = db.query(VisitDB).count()
    total_prescriptions = db.query(PrescriptionDB).count()
    total_warnings = db.query(SafetyWarningDB).filter(SafetyWarningDB.status == "ACTIVE").count()
    critical_warnings = db.query(SafetyWarningDB).filter(
        SafetyWarningDB.status == "ACTIVE",
        SafetyWarningDB.severity == "CRITICAL"
    ).count()

    recent_patients_db = db.query(PatientDB).order_by(PatientDB.id.desc()).limit(5).all()
    recent_patients = []
    for p in recent_patients_db:
        latest_v = (
            db.query(VisitDB)
            .filter(VisitDB.patient_id == p.patient_id)
            .order_by(VisitDB.visit_date.desc())
            .first()
        )
        recent_patients.append({
            "patient_id": p.patient_id,
            "display_name": p.display_name or f"Patient {p.patient_id}",
            "age": p.age,
            "sex": p.sex,
            "last_visit": latest_v.visit_date.strftime("%d %B %Y") if (latest_v and latest_v.visit_date) else "No visits",
            "last_diagnosis": latest_v.diagnosis if latest_v else "None recorded",
            "status": "Active"
        })

    return {
        "total_patients": total_patients,
        "total_visits": total_visits,
        "total_prescriptions": total_prescriptions,
        "total_active_warnings": total_warnings,
        "critical_warnings_count": critical_warnings,
        "recent_patients": recent_patients
    }


@app.get("/api/visits/{visit_id}/pdf")
def download_visit_prescription_pdf(visit_id: str, db: Session = Depends(get_db)):
    """Generate and return official prescription PDF from stored visit data."""
    from fastapi.responses import Response
    from backend.pdf_generator import generate_prescription_pdf

    visit = db.query(VisitDB).filter(VisitDB.visit_id == visit_id).first()
    if not visit:
        # Fallback to check by prescription_id
        visit = db.query(VisitDB).filter(VisitDB.prescription_id == visit_id).first()
        if not visit:
            p_direct = db.query(PrescriptionDB).filter(PrescriptionDB.prescription_id == visit_id).first()
            if p_direct:
                visit = VisitDB(
                    visit_id=f"VIS-{p_direct.prescription_id[-6:]}",
                    patient_id=p_direct.patient_id,
                    doctor_id=p_direct.clinician_id,
                    visit_date=p_direct.created_at,
                    diagnosis=p_direct.diagnosis,
                    clinical_notes=p_direct.raw_text,
                    prescription_id=p_direct.prescription_id
                )
            else:
                raise HTTPException(status_code=404, detail="Visit or prescription record not found")

    patient = db.query(PatientDB).filter(PatientDB.patient_id == visit.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found")

    # Fetch prescription items
    items_db = []
    p_rec = None
    if visit.prescription_id:
        p_rec = db.query(PrescriptionDB).filter(PrescriptionDB.prescription_id == visit.prescription_id).first()

    if not p_rec:
        p_rec = db.query(PrescriptionDB).filter(PrescriptionDB.patient_id == visit.patient_id).order_by(PrescriptionDB.created_at.desc()).first()

    if p_rec:
        items_db = db.query(PrescriptionItemDB).filter(PrescriptionItemDB.prescription_id == p_rec.prescription_id).all()
        warn_db = db.query(SafetyWarningDB).filter(SafetyWarningDB.prescription_id == p_rec.prescription_id).all()
    else:
        warn_db = []

    warnings = [{
        "rule_id": w.rule_id,
        "severity": w.severity,
        "title": w.title,
        "recommendation": w.recommendation
    } for w in warn_db]

    overrides = []
    for w in warn_db:
        ov = db.query(ClinicianOverrideDB).filter(ClinicianOverrideDB.warning_id == w.warning_id).first()
        if ov:
            overrides.append({
                "rule_id": w.rule_id,
                "clinician_role": ov.clinician_role,
                "reason": ov.override_reason
            })

    items = [{
        "medication_name": item.medication_name,
        "dose": item.dose,
        "unit": item.unit,
        "route": item.route,
        "frequency": item.frequency,
        "duration_days": item.duration_days,
        "indication": item.indication
    } for item in items_db]

    patient_dict = {
        "patient_id": patient.patient_id,
        "age": patient.age,
        "sex": patient.sex,
        "weight_kg": patient.weight_kg,
        "egfr_ml_min": patient.egfr_ml_min,
        "child_pugh_class": patient.child_pugh_class,
        "allergies": allergy_store.substances(patient.allergies_json),
        "active_medications": json.loads(patient.active_medications_json) if patient.active_medications_json else []
    }

    visit_dict = {
        "visit_id": visit.visit_id,
        "visit_date": visit.visit_date,
        "diagnosis": visit.diagnosis,
        "clinical_notes": visit.clinical_notes
    }

    pdf_bytes = generate_prescription_pdf(
        patient=patient_dict,
        visit=visit_dict,
        prescription_items=items,
        warnings=warnings,
        overrides=overrides,
        clinician_id=visit.doctor_id or "DOC-DEMO-01",
        clinician_role="ATTENDING_PHYSICIAN"
    )

    filename = f"Prescription_{patient.patient_id}_{visit.visit_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@app.put("/api/patients/{patient_id}/contact")
def update_patient_contact(
    patient_id: str,
    payload: PatientContactUpdate,
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal),
):
    """
    Add or correct the reminder contact for an existing patient.

    Exists so a returning patient who never gave an address can be reached from the
    next booking onwards without re-registering. Passing an empty string clears a
    field, which is how a patient withdraws consent to be contacted.
    """
    require_clinician(principal)
    patient = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found.")

    if payload.contact_email is not None:
        patient.contact_email = payload.contact_email.strip() or None
    if payload.contact_phone is not None:
        patient.contact_phone = payload.contact_phone.strip() or None
    db.commit()

    return {
        "patient_id": patient_id,
        "contact_email": patient.contact_email,
        "contact_phone": patient.contact_phone,
        "reminders_reachable": bool(patient.contact_email or patient.contact_phone),
    }


@app.post("/api/appointments", status_code=status.HTTP_201_CREATED)
def schedule_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal),
):
    """
    Schedule a follow-up check-up appointment for a patient.
    Captures patient-doctor relationship, emails, phone number, and schedules multi-channel notifications.
    """
    require_clinician(principal)
    p = db.query(PatientDB).filter(PatientDB.patient_id == payload.patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    try:
        app_dt = datetime.fromisoformat(payload.appointment_date)
    except Exception:
        app_dt = now_ist()

    if app_dt.tzinfo is None:
        app_dt = app_dt.replace(tzinfo=IST)

    appt_id = f"APT-{uuid.uuid4().hex[:6].upper()}"
    time_info = format_ist_datetime(app_dt)

    # --- resolve reminder contacts -----------------------------------------
    patient_row = db.query(PatientDB).filter(
        PatientDB.patient_id == payload.patient_id).first()
    doctor_id = principal.get("clinician_id", "DOC-DEMO-01")
    doctor_row = db.query(DoctorDB).filter(DoctorDB.doctor_id == doctor_id).first()

    resolved_patient_email = (payload.patient_email or "").strip() or (
        patient_row.contact_email if patient_row else None)
    resolved_patient_phone = (payload.patient_phone or "").strip() or (
        patient_row.contact_phone if patient_row else None)
    resolved_doctor_email = (payload.doctor_email or "").strip() or (
        doctor_row.email if doctor_row else None)

    # Remember anything newly supplied, so the next booking for this patient does
    # not ask again. Only ever fills a blank or replaces with an explicitly given
    # value; it never quietly discards what is on file.
    if patient_row:
        if (payload.patient_email or "").strip():
            patient_row.contact_email = payload.patient_email.strip()
        if (payload.patient_phone or "").strip():
            patient_row.contact_phone = payload.patient_phone.strip()
    if (payload.doctor_email or "").strip():
        # A clinician can authenticate through the in-memory credential registry
        # without ever having a doctors row, so remembering their address means
        # creating the row when it is missing. Otherwise every booking would ask
        # for the clinician's e-mail again.
        if not doctor_row:
            doctor_row = DoctorDB(
                doctor_id=doctor_id,
                display_name=principal.get("clinician_name") or doctor_id,
                role=principal.get("clinician_role", "ATTENDING_PHYSICIAN"),
            )
            db.add(doctor_row)
        doctor_row.email = payload.doctor_email.strip()

    appt = AppointmentDB(
        appointment_id=appt_id,
        patient_id=payload.patient_id,
        visit_id=payload.visit_id,
        doctor_id=principal.get("clinician_id", "DOC-DEMO-01"),
        appointment_date=app_dt,
        reason=payload.reason,
        # No placeholder contact details. A fabricated address meant a patient with
        # nothing on file was still recorded as reminded, at an address that does
        # not exist; a missing contact is now recorded as NO_CONTACT_ON_RECORD.
        #
        # Resolution order is: what this booking supplied, then what the patient and
        # doctor records already hold. That is what makes a RETURNING patient work --
        # they gave an address once and are not asked again.
        doctor_email=resolved_doctor_email,
        patient_email=resolved_patient_email,
        patient_phone=resolved_patient_phone,
        # Nothing has been sent at booking time. These flags are written by the
        # scheduler after a dispatch attempt, never here: they previously claimed
        # an advance notice that no code path ever sent.
        notification_sent=False,
        advance_notice_sent=False,
        same_day_alert_sent=False,
        delivery_status_json=json.dumps({}),
        status="SCHEDULED"
    )
    db.add(appt)
    db.commit()

    # Log immutable audit event
    audit_logger.log_event(
        db=db,
        event_type="APPOINTMENT_SCHEDULED",
        prescription_id="-",
        patient_id=payload.patient_id,
        clinician_id=principal.get("clinician_id", "DOC-DEMO-01"),
        clinician_role=principal.get("clinician_role", "ATTENDING_PHYSICIAN"),
        action_summary=f"Check-up appointment scheduled for {payload.patient_id} on {time_info['formatted']}.",
        payload={
            "appointment_id": appt_id,
            "appointment_date_ist": time_info["iso"],
            "formatted_time": time_info["formatted"],
            "reason": payload.reason,
            "patient_phone": appt.patient_phone,
            "doctor_email": appt.doctor_email,
            "patient_email": appt.patient_email
        }
    )

    # If appointment is scheduled for today (IST), trigger immediate notification engine
    same_day_triggered = False
    if app_dt.date() == now_ist().date():
        scan_and_trigger_same_day_notifications(db)
        same_day_triggered = True

    return {
        "status": "SCHEDULED",
        "appointment_id": appt_id,
        "patient_id": payload.patient_id,
        "appointment_date": app_dt.isoformat(),
        "formatted_date_ist": time_info["formatted"],
        "day_of_week": time_info["day_of_week"],
        "time": time_info["time"],
        "reason": payload.reason,
        "same_day_alert_triggered": same_day_triggered,
        # What a reminder can actually reach for this appointment. Returned so the
        # booking UI can say "no e-mail on file for this patient" at the moment a
        # clinician could still fix it, rather than reporting success regardless.
        "reminder_contacts": {
            "patient_email": resolved_patient_email,
            "patient_phone": resolved_patient_phone,
            "doctor_email": resolved_doctor_email,
            "patient_email_source": (
                "SUPPLIED_NOW" if (payload.patient_email or "").strip()
                else "PATIENT_RECORD" if resolved_patient_email else "NONE_ON_FILE"
            ),
            "doctor_email_source": (
                "SUPPLIED_NOW" if (payload.doctor_email or "").strip()
                else "DOCTOR_RECORD" if resolved_doctor_email else "NONE_ON_FILE"
            ),
        },
        "channels": channel_status(),
        "notification_channels": ["Email (Doctor & Patient)", "SMS / WhatsApp", "In-App Console Alert"],
        "notification": "Follow-up notifications and same-day morning alerts (IST) configured."
    }


@app.post("/api/notifications/trigger-same-day")
def trigger_same_day_notifications_endpoint(
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal)
):
    """
    Automated / manual trigger for same-day check-up notification scan.
    Identifies appointments occurring on current date (IST), dispatches multi-channel alerts,
    and updates audit log.
    """
    require_clinician(principal)
    report = scan_and_trigger_same_day_notifications(db)
    return report


@app.get("/api/notifications/in-app")
def get_in_app_notifications(patient_id: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Fetch active in-app notifications for the clinician/patient console.

    Read from the notifications table rather than a module-level list, which
    emptied on restart and was invisible to any other worker process.
    """
    return list_in_app_notifications(db, patient_id=patient_id)


@app.get("/api/notifications/status")
def get_notification_channel_status(db: Session = Depends(get_db)):
    """
    What this deployment can actually deliver, and what it has recorded.

    Exists so "was the patient actually told?" is answerable without reading the
    source. An unconfigured channel reports itself as unconfigured here and in
    every stored delivery record.
    """
    counts: Dict[str, int] = {}
    for status_value, count in (
        db.query(NotificationDB.status, func.count(NotificationDB.id))
        .group_by(NotificationDB.status)
        .all()
    ):
        counts[status_value] = int(count)
    return {
        "channels": channel_status(),
        "scheduler": {
            "enabled": notification_scheduler_enabled(),
            "interval_seconds": NOTIFICATION_SCHEDULER_INTERVAL_SECONDS,
            "last_run_ist": _NOTIFICATION_SCHEDULER_STATE.get("last_run_ist"),
            "last_error": _NOTIFICATION_SCHEDULER_STATE.get("last_error"),
            "runs_completed": _NOTIFICATION_SCHEDULER_STATE.get("runs", 0),
        },
        "delivery_attempts_by_status": counts,
    }


@app.post("/api/notifications/run-scan")
def run_notification_scans(
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal),
):
    """Run both the advance and same-day scans now, as the scheduler does."""
    require_clinician(principal)
    return run_all_scans(db)


@app.get("/api/patients/{patient_id}/next-appointment")
def get_next_patient_appointment(patient_id: str, db: Session = Depends(get_db)):
    """
    Retrieve the next scheduled check-up appointment for a specific patient.
    """
    p = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    start_bound, _ = get_ist_bounds_for_date(now_ist())
    appt = (
        db.query(AppointmentDB)
        .filter(
            AppointmentDB.patient_id == patient_id,
            AppointmentDB.status == "SCHEDULED",
            AppointmentDB.appointment_date >= start_bound
        )
        .order_by(AppointmentDB.id.desc())
        .first()
    )

    if not appt:
        appt = (
            db.query(AppointmentDB)
            .filter(
                AppointmentDB.patient_id == patient_id,
                AppointmentDB.status == "SCHEDULED"
            )
            .order_by(AppointmentDB.id.desc())
            .first()
        )

    if not appt:
        return {"has_appointment": False, "message": "No upcoming check-up scheduled."}

    time_info = format_ist_datetime(appt.appointment_date)
    is_today = appt.appointment_date.date() == now_ist().date()

    return {
        "has_appointment": True,
        "appointment_id": appt.appointment_id,
        "patient_id": appt.patient_id,
        "visit_id": appt.visit_id,
        "doctor_id": appt.doctor_id,
        "appointment_date": appt.appointment_date.isoformat(),
        "formatted_date_ist": time_info["formatted"],
        "day_of_week": time_info["day_of_week"],
        "time": time_info["time"],
        "date": time_info["date"],
        "reason": appt.reason,
        "is_today": is_today,
        "same_day_alert_sent": appt.same_day_alert_sent,
        "doctor_email": appt.doctor_email,
        "patient_email": appt.patient_email,
        "patient_phone": appt.patient_phone
    }


@app.get("/api/appointments")
def list_appointments(patient_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(AppointmentDB)
    if patient_id:
        query = query.filter(AppointmentDB.patient_id == patient_id)
    appts = query.order_by(AppointmentDB.appointment_date.asc()).all()
    results = []
    for a in appts:
        results.append({
            "appointment_id": a.appointment_id,
            "patient_id": a.patient_id,
            "visit_id": a.visit_id,
            "doctor_id": a.doctor_id,
            "appointment_date": a.appointment_date.isoformat(),
            "reason": a.reason,
            "status": a.status,
            "notification_sent": a.notification_sent
        })
    return results


# ---------------------------------------------------------------------------
# Patient registration, medication reconciliation, allergy self-reporting
# (Sections 3, 3B, 18A, 24, 25)
# ---------------------------------------------------------------------------

def _next_patient_id(db: Session) -> str:
    """Server-issued synthetic identifier. Clients never choose it."""
    existing = {p.patient_id for p in db.query(PatientDB).all()}
    n = 1
    while f"PATIENT-{n:03d}" in existing:
        n += 1
    return f"PATIENT-{n:03d}"


@app.post("/api/patients", status_code=status.HTTP_201_CREATED)
def register_patient(
    payload: PatientRegistration,
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal),
):
    """
    Create a patient record. Clinician roles only.

    The patient_id is issued by the server, never supplied by the caller.

    Real contact details are accepted and stored: contact_email and contact_phone
    exist so appointment reminders reach the patient, and so a returning patient is
    not asked for an address at every booking. Both are optional -- a patient who
    supplies neither is simply never sent a reminder -- and nothing outside the
    reminder path reads them.

    Note the defaults: allergy, renal and hepatic status all start UNKNOWN
    rather than normal. A newly registered patient with nothing filled in
    produces missing-information warnings, not a clean bill of health.
    """
    require_clinician(principal)
    role = principal.get("clinician_role", "").upper()
    if role not in PATIENT_MANAGEMENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' is not permitted to register patients.",
        )

    patient_id = _next_patient_id(db)
    # The NAME, stored as the name. This used to write "PATIENT-021 (Meera
    # Krishnan)" -- the record key glued onto the front of the person -- so every
    # newly registered patient re-created the format the seeded roster was cleaned
    # of. The id is already on the row; repeating it inside the name field means
    # every reader has to strip it back off, and one that forgets prints it twice.
    raw_name = (payload.display_name or "").strip()
    # A name that already carries the old wrapper is unwrapped rather than nested.
    wrapped = re.match(r"^\s*PATIENT-\d+\s*\((.+)\)\s*$", raw_name)
    if wrapped:
        raw_name = wrapped.group(1).strip()
    # A "name" that is just an id is not a name, and neither is an empty box.
    if not raw_name or re.fullmatch(r"PATIENT-\d+", raw_name):
        disp_name = None
    else:
        disp_name = raw_name

    p = PatientDB(
        patient_id=patient_id,
        display_name=disp_name,
        age=payload.age,
        age_category=payload.age_category.value if payload.age_category else "UNKNOWN",
        sex=payload.sex or "UNKNOWN",
        weight_kg=payload.weight_kg,
        allergies_json=allergy_store.dumps([]),
        allergy_status_known=payload.allergy_status_known,
        contact_email=(payload.contact_email or "").strip() or None,
        contact_phone=(payload.contact_phone or "").strip() or None,
        egfr_ml_min=payload.egfr_ml_min,
        serum_creatinine_mg_dl=payload.serum_creatinine_mg_dl,
        renal_status_known=payload.renal_status_known,
        child_pugh_class=payload.child_pugh_class,
        hepatic_status_known=payload.hepatic_status_known,
        pregnancy_status=payload.pregnancy_status.value if payload.pregnancy_status else "UNKNOWN",
        lactation_status=payload.lactation_status.value if payload.lactation_status else "UNKNOWN",
        active_medications_json=json.dumps(payload.active_medications or []),
        clinical_notes=payload.clinical_notes,
    )
    db.add(p)
    db.commit()

    audit_logger.log_event(
        db=db, event_type="PATIENT_REGISTERED", prescription_id="-",
        patient_id=patient_id,
        clinician_id=principal.get("clinician_id", "UNKNOWN"),
        clinician_role=role,
        action_summary=f"Patient record {patient_id} created.",
        payload={
            "age": payload.age,
            "allergy_status_known": payload.allergy_status_known,
            "renal_status_known": payload.renal_status_known,
            "active_medication_count": len(payload.active_medications or []),
        },
        model_version=SYSTEM_VERSION, prompt_template_id=PROMPT_TEMPLATE_ID,
    )

    return {
        "patient_id": patient_id,
        "status": "CREATED",
        "patient_access_token": create_patient_token(patient_id),
        "token_note": (
            "Give this to the patient so they can report their own allergies. It is "
            "scoped to this record only and cannot prescribe, override, or read "
            "another patient."
        ),
        "unknowns": [
            k for k, v in [
                ("allergy history", payload.allergy_status_known),
                ("renal function", payload.renal_status_known),
                ("hepatic function", payload.hepatic_status_known),
            ] if not v
        ],
    }


@app.put("/api/patients/{patient_id}/medications")
def update_medications(
    patient_id: str,
    payload: MedicationUpdate,
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal),
):
    """
    Replace a patient's current medication list. Clinician roles only -
    medication reconciliation is a clinical act, not self-service.
    """
    require_clinician(principal)
    role = principal.get("clinician_role", "").upper()
    if role not in PATIENT_MANAGEMENT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Role '{role}' is not permitted to edit medications.")

    p = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    before = json.loads(p.active_medications_json) if p.active_medications_json else []
    cleaned = [m.strip() for m in payload.active_medications if m and m.strip()]
    p.active_medications_json = json.dumps(cleaned)
    db.commit()

    audit_logger.log_event(
        db=db, event_type="MEDICATIONS_UPDATED", prescription_id="-",
        patient_id=patient_id,
        clinician_id=principal.get("clinician_id", "UNKNOWN"), clinician_role=role,
        action_summary=f"Current medications updated for {patient_id} ({len(before)} -> {len(cleaned)}).",
        payload={"before": before, "after": cleaned, "reason": payload.reason},
        model_version=SYSTEM_VERSION, prompt_template_id=PROMPT_TEMPLATE_ID,
    )
    return {"patient_id": patient_id, "active_medications": cleaned,
            "previous_count": len(before), "current_count": len(cleaned),
            "note": "Re-analyse any active prescription - interaction checks read this list."}


@app.post("/api/patients/{patient_id}/allergies", status_code=status.HTTP_201_CREATED)
def report_allergy(
    patient_id: str,
    payload: AllergyReportRequest,
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal),
):
    """
    Record an allergy. Patients may submit for their own record; clinicians for any.

    A patient submission is stored as SELF_REPORTED. It still triggers the
    allergy rules - suppressing a safety check because the report is unverified
    would be the wrong trade - but every warning derived from it states that the
    report has not been clinician-verified.
    """
    require_patient_scope(principal, patient_id)

    p = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    role = principal.get("clinician_role", "").upper()
    is_patient = role == "PATIENT"
    source = allergy_store.SELF_REPORTED if is_patient else allergy_store.CLINICIAN_VERIFIED

    records, added = allergy_store.add_report(
        p.allergies_json, payload.substance,
        source=source, reported_by=principal.get("clinician_id", "UNKNOWN"),
        reaction=payload.reaction,
    )
    p.allergies_json = allergy_store.dumps(records)
    # Recording an allergy means a history now exists, clearing the
    # missing-allergy-information guard.
    p.allergy_status_known = True
    db.commit()

    audit_logger.log_event(
        db=db, event_type="ALLERGY_REPORTED", prescription_id="-",
        patient_id=patient_id,
        clinician_id=principal.get("clinician_id", "UNKNOWN"), clinician_role=role,
        action_summary=f"Allergy '{payload.substance}' recorded for {patient_id} ({source}).",
        payload={"substance": payload.substance, "source": source,
                 "reaction": payload.reaction, "newly_added": added},
        model_version=SYSTEM_VERSION, prompt_template_id=PROMPT_TEMPLATE_ID,
    )

    return {
        "patient_id": patient_id,
        "substance": payload.substance,
        "source": source,
        "newly_added": added,
        "allergy_records": allergy_store.normalise(p.allergies_json),
        "note": (
            "Recorded as patient-reported and awaiting clinician verification. It will "
            "still trigger allergy safety checks."
            if is_patient else
            "Recorded as clinician-verified."
        ),
    }


@app.post("/api/patients/{patient_id}/allergies/verify")
def verify_allergy(
    patient_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal),
):
    """Promote a self-reported allergy to clinician-verified."""
    require_clinician(principal)
    role = principal.get("clinician_role", "").upper()
    if role not in PATIENT_MANAGEMENT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Role '{role}' is not permitted to verify allergies.")

    substance = (payload or {}).get("substance", "")
    if not substance:
        raise HTTPException(status_code=422, detail="substance is required")

    p = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    records, changed = allergy_store.verify(p.allergies_json, substance,
                                            principal.get("clinician_id", "UNKNOWN"))
    if not changed:
        raise HTTPException(status_code=404,
                            detail=f"No unverified allergy '{substance}' found for {patient_id}.")
    p.allergies_json = allergy_store.dumps(records)
    db.commit()

    audit_logger.log_event(
        db=db, event_type="ALLERGY_VERIFIED", prescription_id="-",
        patient_id=patient_id,
        clinician_id=principal.get("clinician_id", "UNKNOWN"), clinician_role=role,
        action_summary=f"Allergy '{substance}' verified for {patient_id}.",
        payload={"substance": substance},
        model_version=SYSTEM_VERSION, prompt_template_id=PROMPT_TEMPLATE_ID,
    )
    return {"patient_id": patient_id, "substance": substance,
            "source": allergy_store.CLINICIAN_VERIFIED,
            "allergy_records": allergy_store.normalise(p.allergies_json)}


@app.post("/api/auth/patient-login")
def patient_login(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Demo patient login. Issues a token scoped to one record.

    A real deployment would authenticate the person; this prototype only
    demonstrates the scoping, and says so.
    """
    patient_id = (payload or {}).get("patient_id", "").strip().upper()
    p = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {
        "access_token": create_patient_token(patient_id),
        "token_type": "bearer",
        "patient_id": patient_id,
        "role": "PATIENT",
        "scope_note": "Scoped to this record. Cannot prescribe, override warnings, or read other patients.",
        "prototype_note": "Demo login only - no credential is verified here.",
    }


# ---------------------------------------------------------------------------
# Structured Extraction Layer (Section 3A)
# ---------------------------------------------------------------------------

@app.post("/api/prescriptions/extract", response_model=ExtractedPrescription)
def extract_prescription_from_text(payload: Dict[str, Any]):
    raw_text = payload.get("raw_text", "")
    extracted = clinical_parser.parse_free_text(raw_text)
    return extracted


# ---------------------------------------------------------------------------
# Prescription Analysis & Clinical Rules Engine (Sections 2, 4, 5, 6, 7, 10, 21)
# ---------------------------------------------------------------------------

@app.post("/api/prescriptions")
def create_prescription(prescription: PrescriptionCreate, db: Session = Depends(get_db)):
    patient_db = db.query(PatientDB).filter(PatientDB.patient_id == prescription.patient_id).first()
    if not patient_db:
        raise HTTPException(status_code=404, detail=f"Patient {prescription.patient_id} not found.")

    presc_id = f"RX-{uuid.uuid4().hex[:8].upper()}"
    new_presc = PrescriptionDB(
        prescription_id=presc_id,
        patient_id=prescription.patient_id,
        diagnosis=prescription.diagnosis,
        raw_text=prescription.raw_text,
        clinician_id=prescription.clinician_id,
        clinician_role=prescription.clinician_role.value if isinstance(prescription.clinician_role, ClinicianRole) else str(prescription.clinician_role),
        status="SUBMITTED"
    )
    db.add(new_presc)

    # Add items
    for it in prescription.items:
        aware_val = it.aware_category.value if hasattr(it.aware_category, 'value') else str(it.aware_category or 'NOT_APPLICABLE')
        db_item = PrescriptionItemDB(
            prescription_id=presc_id,
            medication_name=it.medication_name,
            dose=it.dose,
            unit=it.unit,
            route=it.route,
            frequency=it.frequency,
            duration_days=it.duration_days,
            indication=it.indication,
            antimicrobial_class=it.antimicrobial_class,
            aware_category=aware_val,
            extraction_confidence_json=json.dumps(it.extraction_confidence)
        )
        db.add(db_item)

    db.commit()
    db.refresh(new_presc)

    # Log submission in immutable audit trail
    audit_logger.log_event(
        db=db,
        event_type="PRESCRIPTION_SUBMITTED",
        prescription_id=presc_id,
        patient_id=prescription.patient_id,
        clinician_id=prescription.clinician_id,
        clinician_role=prescription.clinician_role.value if isinstance(prescription.clinician_role, ClinicianRole) else str(prescription.clinician_role),
        action_summary=f"Prescription {presc_id} created for patient {prescription.patient_id} with {len(prescription.items)} medication(s).",
        payload={
            "diagnosis": prescription.diagnosis,
            "raw_text": prescription.raw_text,
            "items_count": len(prescription.items),
            "medications": [i.medication_name for i in prescription.items]
        },
        model_version=SYSTEM_VERSION,
        prompt_template_id=PROMPT_TEMPLATE_ID
    )

    return {"prescription_id": presc_id, "status": "SUBMITTED", "created_at": new_presc.created_at}


@app.post("/api/prescriptions/{prescription_id}/analyze")
def analyze_prescription(prescription_id: str, db: Session = Depends(get_db)):
    presc_db = db.query(PrescriptionDB).filter(PrescriptionDB.prescription_id == prescription_id).first()
    if not presc_db:
        raise HTTPException(status_code=404, detail="Prescription not found")

    patient_db = db.query(PatientDB).filter(PatientDB.patient_id == presc_db.patient_id).first()
    if not patient_db:
        raise HTTPException(status_code=404, detail="Associated patient record not found")

    # Reconstruct patient and prescription schemas
    patient_schema = PatientCreate(
        patient_id=patient_db.patient_id,
        age=patient_db.age,
        age_category=patient_db.age_category,
        weight_kg=patient_db.weight_kg,
        sex=patient_db.sex,
        allergies=allergy_store.substances(patient_db.allergies_json),
        allergy_provenance={
            r["substance"].strip().lower(): r.get("source", allergy_store.SELF_REPORTED)
            for r in allergy_store.normalise(patient_db.allergies_json)
        },
        allergy_status_known=patient_db.allergy_status_known,
        egfr_ml_min=patient_db.egfr_ml_min,
        serum_creatinine_mg_dl=patient_db.serum_creatinine_mg_dl,
        renal_status_known=patient_db.renal_status_known,
        child_pugh_class=patient_db.child_pugh_class,
        hepatic_status_known=patient_db.hepatic_status_known,
        pregnancy_status=patient_db.pregnancy_status,
        lactation_status=patient_db.lactation_status,
        active_medications=json.loads(patient_db.active_medications_json) if patient_db.active_medications_json else [],
        clinical_notes=patient_db.clinical_notes
    )

    items_db = db.query(PrescriptionItemDB).filter(PrescriptionItemDB.prescription_id == prescription_id).all()
    items_schema = [
        PrescriptionItem(
            medication_name=i.medication_name,
            dose=i.dose,
            unit=i.unit,
            route=i.route,
            frequency=i.frequency,
            duration_days=i.duration_days,
            indication=i.indication,
            antimicrobial_class=i.antimicrobial_class,
            aware_category=i.aware_category,
            extraction_confidence=json.loads(i.extraction_confidence_json) if i.extraction_confidence_json else {}
        )
        for i in items_db
    ]

    presc_schema = PrescriptionCreate(
        prescription_id=prescription_id,
        patient_id=presc_db.patient_id,
        diagnosis=presc_db.diagnosis,
        raw_text=presc_db.raw_text,
        items=items_schema,
        clinician_id=presc_db.clinician_id,
        clinician_role=ClinicianRole(presc_db.clinician_role) if presc_db.clinician_role in ClinicianRole.__members__ else ClinicianRole.ATTENDING_PHYSICIAN
    )

    # 1. Execute Deterministic Clinical Rules Engine (Sections 4, 5, 5A, 6, 6A, 11)
    warnings = rule_engine.evaluate_prescription(patient_schema, presc_schema, prescription_id=prescription_id)

    # Map existing warnings to preserve override status and prevent alert fatigue duplicate counting
    existing_warn_map = {
        w.warning_id: w for w in db.query(SafetyWarningDB).filter(SafetyWarningDB.prescription_id == prescription_id).all()
    }
    new_warning_ids = {w.warning_id for w in warnings}

    # Delete stale warnings that no longer apply
    for old_id, old_w in list(existing_warn_map.items()):
        if old_id not in new_warning_ids:
            db.delete(old_w)

    # Insert or update active warnings
    for w in warnings:
        if w.warning_id in existing_warn_map:
            # Preserve existing override status
            w.status = existing_warn_map[w.warning_id].status
        else:
            # New warning triggered
            warn_db = SafetyWarningDB(
                warning_id=w.warning_id,
                prescription_id=prescription_id,
                rule_id=w.rule_id,
                category=w.category.value,
                severity=w.severity.value,
                title=w.title,
                clinical_concern=w.clinical_concern,
                recommendation=w.recommendation,
                prescribed_drug=w.prescribed_drug,
                interacting_factor=w.interacting_factor,
                evidence_document=w.evidence.document_title,
                evidence_version=w.evidence.guideline_version,
                evidence_passage=w.evidence.verbatim_passage,
                evidence_url=w.evidence.source_url,
            supporting_labels_json=json.dumps([sl.model_dump() for sl in w.supporting_labels]) if w.supporting_labels else None,
                rule_author=w.rule_author,
                rule_approval_status=w.rule_approval_status,
                rule_effective_date=w.rule_effective_date,
                status="ACTIVE"
            )
            db.add(warn_db)
            audit_logger.record_warning_triggered(db, w.rule_id)

    db.commit()

    # 2. Retrieve Relevant Guideline Recommendations (Sections 7, 8)
    guideline_info = knowledge_base.match_syndrome_guideline(presc_db.diagnosis)
    # Retrieval augments the deterministic match; it never gates rule firing.
    retrieved_evidence = knowledge_base.retrieve_guideline_evidence(presc_db.diagnosis, k=3)
    guidelines_list = [guideline_info] if guideline_info else []

    # ICMR Standard Treatment Workflows (2022) are returned in their OWN field,
    # not appended to guideline_recommendations, because they are a different
    # ICMR publication with a different scope and must be attributed as such.
    stw_condition = knowledge_base.match_stw_condition(presc_db.diagnosis)

    # Syndrome index of the ICMR Treatment Guidelines 2022-23 edition, surfaced
    # separately from both the workflows and the syndrome file above. It travels
    # with its attribution basis so a consumer can see the edition claim is
    # operator-attested rather than verified against a held PDF.
    stg_condition = knowledge_base.match_stg_condition(presc_db.diagnosis)

    # 3. Retrieve Local AMR Context (Section 13)
    local_amr = []
    for it in items_schema:
        records = knowledge_base.get_local_amr_records(it.medication_name)
        local_amr.extend(records)

    # 4. Generate Deterministic Template Explanation with Injection Defense & Version Pinning (Sections 10, 10A, 22A)
    explainer_res = clinical_explainer.generate_explanation(
        patient=patient_schema,
        items=items_schema,
        warnings=warnings,
        diagnosis=presc_db.diagnosis
    )

    # 5. Deterministic Stewardship Priority Rollup (Sections 14, 15)
    stewardship_priority = compute_stewardship_priority(
        warnings=warnings,
        items=items_schema
    )

    # 5A. Per-drug external evidence, beside the national guidance (Spec §17, §23).
    #
    # For EVERY prescribed drug, not only the ones COVERAGE-001 flagged: the
    # regulatory label -- and the web where a provider is configured -- read
    # against THIS patient's recorded allergies, renal and hepatic status,
    # pregnancy and home medications, returned alongside the held-corpus passages
    # about the same drug so a clinician can compare the two directly.
    #
    # For an unassessed drug this fills a gap the engine reported. For an assessed
    # one it is corroboration, or a visible difference between two sources.
    #
    # DELIBERATELY AFTER THE ROLLUP ABOVE, and reading the warnings rather than
    # the knowledge base: it cannot alter which rules fired or what tier they
    # produced. Wrapped, because an external endpoint being slow or down must
    # degrade this feature and nothing else -- the prescription analysis still
    # returns, with the coverage warning standing exactly as it did before.
    try:
        from backend.agents.external_safety import evidence_for_items

        coverage_findings = evidence_for_items(
            patient_schema, items_schema, warnings, presc_db.diagnosis
        )
    except Exception:
        coverage_findings = []

    # 6. Immutable Audit Log (Section 19)
    audit_logger.log_event(
        db=db,
        event_type="PRESCRIPTION_ANALYZED",
        prescription_id=prescription_id,
        patient_id=patient_schema.patient_id,
        clinician_id=presc_db.clinician_id,
        clinician_role=presc_db.clinician_role,
        action_summary=f"Prescription analyzed. {len(warnings)} safety concern(s) surfaced. Priority: {stewardship_priority['tier']}.",
        payload={
            "diagnosis": presc_db.diagnosis,
            "items": [i.medication_name for i in items_schema],
            "warnings_count": len(warnings),
            "warnings_ids": [w.warning_id for w in warnings],
            "stewardship_priority_tier": stewardship_priority["tier"]
        },
        model_version=SYSTEM_VERSION,
        prompt_template_id=PROMPT_TEMPLATE_ID
    )

    # Calculate severity counts
    crit_count = sum(1 for w in warnings if w.severity == SeverityLevel.CRITICAL)
    high_count = sum(1 for w in warnings if w.severity == SeverityLevel.HIGH)
    mod_count = sum(1 for w in warnings if w.severity == SeverityLevel.MODERATE)

    return {
        "prescription_id": prescription_id,
        "patient_id": patient_schema.patient_id,
        "patient_summary": {
            "age": patient_schema.age,
            "age_category": patient_schema.age_category,
            "egfr_ml_min": patient_schema.egfr_ml_min,
            "child_pugh_class": patient_schema.child_pugh_class,
            "pregnancy_status": patient_schema.pregnancy_status,
            "allergies": patient_schema.allergies,
            "active_medications": patient_schema.active_medications
        },
        "diagnosis": presc_db.diagnosis,
        "items": [i.model_dump() for i in items_schema],
        "warnings": [w.model_dump() for w in warnings],
        "total_warnings": len(warnings),
        "critical_warnings_count": crit_count,
        "high_warnings_count": high_count,
        "moderate_warnings_count": mod_count,
        "stewardship_summary": {
            "stewardship_priority": stewardship_priority,
            "aware_breakdown": {
                it.medication_name: knowledge_base.get_aware_category(it.medication_name)
                for it in items_schema
            }
        },
        "guideline_recommendations": guidelines_list,
        "stw_workflow_condition": stw_condition,
        "stg_2022_23_condition": stg_condition,
        "retrieved_guideline_evidence": retrieved_evidence,
        # Coverage-gap resolution for drugs no clinical rule could assess.
        #
        # Computed AFTER the warnings and the stewardship rollup, from the warnings
        # themselves, and returned in its own field. Three consequences, all
        # deliberate: it cannot change which rules fired, it cannot change the
        # priority tier, and a client that does not know about this field behaves
        # exactly as it did before. The findings are external evidence attached to
        # a gap the engine already reported -- never a rule finding.
        "external_coverage_findings": coverage_findings,
        "local_amr_context": local_amr,
        "explanation": explainer_res["explanation"],
        "model_version_info": explainer_res["metadata"],
        "created_at": presc_db.created_at
    }


# ---------------------------------------------------------------------------
# Warnings & Evidence Endpoints (Sections 20, 21, 28)
# ---------------------------------------------------------------------------

@app.get("/api/prescriptions/{prescription_id}/warnings")
def get_prescription_warnings(prescription_id: str, db: Session = Depends(get_db)):
    warns = db.query(SafetyWarningDB).filter(SafetyWarningDB.prescription_id == prescription_id).all()
    results = []
    for w in warns:
        results.append({
            "warning_id": w.warning_id,
            "rule_id": w.rule_id,
            "category": w.category,
            "severity": w.severity,
            "title": w.title,
            "clinical_concern": w.clinical_concern,
            "recommendation": w.recommendation,
            "prescribed_drug": w.prescribed_drug,
            "interacting_factor": w.interacting_factor,
            "evidence": {
                "document_title": w.evidence_document,
                "guideline_version": w.evidence_version,
                "verbatim_passage": w.evidence_passage,
                "source_url": w.evidence_url
            },
            "supporting_labels": json.loads(w.supporting_labels_json) if w.supporting_labels_json else [],
            "rule_author": w.rule_author,
            "rule_approval_status": w.rule_approval_status,
            "rule_effective_date": w.rule_effective_date,
            "status": w.status
        })
    return results


@app.get("/api/warnings/{warning_id}/evidence")
def get_warning_evidence(warning_id: str, db: Session = Depends(get_db)):
    warn = db.query(SafetyWarningDB).filter(SafetyWarningDB.warning_id == warning_id).first()
    if not warn:
        raise HTTPException(status_code=404, detail="Warning not found")
    return {
        "warning_id": warn.warning_id,
        "rule_id": warn.rule_id,
        "prescribed_drug": warn.prescribed_drug,
        "document_title": warn.evidence_document,
        "guideline_version": warn.evidence_version,
        "verbatim_passage": warn.evidence_passage,
        "source_url": warn.evidence_url,
        "rule_author": warn.rule_author,
        "rule_approval_status": warn.rule_approval_status,
        "supporting_labels": json.loads(warn.supporting_labels_json) if warn.supporting_labels_json else [],
        "unverified_sources": next(
            (r.get("unverified_sources", []) for r in knowledge_base.rules_catalog
             if r.get("rule_id") == warn.rule_id), []
        ),
        "precedence_hierarchy": GUIDELINE_PRECEDENCE_HIERARCHY
    }


# ---------------------------------------------------------------------------
# Clinician Override & Server-Side Role Resolution (Sections 18, 18A, 28)
# ---------------------------------------------------------------------------

@app.post("/api/warnings/{warning_id}/override", response_model=OverrideResponse)
def override_warning(
    warning_id: str,
    payload: OverrideRequest,
    current_clinician: Dict[str, str] = Depends(get_current_clinician),
    db: Session = Depends(get_db)
):
    # Verify warning exists
    warning = db.query(SafetyWarningDB).filter(SafetyWarningDB.warning_id == warning_id).first()
    if not warning:
        raise HTTPException(status_code=404, detail="Warning not found")

    # Enforce server-side role authorization from verified session token
    authorizer.verify_override_authorization(
        clinician_role=current_clinician["clinician_role"],
        clinician_id=current_clinician["clinician_id"]
    )

    # Validate justification text
    if not payload.override_reason or len(payload.override_reason.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="A substantive clinical justification (minimum 10 characters) is required to override safety warnings."
        )

    # Record override in database, update alert metrics and append to audit log
    override = audit_logger.record_override(
        db=db,
        warning_id=warning_id,
        prescription_id=warning.prescription_id,
        clinician_id=current_clinician["clinician_id"],
        clinician_role=current_clinician["clinician_role"],
        override_reason=payload.override_reason.strip()
    )

    return OverrideResponse(
        status="CONFIRMED",
        warning_id=warning_id,
        override_id=override.override_id,
        prescription_id=warning.prescription_id,
        clinician_id=current_clinician["clinician_id"],
        clinician_role=current_clinician["clinician_role"],
        timestamp=override.timestamp,
        message="Warning successfully overridden and logged in immutable audit trail."
    )


# ---------------------------------------------------------------------------
# Rule Authoring & Management Endpoint (Sections 18A, 21)
# ---------------------------------------------------------------------------

@app.post("/api/rules")
def author_clinical_rule(
    payload: Dict[str, Any],
    current_clinician: Dict[str, str] = Depends(get_current_clinician),
    db: Session = Depends(get_db)
):
    """
    Authorized endpoint for creating/updating clinical safety rules (Spec §18A).
    Requires Infectious Disease Specialist, Clinical Pharmacist, or Attending Physician role.
    """
    authorizer.verify_rule_authoring_authorization(
        author_role=current_clinician["clinician_role"],
        author_id=current_clinician["clinician_id"]
    )

    rule_id = payload.get("rule_id")
    if not rule_id:
        raise HTTPException(status_code=400, detail="rule_id is required.")

    # Record in Rule Authorship Log
    log_entry = RuleAuthorshipLogDB(
        rule_id=rule_id,
        action=payload.get("action", "UPDATED"),
        author_id=current_clinician["clinician_id"],
        author_role=current_clinician["clinician_role"],
        approved_by=payload.get("approved_by"),
        change_summary=payload.get("change_summary", "Clinical rule authored/updated.")
    )
    db.add(log_entry)
    db.commit()

    return {
        "status": "RULE_AUTHORSHIP_RECORDED",
        "rule_id": rule_id,
        "author_id": current_clinician["clinician_id"],
        "author_role": current_clinician["clinician_role"]
    }


# ---------------------------------------------------------------------------
# Audit Trail & Alert Fatigue Endpoints (Sections 16A, 19, 28)
# ---------------------------------------------------------------------------

@app.get("/api/audit/logs")
def get_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    prescription_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(AuditLogDB)
    if prescription_id:
        query = query.filter(AuditLogDB.prescription_id == prescription_id)
    logs = query.order_by(AuditLogDB.id.desc()).limit(limit).all()
    results = []
    for l in logs:
        results.append({
            "log_id": l.log_id,
            "timestamp": l.timestamp.isoformat(),
            "event_type": l.event_type,
            "prescription_id": l.prescription_id,
            "patient_id": l.patient_id,
            "clinician_id": l.clinician_id,
            "clinician_role": l.clinician_role,
            "action_summary": l.action_summary,
            "payload": json.loads(l.payload_json),
            "prev_hash": l.prev_hash,
            "integrity_hash": l.integrity_hash,
            "model_version": l.model_version
        })
    return results


@app.get("/api/audit/verify")
def verify_audit_chain_integrity(db: Session = Depends(get_db)):
    """Walk and cryptographically verify the SHA-256 hash chain from genesis to head."""
    verification = audit_logger.verify_chain_integrity(db)
    return verification


@app.get("/api/audit/alert-fatigue")
def get_alert_fatigue_metrics(db: Session = Depends(get_db)):
    return audit_logger.get_alert_fatigue_report(db)


# ---------------------------------------------------------------------------
# Guidelines & Knowledge Base Endpoints (Sections 7, 8, 8A, 13)
# ---------------------------------------------------------------------------

@app.get("/api/guidelines/rules")
def list_clinical_rules():
    catalog_version = getattr(knowledge_base, "rules_catalog_metadata", {}).get("catalog_version", "UNKNOWN")
    return {
        "catalog_version": catalog_version,
        "total_rules": len(knowledge_base.rules_catalog),
        "rules": knowledge_base.rules_catalog
    }


# ---------------------------------------------------------------------------
# Patient feedback (Section 30 - post-prescription follow-up)
#
# SCOPE OF THIS SLICE, STATED PLAINLY: a patient opens the page with a per-visit
# code, sees that visit's medications, answers three questions, and the answers
# reach the clinician as an in-app notification and a stored record.
#
# What it deliberately does NOT do yet:
#   - ask periodically. There is no scheduling here. The patient answers when they
#     open the link, once per submission, and nothing prompts them again.
#   - escalate. An answer of "worse" is stored and notified like any other. It does
#     not page anyone, and the page tells the patient so in as many words.
# Both are real work and neither is stubbed out pretending to exist.
# ---------------------------------------------------------------------------

# Digits and letters that cannot be misread aloud or in handwriting: no O/0, I/1,
# S/5. The code is read out or written on a discharge slip, so an ambiguous glyph
# is a support call.
# How long a patient must wait before sending a SECOND update for the same visit.
#
# Not a delay on the clinician's notification -- that is immediate. This exists so
# a follow-up is a considered answer rather than a stream: a patient refreshing
# the page and sending "worse" four times in an hour produces four alerts about
# one deterioration, and the fourth is the one a clinician stops reading.
#
# Scoped to the visit, so a patient with two open visits can report on each.
FEEDBACK_RESUBMIT_COOLDOWN_HOURS = 24

def _as_utc(value: datetime) -> datetime:
    """
    A stored timestamp as an aware UTC datetime.

    SQLite hands back naive datetimes, and comparing a naive value to an aware
    `now` raises TypeError -- which in a cooldown check would mean the refusal
    never fires and the limit silently does not exist.
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


_FEEDBACK_ALPHABET = "ABCDEFGHJKLMNPQRTUVWXY2346789"


def _new_feedback_code(db: Session) -> str:
    """A short per-visit code, checked for collision against existing visits."""
    import secrets

    for _ in range(12):
        code = "".join(secrets.choice(_FEEDBACK_ALPHABET) for _ in range(8))
        if not db.query(VisitDB).filter(VisitDB.feedback_code == code).first():
            return code
    # 29^8 is ~5e11; twelve collisions means something is wrong with the RNG, and
    # returning a duplicate would let one patient open another's visit.
    raise HTTPException(status_code=500, detail="Could not allocate a feedback code.")


def _visit_for_code(db: Session, code: str) -> VisitDB:
    """
    The one visit a code opens, or 404.

    A blank or missing code must never match. Visits recorded before this feature
    have feedback_code NULL, and a query for "" would otherwise return one of them.
    """
    cleaned = (code or "").strip().upper()
    if len(cleaned) < 6:
        raise HTTPException(status_code=404, detail="That code was not recognised.")
    visit = db.query(VisitDB).filter(VisitDB.feedback_code == cleaned).first()
    if not visit:
        # Deliberately the same message as a malformed code: distinguishing "no such
        # code" from "code exists but is not yours" tells a guesser which is which.
        raise HTTPException(status_code=404, detail="That code was not recognised.")
    return visit


@app.get("/api/feedback/unseen")
def list_unseen_feedback(
    db: Session = Depends(get_db),
    current_clinician: Dict[str, str] = Depends(get_current_clinician),
):
    """
    Answers no clinician has opened yet. Drives the alert shown after login.

    Declared BEFORE /api/feedback/{code}: FastAPI matches in declaration order, and
    with the parameterised route first "unseen" would be read as a visit code and
    answer 404.
    """
    # Unseen BY THIS CLINICIAN. A shared "seen" flag let whichever clinician logged
    # in first clear an answer for all five of them -- so a pharmacist dismissing a
    # popup could hide it from the attending physician who owned the patient.
    clinician_id = current_clinician.get("clinician_id") or current_clinician.get("doctor_id") or ""
    acknowledged = (db.query(FeedbackAcknowledgementDB.response_id)
                    .filter(FeedbackAcknowledgementDB.clinician_id == clinician_id))

    # NO DELAY HERE, deliberately. An answer reaches the clinician as soon as the
    # patient sends it: a patient reporting that they feel worse is the one signal
    # in this system that should never wait. The 24 hours applies to how often a
    # patient may SEND, not to how quickly a clinician is told -- see
    # submit_feedback.
    rows = (db.query(FeedbackResponseDB)
            .filter(~FeedbackResponseDB.response_id.in_(acknowledged))
            .order_by(FeedbackResponseDB.submitted_at.desc())
            .limit(25).all())
    names = {p.patient_id: p.display_name for p in db.query(PatientDB).all()}
    return {
        "unseen": len(rows),
        "responses": [{
            "response_id": r.response_id,
            "visit_id": r.visit_id,
            "patient_id": r.patient_id,
            "patient_name": names.get(r.patient_id) or r.patient_id,
            "feeling": r.feeling,
            "medicines_helped": r.medicines_helped,
            # Adherence travels with the answer. An unreported "STOPPED" is the
            # single most actionable thing this form collects, and a field that is
            # stored but never serialised is a question asked for nothing.
            "doses_taken": r.doses_taken,
            "discomfort": r.discomfort,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        } for r in rows],
    }


@app.get("/api/feedback/{code}")
def get_feedback_context(code: str, db: Session = Depends(get_db)):
    """
    What the patient is shown before answering: their own medications for THIS visit.

    Scoped hard to the one visit the code opens. No allergies, no renal function, no
    other visit, no clinical notes -- a patient confirming how their treatment is
    going does not need their full record, and a public endpoint should hand back
    the minimum that makes the question answerable.
    """
    visit = _visit_for_code(db, code)
    # Whether an update can be sent now. Reported on open so the form can say so
    # up front instead of accepting answers it is going to refuse.
    _last = (db.query(FeedbackResponseDB)
             .filter(FeedbackResponseDB.visit_id == visit.visit_id)
             .order_by(FeedbackResponseDB.submitted_at.desc())
             .first())
    _can_submit, _next_at = True, None
    if _last and _last.submitted_at:
        _due = _as_utc(_last.submitted_at) + timedelta(hours=FEEDBACK_RESUBMIT_COOLDOWN_HOURS)
        if _due > datetime.now(timezone.utc):
            _can_submit, _next_at = False, _due.isoformat()
    patient = db.query(PatientDB).filter(PatientDB.patient_id == visit.patient_id).first()

    medications: List[Dict[str, Any]] = []
    if visit.prescription_id:
        items = db.query(PrescriptionItemDB).filter(
            PrescriptionItemDB.prescription_id == visit.prescription_id
        ).all()
        medications = [{
            "medication_name": i.medication_name,
            "dose": i.dose,
            "unit": i.unit,
            "route": i.route,
            "frequency": i.frequency,
            "duration_days": i.duration_days,
        } for i in items]

    already = db.query(FeedbackResponseDB).filter(
        FeedbackResponseDB.visit_id == visit.visit_id
    ).count()

    return {
        "can_submit": _can_submit,
        "next_submission_allowed_at": _next_at,
        "resubmit_cooldown_hours": FEEDBACK_RESUBMIT_COOLDOWN_HOURS,
        "visit_id": visit.visit_id,
        "patient_name": (patient.display_name if patient else None) or visit.patient_id,
        "diagnosis": visit.diagnosis,
        "visit_date": visit.visit_date.isoformat() if visit.visit_date else None,
        "medications": medications,
        "previous_responses": already,
        "not_for_emergencies": (
            "This form is read by your clinician during working hours. It is not "
            "monitored continuously. If you feel seriously unwell, contact your "
            "doctor or emergency services directly."
        ),
    }


@app.post("/api/feedback/{code}")
def submit_feedback(code: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Store the patient's answers and raise an in-app notification for the clinician."""
    import uuid

    visit = _visit_for_code(db, code)
    patient = db.query(PatientDB).filter(PatientDB.patient_id == visit.patient_id).first()

    # ONE UPDATE PER VISIT PER COOLDOWN. Checked before anything is validated, so a
    # patient inside the window is told plainly rather than filling the form in and
    # being refused at the end.
    last = (db.query(FeedbackResponseDB)
            .filter(FeedbackResponseDB.visit_id == visit.visit_id)
            .order_by(FeedbackResponseDB.submitted_at.desc())
            .first())
    if last and last.submitted_at:
        next_allowed = last.submitted_at + timedelta(hours=FEEDBACK_RESUBMIT_COOLDOWN_HOURS)
        if _as_utc(last.submitted_at) > datetime.now(timezone.utc) - timedelta(
                hours=FEEDBACK_RESUBMIT_COOLDOWN_HOURS):
            raise HTTPException(
                status_code=429,
                detail=(
                    "Thank you - your clinician already has your update from this visit. "
                    "You can send another after "
                    f"{next_allowed.strftime('%d %b, %I:%M %p')}. If something feels "
                    "seriously wrong before then, contact your clinician or emergency "
                    "services directly rather than waiting."
                ),
            )

    feeling = str(payload.get("feeling") or "").strip().upper()
    helped = str(payload.get("medicines_helped") or "").strip().upper()
    discomfort = str(payload.get("discomfort") or "").strip()

    # ADHERENCE. Central to this system's own subject: a course not completed is a
    # principal driver of resistance, and it is invisible to every other signal the
    # system holds -- the prescription says what was ordered, never what was taken.
    # Optional on purpose: a patient who will not answer it must still be able to
    # report that they feel worse.
    doses = str(payload.get("doses_taken") or "").strip().upper() or None
    if doses and doses not in {"ALL", "MOST", "SOME", "STOPPED"}:
        doses = None

    if feeling not in {"BETTER", "SAME", "WORSE"}:
        raise HTTPException(status_code=400, detail="Please answer how you are feeling.")
    if helped not in {"YES", "NO", "UNSURE"}:
        raise HTTPException(status_code=400, detail="Please answer whether the medicines helped.")

    response = FeedbackResponseDB(
        response_id=f"FB-{uuid.uuid4().hex[:10].upper()}",
        visit_id=visit.visit_id,
        patient_id=visit.patient_id,
        doctor_id=visit.doctor_id,
        feeling=feeling,
        medicines_helped=helped,
        doses_taken=doses,
        # Stored exactly as written. A patient's own words about their symptoms are
        # not something this system should tidy.
        discomfort=discomfort[:2000] or None,
    )
    db.add(response)

    name = (patient.display_name if patient else None) or visit.patient_id
    headline = {"BETTER": "reports feeling better",
                "SAME": "reports no change",
                "WORSE": "REPORTS FEELING WORSE"}[feeling]
    db.add(NotificationDB(
        notification_id=f"NOTIF-{uuid.uuid4().hex[:10].upper()}",
        patient_id=visit.patient_id,
        doctor_id=visit.doctor_id,
        kind="PATIENT_FEEDBACK",
        channel="IN_APP",
        recipient_type="DOCTOR",
        title=f"{name} {headline}",
        message=(
            f"Visit {visit.visit_id} ({visit.diagnosis or 'no diagnosis recorded'}). "
            f"Feeling: {feeling}. Medicines helped: {helped}."
            + (f" Reported: {discomfort[:300]}" if discomfort else " No discomfort described.")
        ),
        # IN_APP is the one channel that is real without configuration, and this row
        # IS the delivery -- it is readable the moment it is written.
        status="DELIVERED",
        detail="Patient feedback recorded and queued for clinician review.",
    ))
    db.commit()

    return {
        "recorded": True,
        "response_id": response.response_id,
        "message": "Thank you. Your answers have been sent to your clinician.",
    }


@app.post("/api/feedback/{response_id}/seen")
def mark_feedback_seen(
    response_id: str,
    db: Session = Depends(get_db),
    current_clinician: Dict[str, str] = Depends(get_current_clinician),
):
    """
    Acknowledge one answer so it stops appearing in the post-login alert.

    Marking it seen is NOT marking it handled. The answer stays in the record and
    in the patient's own history; this only stops it announcing itself.
    """
    row = db.query(FeedbackResponseDB).filter(
        FeedbackResponseDB.response_id == response_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="No such feedback response.")

    clinician_id = current_clinician.get("clinician_id") or current_clinician.get("doctor_id") or ""
    existing = db.query(FeedbackAcknowledgementDB).filter(
        FeedbackAcknowledgementDB.response_id == response_id,
        FeedbackAcknowledgementDB.clinician_id == clinician_id,
    ).first()
    if not existing:
        db.add(FeedbackAcknowledgementDB(response_id=response_id, clinician_id=clinician_id))
        db.commit()
    # Acknowledging is per clinician and says nothing about the other four. The
    # answer itself is untouched: it stays in the record and on the patient's page.
    return {"response_id": response_id, "seen_by": clinician_id, "seen": True}


@app.get("/api/feedback")
def list_feedback_responses(
    patient_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_clinician: Dict[str, str] = Depends(get_current_clinician),
):
    """
    Every patient answer, newest first. Clinician-only.

    The submit endpoint is public because the patient has no login; READING the
    answers is not, because the reader is a clinician looking at other people's
    records.
    """
    query = db.query(FeedbackResponseDB)
    if patient_id:
        query = query.filter(FeedbackResponseDB.patient_id == patient_id)
    rows = query.order_by(FeedbackResponseDB.submitted_at.desc()).limit(200).all()

    names = {p.patient_id: p.display_name for p in db.query(PatientDB).all()}
    return {
        "total": len(rows),
        "responses": [{
            "response_id": r.response_id,
            "visit_id": r.visit_id,
            "patient_id": r.patient_id,
            "patient_name": names.get(r.patient_id) or r.patient_id,
            "doctor_id": r.doctor_id,
            "feeling": r.feeling,
            "medicines_helped": r.medicines_helped,
            # Adherence travels with the answer. An unreported "STOPPED" is the
            # single most actionable thing this form collects, and a field that is
            # stored but never serialised is a question asked for nothing.
            "doses_taken": r.doses_taken,
            "discomfort": r.discomfort,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        } for r in rows],
    }


@app.get("/api/guidelines/documents")
def list_ingested_documents(domain: Optional[str] = None):
    """
    The documents this system actually holds, optionally filtered by clinical domain.

    The corpus summary on /api/system/health reports HOW MANY documents sit in each
    domain and never reported WHICH, so a reader could see that 14 research-ethics
    documents were held and had no way to find out what they were. Counts without a
    listing also make the corpus unauditable: "94 documents" is a claim nobody
    outside this process could check.

    Every field returned is read from the ingested corpus. Nothing is restated from
    memory, and each document carries the provenance it was ingested with -- source
    type, provenance basis, and the page-reference kind that governs whether its
    page numbers are real pages of a real edition.
    """
    from backend.rag.store import (
        DOMAIN_ANTIMICROBIAL,
        DOMAIN_READING_CONTRACT,
        NOT_A_CLINICAL_GUIDELINE_RANK,
        vector_store,
    )
    from backend.config import ANTIMICROBIAL_CONTENT_DOCUMENT_IDS

    import re as _re

    # Headings that describe the publication rather than its subject. A coverage
    # list made of "CONTENTS", "Foreword" and the document's own title tells a
    # reader nothing about what the document is for.
    _NOISE = _re.compile(
        r"^(contents|table of contents|index|foreword|preface|message|disclaimer|"
        r"acknowledgements?|abbreviations?|references?|annexures?.*|appendix.*|"
        r"list of experts|indian council of medical research|consensus document.*|"
        r"guidelines? for.*|dhr-icmr|ministry of health.*|national guidelines?.*|"
        r"world health organization)$",
        _re.I,
    )

    # Front matter and tables of contents. A "what this says" excerpt drawn from the
    # publisher block or the contents page says nothing about the subject.
    _FRONT = _re.compile(
        r"(designed & printed|printed at m/s|published by|all rights reserved|isbn|"
        r"production controller|compiled & edited|ansari nagar|^disclaimer|"
        r"^foreword|^preface|^message\b|^acknowledgement)", _re.I,
    )
    # A contents page is mostly headings and page numbers.
    _TOC = _re.compile(r"(foreword\s+i+\b|contents\s+foreword|\.{4,}|\s\d+\s+\d+\s+\d+\s)", _re.I)
    # ...but a contents page without dot leaders interleaves its numbers with the
    # headings -- "Procedures after the consent process 54 5.10 Special situations 55
    # 5.11 Consent for studies using deception 55" -- which no fixed pattern catches.
    # Standalone-number density does: prose cites few bare numbers, a contents page is
    # built from them.
    _BARE_NUMBER = _re.compile(r"(?<![\w.])\d{1,3}(?![\w.%])")

    chunk_counts: Dict[str, int] = {}
    sections: Dict[str, List[str]] = {}
    # doc_id -> heading -> (page, verbatim excerpt)
    topic_text: Dict[str, Dict[str, tuple]] = {}
    # doc_id -> [(page, excerpt)] for documents whose headings were never detected.
    #
    # The heading matcher in backend.rag.ingest fires on numbered or mostly-uppercase
    # lines, and eight of the 54 condition-specific documents have none it recognises
    # -- the type 1 diabetes guideline has 604 chunks and zero detected sections, and
    # the neonatal jaundice guideline 71 chunks and zero. Anchoring every excerpt to a
    # heading therefore left those documents showing nothing at all, and because the
    # list sorts by title the blank ones landed at the top.
    #
    # A document with no headings still has an opening. Quoting it is no weaker a
    # claim than quoting a passage that happens to sit under a heading.
    opening_text: Dict[str, List[tuple]] = {}
    seen_per_doc: Dict[str, int] = {}
    for chunk in vector_store.chunks:
        doc_id = chunk.get("document_id")
        chunk_counts[doc_id] = chunk_counts.get(doc_id, 0) + 1
        seen_per_doc[doc_id] = seen_per_doc.get(doc_id, 0) + 1

        # What the document covers, taken from its OWN section headings as captured
        # at ingestion. The provenance note says how a citation from the document
        # must be treated; it deliberately says almost nothing about the subject
        # matter, and for the 22 oncology consensus documents it is near-identical
        # boilerplate, so the panel showing only that note could not distinguish the
        # gallbladder document from the retinoblastoma one.
        #
        # This is a list of headings DETECTED, not a table of contents: the heading
        # matcher in backend.rag.ingest is deliberately conservative and misses many,
        # so the field is labelled as detected and never presented as complete.
        raw = (chunk.get("section") or "").strip()
        heading_ok = bool(raw) and 6 <= len(raw) <= 70
        # Collect an opening passage for documents that will end up with no headed
        # topic at all. Bounded to the first 60 chunks so this stays cheap on a
        # 600-chunk document; front matter is rejected by the quality gates anyway.
        want_opening = (
            len(opening_text.get(doc_id, [])) < 3 and seen_per_doc[doc_id] <= 60
        )
        if not heading_ok and not want_opening:
            continue
        flat = _re.sub(r"\s+", " ", raw) if heading_ok else ""
        # Drop the residue of PDF extraction damage. Matching the literal U+FFFD is
        # not enough: the same damage also arrives as other unmapped codepoints, so
        # anything outside ordinary heading punctuation is stripped by class.
        if heading_ok:
            flat = _re.sub(r"[^\w\s()/&,'.\-]", "", flat, flags=_re.UNICODE).strip(" :.-")
            flat = _re.sub(r"^\d+(?:\.\d+)*\s+", "", flat)
            if (_NOISE.match(flat.lower()) or not _re.search(r"[A-Za-z]{4,}", flat)
                    or len(flat) < 5):
                heading_ok, flat = False, ""
        if heading_ok:
            bucket = sections.setdefault(doc_id, [])
            if flat not in bucket:
                bucket.append(flat)
        elif not want_opening:
            continue

        # WHAT THE SECTION ACTUALLY SAYS, verbatim from the document.
        #
        # A heading tells a reader the topic exists. It does not tell them what the
        # document says about it, which is the only thing that distinguishes this
        # guideline from the next one with the same chapter names. The first
        # substantive passage under each heading is kept, and nothing is summarised
        # or paraphrased: the text below is the document's own, cut at a sentence
        # boundary.
        store = topic_text.setdefault(doc_id, {})
        if heading_ok and flat in store:
            continue
        body = " ".join((chunk.get("text") or "").split())
        if len(body) < 220 or _FRONT.search(body[:200]) or _TOC.search(body[:400]):
            continue

        # Prose only. Reporting forms, flowcharts and staging tables extract as runs
        # of dots, blank fields and isolated abbreviations -- the cervix document's
        # cone-biopsy reporting form yields "Dimensions ...x... x...mm Resection
        # margins : Number of sections studied :". That is faithfully what the page
        # holds and it tells a reader nothing, so it is skipped rather than quoted.
        letters = sum(ch.isalpha() or ch.isspace() for ch in body)
        if letters / len(body) < 0.82:
            continue
        if _re.search(r"\.{3,}|_{3,}|(?:\s[:;]\s){3,}", body):
            continue
        # One bare number per ~45 characters of prose is already generous; a contents
        # page runs far denser.
        if len(_BARE_NUMBER.findall(body[:460])) > 10:
            continue
        # Reference lists survive every check above -- they are prose-dense, carry few
        # short bare numbers because their numbers are years and page ranges, and read
        # as "7. ICCN India 2005. Guidelines for Head & Neck Cancers 8. Head and Neck
        # Guidelines. Downloaded from ... 9. ESMO Minimum Clinical Recommendations".
        # A bibliography is not what the document says about its subject.
        if "http" in body.lower() or len(_re.findall(r"\b\d{1,2}\.\s+[A-Z]", body[:460])) >= 3:
            continue
        # Strip the running header PDFs repeat at the top of every page, the
        # chapter/section furniture, and the heading itself, so the excerpt opens on
        # the substance rather than on navigation.
        doc_title = (vector_store.docs.get(doc_id, {}) or {}).get("title") or ""

        # Invisible formatting residue first, so it cannot break the pattern matches
        # below. U+00AD is a soft hyphen the encoder left behind; U+FFFD is an
        # unmapped glyph. An en dash (U+2013) is NOT damage and is left alone -- it is
        # the document's own punctuation in ranges like "90 - 95%".
        body = body.replace("­", "").replace("�", "")
        # Bullet glyphs the encoder rendered as stray "z" characters.
        body = _re.sub(r"(?:\bz\s+){2,}", "• ", body)

        # Running headers repeat the title on every page and reappear mid-chunk, in
        # wording that drifts from the recorded title ("Consensus Document for the
        # Management of Cancer Cervix" against a title of "...for Management of..."),
        # so they are matched loosely on the distinctive words rather than exactly.
        #
        # This runs BEFORE the furniture loop, not after: removing a leading running
        # header exposes the chapter marker behind it, and a loop that has already
        # finished cannot strip what the removal just revealed. That ordering left
        # "CHAPTER9 APPENDIX Appendix - A BIOMARKERS..." as an excerpt opening.
        title_words = [w for w in _re.findall(r"[A-Za-z]{4,}", doc_title)
                       if w.lower() not in {"document", "guidelines", "guideline", "for", "the"}]
        if len(title_words) >= 2:
            loose = r"\b" + r"\W+(?:\w+\W+){0,3}?".join(_re.escape(w) for w in title_words[:5]) + r"\b"
            body = _re.sub(loose, "", body, flags=_re.I)
            body = _re.sub(r"\s{2,}", " ", body).strip(" -–—:.")

        # Page furniture, applied until the text stops changing. Order alone is not
        # enough: "ICMR Guidelines ... 2018  1  SECTION 1 INTRODUCTION 1.1 Definition"
        # needs the page number removed before the SECTION pattern can match, and the
        # heading removed after both.
        furniture = [
            # The operator-attested 2022-23 chapters mark headings with "#", so their
            # passages open "#CLASSIFICATION Based on the duration of illness". Left
            # in place, the capital-letter check below rejected every chunk of the
            # bone and joint infection chapter and it showed nothing at all.
            r"^\s*#+\s*",
            r"^\s*(APPENDIX|ANNEXURE)\s*[-–—]?\s*[A-Z0-9]?\s*",
            r"^\s*" + _re.escape(doc_title[:60]) + r"\s*",
            r"^\s*(CHAPTER|SECTION)\s*\d*\s*",
            r"^\s*\d{1,4}(?:\.\d+)*\s+",
            r"^\s*[ivxlc]{1,5}\s+(?=[A-Z])",
            r"^\s*" + _re.escape(flat) + r"\s*",
            r"^\s*" + _re.escape(raw) + r"\s*",
        ]
        for _ in range(6):
            before = body
            for pattern in furniture:
                body = _re.sub(pattern, "", body, flags=_re.I)
            body = body.strip()
            if body == before:
                break

        # A chunk that begins mid-word or mid-sentence makes a poor opening quote:
        # the reader is dropped into the middle of something. Skip rather than
        # present it as though it were the start of a statement.
        if not body[:1].isupper() and not body[:1].isdigit():
            continue
        if len(body) < 180:
            continue
        cut = body[:460]
        if len(body) > 460:
            stop = max(cut.rfind(". "), cut.rfind("; "))
            cut = cut[: stop + 1] if stop > 220 else cut.rsplit(" ", 1)[0]
            # Trailing punctuation first: a cut ending on a full stop plus an appended
            # ellipsis reads as "India...." and looks like dot leaders.
            cut = cut.rstrip(" .;") + "..."
        cut = cut.strip()
        # Re-checked after trimming: the gate above judged the whole chunk, and the
        # first 460 characters of a mostly-prose chunk can still be its table.
        if sum(ch.isalpha() or ch.isspace() for ch in cut) / max(len(cut), 1) < 0.82:
            continue
        if heading_ok:
            store[flat] = (chunk.get("page"), cut)
        else:
            opening_text.setdefault(doc_id, []).append((chunk.get("page"), cut))

    out: List[Dict[str, Any]] = []
    for doc_id, d in vector_store.docs.items():
        doc_domain = d.get("clinical_domain", DOMAIN_ANTIMICROBIAL)
        if domain and doc_domain != domain:
            continue
        rank = d.get("precedence_rank")
        out.append({
            "document_id": doc_id,
            "title": d.get("title"),
            "issuing_org": d.get("issuing_org"),
            "version": d.get("version"),
            "publication_date": d.get("publication_date"),
            "geographic_scope": d.get("geographic_scope"),
            "source_url": d.get("source_url"),
            "clinical_domain": doc_domain,
            "precedence_rank": rank,
            "is_clinical_guideline": rank != NOT_A_CLINICAL_GUIDELINE_RANK,
            "carries_antimicrobial_authority": (
                doc_domain == DOMAIN_ANTIMICROBIAL and rank != NOT_A_CLINICAL_GUIDELINE_RANK
            ),
            # Distinct from authority: a condition-specific guideline can name
            # antibacterial regimens for its own condition without being an
            # antimicrobial guideline. See config.ANTIMICROBIAL_CONTENT_DOCUMENT_IDS.
            "carries_antimicrobial_content": doc_id in ANTIMICROBIAL_CONTENT_DOCUMENT_IDS,
            "domain_caveat": DOMAIN_READING_CONTRACT.get(doc_domain),
            "source_type": d.get("source_type", "OFFICIAL_PDF"),
            "provenance_basis": d.get("provenance_basis", "HASH_VERIFIED_PDF"),
            "page_reference_kind": d.get("page_reference_kind", "OFFICIAL_DOCUMENT_PAGE"),
            "page_count": d.get("page_count"),
            "chunks": chunk_counts.get(doc_id, 0),
            "file_sha256": d.get("file_sha256"),
            "provenance_note": d.get("notes") or None,
            # What the document says, by topic, in its own words. Capped because
            # this is an orientation aid: the type 2 diabetes guideline alone yields
            # 37 headings and a card is not a reader.
            "topics": [
                {"heading": heading, "page": page, "excerpt": excerpt}
                for heading, (page, excerpt) in list(topic_text.get(doc_id, {}).items())[:8]
            ] or [
                # No heading was detected anywhere in this document, so there is
                # nothing to label the passage with. The heading is left empty rather
                # than invented, and the excerpt is still the document's own text.
                {"heading": "", "page": page, "excerpt": excerpt}
                for page, excerpt in opening_text.get(doc_id, [])[:2]
            ],
        })

    # Precedence first, then title, so the ordering a reader sees is the documented
    # hierarchy rather than dictionary order.
    out.sort(key=lambda x: (x["precedence_rank"] or 99, (x["title"] or "").lower()))
    return {
        "total_documents": len(vector_store.docs),
        "returned": len(out),
        "domain_filter": domain,
        "documents": out,
    }


@app.get("/api/guidelines/amr-data")
def get_amr_surveillance_data(drug: Optional[str] = None):
    records = knowledge_base.get_local_amr_records(drug)
    distinct_isolates = knowledge_base.amr_data.get("sample_size_total_isolates", 0)
    total_tests = sum(r.get("sample_size", 0) for r in knowledge_base.amr_data.get("antibiogram", []))
    return {
        "source": knowledge_base.amr_data.get("dataset_title", "ICMR Antimicrobial Resistance Surveillance Network Annual Report"),
        "geographic_scope": knowledge_base.amr_data.get("geographic_scope", "National (India - ICMR Network)"),
        "total_distinct_isolates": distinct_isolates,
        "per_antimicrobial_test_count_sum": total_tests,
        "sample_size_note": knowledge_base.amr_data.get("sample_size_note"),
        "records_count": len(records),
        "records": records
    }


@app.get("/api/guidelines/cross-source")
def compare_guideline_sources(topic: str = Query("", max_length=200)):
    """
    Lay every ingested document's guidance on a topic side by side (Spec 8A).

    Reports what each source says and which antimicrobials each names, ordered by
    the precedence hierarchy. It does NOT assert that sources clinically conflict:
    differences in named agents are computed from the retrieved wording, and the
    clinical reading is left to the clinician. Curated, already-reviewed conflicts
    are returned separately and labelled as such.
    """
    from backend.rag.store import vector_store

    return compare_sources(topic, knowledge_base, vector_store)


@app.get("/api/rules/governance")
def get_rule_governance(db: Session = Depends(get_db)):
    """Catalog rules with their review state derived from the append-only log."""
    return rule_governance.governance_report(db, knowledge_base.rules_catalog)


@app.get("/api/rules/{rule_id}/history")
def get_rule_review_history(rule_id: str, db: Session = Depends(get_db)):
    if not knowledge_base.get_rule_by_id(rule_id):
        raise HTTPException(status_code=404, detail=f"Unknown rule '{rule_id}'.")
    return {"rule_id": rule_id, "history": rule_governance.review_history(db, rule_id)}


@app.post("/api/rules/{rule_id}/review")
def review_clinical_rule(
    rule_id: str,
    payload: Dict[str, Any],
    current_clinician: Dict[str, str] = Depends(get_current_clinician),
    db: Session = Depends(get_db),
):
    """
    Record a clinician's review decision on a catalog rule.

    Authorization reuses the rule-authoring roles, so the same people who may
    author a rule may sign one off. The decision is appended to the authorship log
    AND written into the immutable audit chain, because "who approved this rule,
    when, and on what grounds" is exactly the kind of question the chain exists to
    answer defensibly.

    The catalog file is never edited, and approving a rule does not change how it
    evaluates: every rule fires identically before and after review.
    """
    authorizer.verify_rule_authoring_authorization(
        author_role=current_clinician["clinician_role"],
        author_id=current_clinician["clinician_id"],
    )

    rule = knowledge_base.get_rule_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Unknown rule '{rule_id}'.")

    action = str((payload or {}).get("action", "")).strip().upper()
    if action not in rule_governance.REVIEW_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"action must be one of: {', '.join(rule_governance.REVIEW_ACTIONS)}",
        )

    rationale = str((payload or {}).get("rationale", "")).strip()
    if len(rationale) < 10:
        # A signature without a reason is not governance.
        raise HTTPException(
            status_code=400,
            detail="A clinical rationale of at least 10 characters is required to record a review.",
        )

    entry = rule_governance.record_review(
        db=db,
        rule_id=rule_id,
        action=action,
        rationale=rationale,
        reviewer_id=current_clinician["clinician_id"],
        reviewer_role=current_clinician["clinician_role"],
    )

    audit_logger.log_event(
        db=db,
        event_type="RULE_REVIEWED",
        prescription_id="N/A",
        patient_id="N/A",
        clinician_id=current_clinician["clinician_id"],
        clinician_role=current_clinician["clinician_role"],
        action_summary=f"Rule {rule_id} reviewed: {action}.",
        payload={
            "rule_id": rule_id,
            "action": action,
            "rationale": rationale,
            "rule_severity": rule.get("severity"),
            "rule_category": rule.get("category"),
            "catalog_status_at_review": rule.get("approval_status"),
        },
    )

    return {
        "status": "RULE_REVIEW_RECORDED",
        "rule_id": rule_id,
        "action": action,
        "reviewed_by": current_clinician["clinician_id"],
        "reviewer_role": current_clinician["clinician_role"],
        "reviewed_at": entry.timestamp.isoformat() if entry.timestamp else None,
        "note": "Recorded against the catalog, which is unchanged. Rule evaluation is unaffected.",
    }


@app.get("/api/guidelines/precedence")
def get_guideline_precedence(syndrome: str = "uncomplicated_urinary_tract_infection"):
    return knowledge_base.resolve_guideline_precedence(syndrome)


@app.get("/api/guidelines/stg-conditions")
def list_stg_conditions(condition: Optional[str] = None, diagnosis: Optional[str] = None):
    """
    Browse the syndrome index of the ICMR Treatment Guidelines 2022-23 edition.

    Every response carries the authority document record and the provenance block, so
    a caller cannot render the clinical content without the attribution that qualifies
    it: that the edition claim rests on operator attestation, that no official 2022-23
    PDF is held, and that any page shown belongs to the prior (2019) edition.
    """
    collection = knowledge_base.stg_syndromes
    auth_id = collection.get("authority_document_id")
    envelope = {
        "collection_id": collection.get("collection_id"),
        "collection_title": collection.get("collection_title"),
        "authority_document_id": auth_id,
        "authority_document": collection.get("documents", {}).get(auth_id),
        "prior_edition_document_id": collection.get("prior_edition_document_id"),
        "provenance_note": collection.get("provenance_note"),
        "transcription_note": collection.get("transcription_note"),
        "verification_note": collection.get("verification_note"),
    }

    if condition:
        record = knowledge_base.get_stg_condition(condition)
        if not record:
            raise HTTPException(status_code=404, detail=f"Unknown ICMR 2022-23 condition '{condition}'.")
        return {**envelope, "condition": record}

    if diagnosis:
        match = knowledge_base.match_stg_condition(diagnosis)
        return {**envelope, "query": diagnosis, "matched": bool(match), "condition": match}

    index = knowledge_base.list_stg_conditions()
    return {
        **envelope,
        "transcription_sources": collection.get("transcription_sources", {}),
        "total_conditions": len(index),
        "conditions": index,
    }


@app.get("/api/guidelines/stw-conditions")
def list_stw_conditions(condition: Optional[str] = None, diagnosis: Optional[str] = None):
    """
    Browse the ICMR Standard Treatment Workflows (2022) conditions.

    `condition` fetches one by key, `diagnosis` runs the same deterministic
    matcher the analysis pipeline uses. The collection's provenance block is
    always returned so the caller cannot present this content as the ICMR
    antimicrobial treatment guidelines.
    """
    collection = knowledge_base.stw_collection
    envelope = {
        "collection_id": collection.get("collection_id"),
        "collection_title": collection.get("collection_title"),
        "provenance_note": collection.get("provenance_note"),
        "verbatim_normalization": collection.get("verbatim_normalization"),
        "documents": collection.get("documents", {}),
    }

    if condition:
        record = knowledge_base.get_stw_condition(condition)
        if not record:
            raise HTTPException(status_code=404, detail=f"Unknown STW condition '{condition}'.")
        return {**envelope, "condition": record}

    if diagnosis:
        match = knowledge_base.match_stw_condition(diagnosis)
        return {**envelope, "query": diagnosis, "matched": bool(match), "condition": match}

    index = knowledge_base.list_stw_conditions()
    return {
        **envelope,
        "shared_regimens": collection.get("shared_regimens", {}),
        "total_conditions": len(index),
        "conditions": index,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Ask the Evidence (Spec §20)
# ---------------------------------------------------------------------------

@app.post("/api/evidence/ask")
def ask_the_evidence(payload: Dict[str, Any]):
    """
    Answer questions ABOUT the ingested guideline corpus.

    Strictly extractive: the response is assembled from retrieved verbatim
    passages with citations. No language model is involved, so the endpoint
    cannot assert a claim absent from a held document. Refuses on prompt
    injection, personal medical advice, unknown entities, and low relevance.
    """
    from backend.rag.ask import ask as _ask

    question = payload.get("question", "")
    k = int(payload.get("k", 4) or 4)
    result = _ask(question, k=max(1, min(k, 10)))
    return result.to_dict()


# ---------------------------------------------------------------------------
# Agentic evidence layer (Spec §20, §23)
#
# Separate endpoints from /api/evidence/ask on purpose. That endpoint's guarantee
# is that no model is involved, and it must keep that guarantee exactly - a caller
# relying on it should never receive a composed answer because a flag was set
# somewhere. Two endpoints, two contracts, no flag that quietly changes which one
# you are talking to.
# ---------------------------------------------------------------------------

@app.get("/api/agents/status")
def agent_layer_status():
    """What is actually configured, so the UI states it rather than assuming it."""
    from backend.agents.pipeline import status as _status

    return _status()


@app.get("/api/agents/graph")
def agent_pipeline_graphs():
    """
    The declared nodes and edges of both pipelines.

    Served from the backend rather than drawn in the frontend so the diagram
    cannot drift from the code. A flow chart maintained separately keeps showing a
    step after it is removed, and a reader trusts a picture more than prose -- so a
    stale one misleads harder than no picture at all. Every run returns a trace
    keyed by these same node ids.
    """
    from backend.agents.trace import graphs

    return graphs()


@app.post("/api/agents/ask")
def ask_through_agents(payload: Dict[str, Any]):
    """
    The four-agent path: held corpus + filtered web evidence, grounded by
    precedence and composed with citations.

    Returns the answer AND the working - what the filtration agent accepted and
    rejected, and how the evidence was ordered. The rejections are part of the
    response because a filter whose refusals are invisible cannot be reviewed.
    """
    from backend.agents.pipeline import run as _run

    return _run(
        payload.get("question", ""),
        k=int(payload.get("k", 4) or 4),
        include_web=bool(payload.get("include_web", True)),
    )


@app.post("/api/agents/upload")
async def upload_clinical_document(
    file: UploadFile = File(...),
    document_id: str = Form(...),
    title: str = Form(...),
    issuing_org: str = Form(""),
    claimed_rank: Optional[int] = Form(None),
    current_clinician: Dict[str, str] = Depends(get_current_clinician),
):
    """
    Agent 1: a clinician uploads a trusted document into the retrieval corpus.

    THE ATTESTING ROLE COMES FROM THE TOKEN, never from the request body - the
    same rule the override endpoint follows (Spec §18A). A body that claims
    ATTENDING_PHYSICIAN gets whatever role the session actually holds, because
    rank 1 outranks the national guidelines and a self-declared role would make
    that a claim anyone could make.
    """
    from backend.agents.ingestion import ingest_upload

    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in (".pdf", ".txt", ".md"):
        raise HTTPException(status_code=400, detail="Only .pdf, .txt and .md files can be ingested.")

    contents = await file.read()
    if len(contents) > 40 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds the 40 MB ingestion limit.")

    tmp_dir = Path(tempfile.mkdtemp(prefix="antibiotix-upload-"))
    tmp_path = tmp_dir / (file.filename or f"upload{suffix}")
    try:
        tmp_path.write_bytes(contents)
        outcome = ingest_upload(
            tmp_path,
            document_id=document_id.strip().upper(),
            title=title.strip(),
            issuing_org=issuing_org.strip(),
            claimed_rank=claimed_rank,
            # "clinician_role", not "role": that is the key the session registry
            # actually sets, and reading the wrong one silently produced None --
            # which the rank gate correctly read as "no attesting role" and refused
            # every rank-1 claim, including an attending physician's.
            attesting_role=current_clinician.get("clinician_role"),
            uploaded_by=current_clinician.get("clinician_id", "UNKNOWN"),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if not outcome.accepted:
        # 422 with the WHOLE outcome, not just the message. A refusal here is the
        # safety behaviour working, and the caller needs the trace and the failed
        # checks to see which rule stopped it -- a bare string turns a reviewable
        # refusal into an unexplained error.
        return JSONResponse(status_code=422, content=outcome.to_dict())
    return outcome.to_dict()


@app.get("/api/agents/documents/{document_id}/markdown")
def download_document_markdown(document_id: str, download: bool = False):
    """
    The Markdown a document was converted to before it was indexed.

    THIS IS THE VERIFICATION PATH, not a convenience. Everything downstream --
    the chunks, the embeddings, the citations a clinician is shown -- is derived
    from this file. Without it, "the system indexed my antibiogram correctly" is
    something a user can only take on trust. With it, they can read exactly what
    was indexed and compare it against the PDF on their desk.
    """
    from backend.agents.ingestion import markdown_path_for

    # Path traversal: the id becomes a filename, so anything that is not the id
    # format is refused before it reaches the filesystem.
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{2,63}", document_id or ""):
        raise HTTPException(status_code=400, detail="Not a valid document id.")

    path = markdown_path_for(document_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No converted Markdown is held for {document_id}. Documents ingested "
                   f"before the Markdown pipeline, and those ingested by the corpus scripts, "
                   f"have none.",
        )
    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=f"{document_id}.md" if download else None,
    )


@app.get("/api/agents/documents")
def list_ingested_documents():
    """
    Documents that went through the ingestion agent, newest first.

    Reported from the Markdown directory rather than from the corpus index,
    because that is the set this endpoint can actually serve. Listing every held
    document would offer a download for the 90-odd corpus documents that were
    ingested before this pipeline existed and have no Markdown at all.
    """
    from backend.agents.ingestion import markdown_dir
    from backend.rag.store import vector_store

    directory = markdown_dir()
    if not directory.exists():
        return {"documents": [], "count": 0}

    vector_store._load_chunks()
    rows = []
    for path in directory.glob("*.md"):
        doc = vector_store.docs.get(path.stem) or {}
        stat = path.stat()
        rows.append({
            "document_id": path.stem,
            "title": doc.get("title"),
            "issuing_org": doc.get("issuing_org"),
            "precedence_rank": doc.get("precedence_rank"),
            "clinical_domain": doc.get("clinical_domain"),
            # A Markdown file with no matching corpus entry means the document was
            # removed from the index; the conversion is still readable and says so.
            "still_indexed": bool(doc),
            "markdown_bytes": stat.st_size,
            "converted_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                                    .isoformat(timespec="seconds"),
            "markdown_url": f"/api/agents/documents/{path.stem}/markdown",
        })
    rows.sort(key=lambda r: r["converted_at"], reverse=True)
    return {"documents": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Live Test Suite Execution (Spec §16, §23)
# ---------------------------------------------------------------------------

@app.post("/api/system/run-test-suite")
def run_test_suite():
    """
    Execute the automated clinical safety suite as a subprocess and report the
    REAL result. Counts are parsed from pytest output, never hardcoded: if the
    run fails or times out, that is reported as-is rather than as a pass.
    """
    import subprocess
    import sys
    import re as _re

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    started = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no",
             "-p", "no:cacheprovider", "--color=no"],
            cwd=project_root,
            capture_output=True,
            text=True,
            # 600s, raised from 180s. The suite runs ~275s: 532 tests, several of
            # which load the embedding model and the 15,894-chunk corpus. At 180s
            # this endpoint reported TIMEOUT on a suite that was passing, which is
            # a worse answer than a slow one -- it reads as a broken system.
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return {
            "executed": False,
            "status": "TIMEOUT",
            "detail": "Test suite exceeded the 600s limit; no result can be reported.",
        }
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"executed": False, "status": "ERROR", "detail": str(exc)}

    output = (proc.stdout or "") + (proc.stderr or "")
    # Strip any residual ANSI colour codes so the summary renders cleanly in the UI.
    output = _re.sub(r"\033\[[0-9;]*m", "", output)
    counts = {
        key: int(match.group(1))
        for key, pattern in (
            ("passed", r"(\d+) passed"),
            ("failed", r"(\d+) failed"),
            ("errors", r"(\d+) error"),
            ("skipped", r"(\d+) skipped"),
        )
        if (match := _re.search(pattern, output))
    }
    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0) + counts.get("errors", 0)

    return {
        "executed": True,
        "status": "PASSED" if (proc.returncode == 0 and failed == 0) else "FAILED",
        "exit_code": proc.returncode,
        "passed": passed,
        "failed": failed,
        "skipped": counts.get("skipped", 0),
        "total": passed + failed + counts.get("skipped", 0),
        "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        "summary_line": next(
            (ln.strip() for ln in reversed(output.splitlines()) if "passed" in ln or "failed" in ln),
            "",
        ),
    }


# Static Files & Frontend Routing
# ---------------------------------------------------------------------------

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
# Demo reliability: the frontend is a live-edited prototype, so browsers must never
# serve a stale index.html / app.js against a newer backend. Disable caching for all
# statically served assets.
_NO_STORE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


class NoCacheStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers.update(_NO_STORE)
        return resp


if os.path.exists(frontend_dir):
    app.mount("/static", NoCacheStaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_frontend_root():
        return FileResponse(
            os.path.join(frontend_dir, "index.html"), headers=_NO_STORE
        )

    # SPA deep-link fallback.
    #
    # The frontend routes client-side, so /clinical-tools/pipeline exists only
    # once the app has booted. Without this, opening or REFRESHING any route
    # other than "/" returns {"detail":"Not Found"} - the application replaced by
    # raw JSON, which is what a reader sees if they reload the page they are
    # looking at.
    #
    # AN EXPLICIT LIST OF THE FRONTEND'S OWN ROUTES, not a "/{path:path}"
    # catch-all. A catch-all matches every unrouted URL in the application, which
    # means it silently takes over two things that must not change: the clean JSON
    # 404 an API client depends on, and the trailing-slash redirect that resolves
    # an authenticated route to its 401 rather than a 404. Listing the routes
    # keeps the fallback incapable of shadowing anything under /api.
    #
    # Keep in step with the <Route> list in frontend-src/src/App.tsx.
    _SPA_ROUTES = (
        "/landing", "/login", "/patient-type", "/feedback", "/dashboard", "/review",
        "/clinical-tools", "/clinical-tools/{rest:path}",
        "/patients/{rest:path}",
    )

    def _serve_spa_shell(rest: str = ""):
        return FileResponse(
            os.path.join(frontend_dir, "index.html"), headers=_NO_STORE
        )

    for _route in _SPA_ROUTES:
        app.get(_route, include_in_schema=False)(_serve_spa_shell)
