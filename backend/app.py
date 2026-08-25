"""
FastAPI Main Application for S11 Explainable Antimicrobial Stewardship & Safety Assistant
"""
import os
import threading
import uuid
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from backend.config import (
    SYSTEM_VERSION, ENGINE_BUILD, MODEL_NAME, PROMPT_TEMPLATE_ID,
    PROMPT_TEMPLATE_HASH, GUIDELINE_PRECEDENCE_HIERARCHY,
    AUTHORIZED_OVERRIDE_ROLES, ALERT_FATIGUE_OVERRIDE_RATE_THRESHOLD
)
from backend.models import allergies as allergy_store
from backend.models.database import (
    get_db, init_db, SessionLocal, PatientDB, PrescriptionDB, PrescriptionItemDB,
    SafetyWarningDB, ClinicianOverrideDB, ClinicalRuleDB, RuleAuthorshipLogDB,
    GuidelineDocumentDB, AMRSurveillanceDB, AlertMetricsDB, AuditLogDB,
    DoctorDB, VisitDB, SymptomDB, DiagnosisDB, PatientRAGDocumentDB, AppointmentDB
)
from backend.models.schemas import (
    PatientCreate, PatientResponse, PrescriptionCreate, PrescriptionItem,
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
from backend.auth.security import (
    authorizer, get_current_clinician, create_session_token, create_patient_token,
    get_current_principal, require_clinician, require_patient_scope,
    PATIENT_MANAGEMENT_ROLES,
)
from backend.audit.logger import audit_logger
from backend.seed_data import list_scenario_presets


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
        "timestamp": datetime.now(timezone.utc).isoformat()
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
        "guideline_sources_note": (
            "Derived from the documents actually ingested into this system, not a "
            "hardcoded list. Renal calculations use the CKD-EPI 2021 non-race "
            "equation, which is an implemented formula rather than an ingested document."
        )
    }


# ---------------------------------------------------------------------------
# Authentication Endpoint (Section 28)
# ---------------------------------------------------------------------------

@app.post("/api/auth/login")
def mock_clinician_login(payload: Dict[str, Any]):
    username = payload.get("username", "clinician_demo")
    role = payload.get("role", "ATTENDING_PHYSICIAN")
    access_token = create_session_token(username, role)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "clinician_id": username.upper(),
        "clinician_role": role,
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
    v_date = datetime.now(timezone.utc)
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
        status="COMPLETED"
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
            raise HTTPException(status_code=404, detail="Visit record not found")

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
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


@app.post("/api/appointments", status_code=status.HTTP_201_CREATED)
def schedule_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    principal: Dict[str, str] = Depends(get_current_principal),
):
    """
    Schedule a follow-up appointment for a patient.
    Sends notifications (simulated email to doctor & patient 2 days before).
    """
    require_clinician(principal)
    p = db.query(PatientDB).filter(PatientDB.patient_id == payload.patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    try:
        app_dt = datetime.fromisoformat(payload.appointment_date)
    except Exception:
        app_dt = datetime.now(timezone.utc)

    appt_id = f"APT-{uuid.uuid4().hex[:6].upper()}"
    appt = AppointmentDB(
        appointment_id=appt_id,
        patient_id=payload.patient_id,
        visit_id=payload.visit_id,
        doctor_id=principal.get("clinician_id", "DOC-DEMO-01"),
        appointment_date=app_dt,
        reason=payload.reason,
        doctor_email=payload.doctor_email or "doctor@hospital.org",
        patient_email=payload.patient_email or "patient@de-identified.org",
        notification_sent=True,
        status="SCHEDULED"
    )
    db.add(appt)
    db.commit()

    audit_logger.log_event(
        db=db,
        event_type="APPOINTMENT_SCHEDULED",
        prescription_id="-",
        patient_id=payload.patient_id,
        clinician_id=principal.get("clinician_id", "DOC-DEMO-01"),
        clinician_role=principal.get("clinician_role", "ATTENDING_PHYSICIAN"),
        action_summary=f"Follow-up appointment scheduled for {payload.patient_id} on {app_dt.strftime('%d %b %Y')}.",
        payload={
            "appointment_id": appt_id,
            "appointment_date": app_dt.isoformat(),
            "reason": payload.reason,
            "notification_scheduled": "2 days before appointment"
        }
    )

    return {
        "status": "SCHEDULED",
        "appointment_id": appt_id,
        "patient_id": payload.patient_id,
        "appointment_date": app_dt.isoformat(),
        "reason": payload.reason,
        "notification": "Follow-up email notifications scheduled for doctor and patient (2 days prior)."
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

    The request model carries no name, phone, address or government identifier,
    and the patient_id is issued by the server - spec 24/25 require synthetic,
    de-identified records, so the API is given nowhere to put a real one.

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
    p = PatientDB(
        patient_id=patient_id,
        age=payload.age,
        age_category=payload.age_category.value if payload.age_category else "UNKNOWN",
        sex=payload.sex or "UNKNOWN",
        weight_kg=payload.weight_kg,
        allergies_json=allergy_store.dumps([]),
        allergy_status_known=payload.allergy_status_known,
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
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {
            "executed": False,
            "status": "TIMEOUT",
            "detail": "Test suite exceeded the 180s limit; no result can be reported.",
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
