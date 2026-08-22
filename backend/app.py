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
from backend.models.database import (
    get_db, init_db, PatientDB, PrescriptionDB, PrescriptionItemDB,
    SafetyWarningDB, ClinicianOverrideDB, ClinicalRuleDB, RuleAuthorshipLogDB,
    GuidelineDocumentDB, AMRSurveillanceDB, AlertMetricsDB, AuditLogDB
)
from backend.models.schemas import (
    PatientCreate, PatientResponse, PrescriptionCreate, PrescriptionItem,
    ExtractedPrescription, SafetyWarning, PrescriptionAnalysisResponse,
    OverrideRequest, OverrideResponse, ClinicianRole, SeverityLevel, RuleCategory
)
from backend.guidelines.knowledge_base import knowledge_base
from backend.rules.engine import rule_engine
from backend.rules.priority import compute_stewardship_priority
from backend.extraction.parser import clinical_parser
from backend.llm.explainer import clinical_explainer
from backend.auth.security import authorizer, get_current_clinician, create_session_token
from backend.audit.logger import audit_logger


# Lifespan event handler for clean startup / database initialization
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    init_db()

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
# Patients Endpoints (Sections 3, 24, 25)
# ---------------------------------------------------------------------------

@app.get("/api/patients")
def list_patients(db: Session = Depends(get_db)):
    patients = db.query(PatientDB).all()
    results = []
    for p in patients:
        results.append({
            "id": p.id,
            "patient_id": p.patient_id,
            "age": p.age,
            "age_category": p.age_category,
            "sex": p.sex,
            "weight_kg": p.weight_kg,
            "allergies": json.loads(p.allergies_json) if p.allergies_json else [],
            "allergy_status_known": p.allergy_status_known,
            "egfr_ml_min": p.egfr_ml_min,
            "serum_creatinine_mg_dl": p.serum_creatinine_mg_dl,
            "renal_status_known": p.renal_status_known,
            "child_pugh_class": p.child_pugh_class,
            "hepatic_status_known": p.hepatic_status_known,
            "pregnancy_status": p.pregnancy_status,
            "lactation_status": p.lactation_status,
            "active_medications": json.loads(p.active_medications_json) if p.active_medications_json else [],
            "clinical_notes": p.clinical_notes
        })
    return results


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    p = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {
        "patient_id": p.patient_id,
        "age": p.age,
        "age_category": p.age_category,
        "sex": p.sex,
        "weight_kg": p.weight_kg,
        "allergies": json.loads(p.allergies_json) if p.allergies_json else [],
        "allergy_status_known": p.allergy_status_known,
        "egfr_ml_min": p.egfr_ml_min,
        "serum_creatinine_mg_dl": p.serum_creatinine_mg_dl,
        "renal_status_known": p.renal_status_known,
        "child_pugh_class": p.child_pugh_class,
        "hepatic_status_known": p.hepatic_status_known,
        "pregnancy_status": p.pregnancy_status,
        "lactation_status": p.lactation_status,
        "active_medications": json.loads(p.active_medications_json) if p.active_medications_json else [],
        "clinical_notes": p.clinical_notes
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
        allergies=json.loads(patient_db.allergies_json) if patient_db.allergies_json else [],
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


@app.get("/api/guidelines/precedence")
def get_guideline_precedence(syndrome: str = "uncomplicated_urinary_tract_infection"):
    return knowledge_base.resolve_guideline_precedence(syndrome)


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
