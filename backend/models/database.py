"""
Database Models & SQLite Setup for S11 Prescription Safety Assistant
"""
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

def now_ist() -> datetime:
    return datetime.now(IST)

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, 
    Text, DateTime, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from backend.config import SYSTEM_VERSION, PROMPT_TEMPLATE_ID

Base = declarative_base()

# Database URL configuration (PostgreSQL production / SQLite fallback)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "prescriptions_safety.db"
DB_PATH = DEFAULT_SQLITE_PATH

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class PatientDB(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String(64), unique=True, index=True, nullable=False)
    display_name = Column(String(128), default="Synthetic Patient")
    age = Column(Integer, nullable=True)
    age_category = Column(String(32), default="UNKNOWN")
    weight_kg = Column(Float, nullable=True)
    sex = Column(String(16), default="UNKNOWN")
    allergies_json = Column(Text, default="[]")  # JSON list
    allergy_status_known = Column(Boolean, default=True)
    medical_history_json = Column(Text, default="[]") # JSON list of conditions
    egfr_ml_min = Column(Float, nullable=True)
    serum_creatinine_mg_dl = Column(Float, nullable=True)
    renal_status_known = Column(Boolean, default=True)
    child_pugh_class = Column(String(8), nullable=True)
    hepatic_status_known = Column(Boolean, default=True)
    pregnancy_status = Column(String(32), default="UNKNOWN")
    lactation_status = Column(String(32), default="UNKNOWN")
    active_medications_json = Column(Text, default="[]")  # JSON list
    clinical_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_ist)
    updated_at = Column(DateTime, default=now_ist, onupdate=now_ist)

    prescriptions = relationship("PrescriptionDB", back_populates="patient")
    visits = relationship("VisitDB", back_populates="patient", cascade="all, delete-orphan")


class DoctorDB(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(String(64), unique=True, index=True, nullable=False)
    display_name = Column(String(128), nullable=False)
    role = Column(String(64), default="ATTENDING_PHYSICIAN")
    created_at = Column(DateTime, default=now_ist)


class VisitDB(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(String(64), unique=True, index=True, nullable=False)
    patient_id = Column(String(64), ForeignKey("patients.patient_id"), nullable=False)
    doctor_id = Column(String(64), default="DOC-DEFAULT")
    visit_date = Column(DateTime, default=now_ist)
    diagnosis = Column(String(256), nullable=True)
    clinical_notes = Column(Text, nullable=True)
    prescription_id = Column(String(64), nullable=True)
    status = Column(String(32), default="COMPLETED")
    created_at = Column(DateTime, default=now_ist)

    patient = relationship("PatientDB", back_populates="visits")
    symptoms = relationship("SymptomDB", back_populates="visit", cascade="all, delete-orphan")
    diagnoses = relationship("DiagnosisDB", back_populates="visit", cascade="all, delete-orphan")


class SymptomDB(Base):
    __tablename__ = "symptoms"

    id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(String(64), ForeignKey("visits.visit_id"), nullable=False)
    patient_id = Column(String(64), ForeignKey("patients.patient_id"), nullable=False)
    name = Column(String(128), nullable=False)
    severity = Column(String(32), default="Moderate")
    duration = Column(String(64), nullable=True)
    onset = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_ist)

    visit = relationship("VisitDB", back_populates="symptoms")


class DiagnosisDB(Base):
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(String(64), ForeignKey("visits.visit_id"), nullable=False)
    patient_id = Column(String(64), ForeignKey("patients.patient_id"), nullable=False)
    diagnosis_name = Column(String(256), nullable=False)
    icd_code = Column(String(32), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_ist)

    visit = relationship("VisitDB", back_populates="diagnoses")


class PatientRAGDocumentDB(Base):
    __tablename__ = "patient_rag_documents"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(String(64), unique=True, index=True, nullable=False)
    patient_id = Column(String(64), index=True, nullable=False)
    visit_id = Column(String(64), index=True, nullable=False)
    visit_date = Column(String(32), nullable=False)
    record_type = Column(String(32), default="visit")
    content = Column(Text, nullable=False)
    embedding_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_ist)


class PrescriptionDB(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(String(64), unique=True, index=True, nullable=False)
    patient_id = Column(String(64), ForeignKey("patients.patient_id"), nullable=False)
    visit_id = Column(String(64), nullable=True)
    diagnosis = Column(String(256), nullable=True)
    raw_text = Column(Text, nullable=True)
    clinician_id = Column(String(64), default="DOC-DEFAULT")
    clinician_role = Column(String(64), default="ATTENDING_PHYSICIAN")
    status = Column(String(32), default="ANALYZED")
    created_at = Column(DateTime, default=now_ist)

    patient = relationship("PatientDB", back_populates="prescriptions")
    items = relationship("PrescriptionItemDB", back_populates="prescription", cascade="all, delete-orphan")
    warnings = relationship("SafetyWarningDB", back_populates="prescription", cascade="all, delete-orphan")


class PrescriptionItemDB(Base):
    __tablename__ = "prescription_items"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(String(64), ForeignKey("prescriptions.prescription_id"), nullable=False)
    medication_name = Column(String(128), nullable=False)
    dose = Column(Float, nullable=True)
    unit = Column(String(32), nullable=True)
    route = Column(String(32), nullable=True)
    frequency = Column(String(32), nullable=True)
    duration_days = Column(Integer, nullable=True)
    indication = Column(String(256), nullable=True)
    antimicrobial_class = Column(String(64), nullable=True)
    aware_category = Column(String(32), default="NOT_APPLICABLE")
    extraction_confidence_json = Column(Text, nullable=True)

    prescription = relationship("PrescriptionDB", back_populates="items")


class ClinicalRuleDB(Base):
    __tablename__ = "clinical_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(String(64), unique=True, index=True, nullable=False)
    rule_name = Column(String(256), nullable=False)
    category = Column(String(64), nullable=False)
    severity = Column(String(32), nullable=False)
    description = Column(Text, nullable=False)
    input_conditions_json = Column(Text, nullable=False)
    output_concern = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)
    evidence_source = Column(String(256), nullable=False)
    guideline_version = Column(String(64), nullable=False)
    effective_date = Column(String(32), nullable=True)
    review_date = Column(String(32), nullable=True)
    author = Column(String(128), default="SYSTEM_GENERATED")
    approval_status = Column(String(64), default="PENDING_CLINICAL_REVIEW")
    approved_by = Column(String(128), nullable=True)
    source_url = Column(String(512), nullable=True)
    section_page = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True)


class RuleAuthorshipLogDB(Base):
    __tablename__ = "rule_authorship_logs"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)  # CREATED, UPDATED, APPROVED, RETIRED
    author_id = Column(String(64), nullable=False)
    author_role = Column(String(64), nullable=False)
    approved_by = Column(String(64), nullable=True)
    change_summary = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=now_ist)


class AppointmentDB(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(String(64), unique=True, index=True, nullable=False)
    patient_id = Column(String(64), ForeignKey("patients.patient_id"), nullable=False)
    visit_id = Column(String(64), nullable=True)
    doctor_id = Column(String(64), default="DOC-DEFAULT")
    appointment_date = Column(DateTime, nullable=False)
    reason = Column(Text, nullable=False)
    doctor_email = Column(String(128), nullable=True)
    patient_email = Column(String(128), nullable=True)
    patient_phone = Column(String(32), nullable=True)
    notification_sent = Column(Boolean, default=False)
    advance_notice_sent = Column(Boolean, default=False)
    same_day_alert_sent = Column(Boolean, default=False)
    same_day_alert_timestamp = Column(DateTime, nullable=True)
    delivery_status_json = Column(Text, default="{}")
    status = Column(String(32), default="SCHEDULED")
    created_at = Column(DateTime, default=now_ist)


class GuidelineDocumentDB(Base):
    __tablename__ = "guideline_documents"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(String(64), unique=True, index=True, nullable=False)
    title = Column(String(256), nullable=False)
    issuing_org = Column(String(128), nullable=False)
    version = Column(String(64), nullable=False)
    geographic_scope = Column(String(128), nullable=False)
    precedence_rank = Column(Integer, nullable=False)
    source_url = Column(String(512), nullable=True)
    document_json = Column(Text, nullable=False)


class AMRSurveillanceDB(Base):
    __tablename__ = "amr_surveillance_records"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(String(64), unique=True, index=True, nullable=False)
    organism = Column(String(128), nullable=False)
    antimicrobial = Column(String(128), nullable=False)
    resistance_rate_pct = Column(Float, nullable=False)
    sample_size = Column(Integer, nullable=False)
    geographic_scope = Column(String(128), nullable=False)
    data_source = Column(String(256), nullable=False)
    reporting_year = Column(Integer, nullable=False)


class SafetyWarningDB(Base):
    __tablename__ = "safety_warnings"

    id = Column(Integer, primary_key=True, index=True)
    warning_id = Column(String(128), unique=True, index=True, nullable=False)
    prescription_id = Column(String(64), ForeignKey("prescriptions.prescription_id"), nullable=False)
    rule_id = Column(String(64), nullable=False)
    category = Column(String(64), nullable=False)
    severity = Column(String(32), nullable=False)
    title = Column(String(256), nullable=False)
    clinical_concern = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)
    prescribed_drug = Column(String(128), nullable=False)
    interacting_factor = Column(String(128), nullable=True)
    evidence_document = Column(String(256), nullable=False)
    evidence_version = Column(String(64), nullable=False)
    evidence_passage = Column(Text, nullable=False)
    evidence_url = Column(String(512), nullable=True)
    supporting_labels_json = Column(Text, nullable=True)  # regulatory product-label evidence
    rule_author = Column(String(128), default="SYSTEM_GENERATED")
    rule_approval_status = Column(String(128), default="PENDING_CLINICAL_REVIEW")
    rule_effective_date = Column(String(32), nullable=True)
    status = Column(String(32), default="ACTIVE")  # ACTIVE, OVERRIDDEN, REVIEWED
    created_at = Column(DateTime, default=now_ist)

    prescription = relationship("PrescriptionDB", back_populates="warnings")
    override = relationship("ClinicianOverrideDB", back_populates="warning", uselist=False)


class ClinicianOverrideDB(Base):
    __tablename__ = "clinician_overrides"

    id = Column(Integer, primary_key=True, index=True)
    override_id = Column(String(64), unique=True, index=True, nullable=False)
    warning_id = Column(String(64), ForeignKey("safety_warnings.warning_id"), nullable=False)
    prescription_id = Column(String(64), nullable=False)
    clinician_id = Column(String(64), nullable=False)
    clinician_role = Column(String(64), nullable=False)
    override_reason = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=now_ist)

    warning = relationship("SafetyWarningDB", back_populates="override")


class AuditLogDB(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    log_id = Column(String(64), unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, default=now_ist)
    event_type = Column(String(64), nullable=False)
    prescription_id = Column(String(64), nullable=False)
    patient_id = Column(String(64), nullable=False)
    clinician_id = Column(String(64), nullable=False)
    clinician_role = Column(String(64), nullable=False)
    action_summary = Column(Text, nullable=False)
    payload_json = Column(Text, nullable=False)
    prev_hash = Column(String(64), nullable=True)
    integrity_hash = Column(String(64), nullable=False)
    model_version = Column(String(64), default=SYSTEM_VERSION)
    prompt_template_id = Column(String(64), default=PROMPT_TEMPLATE_ID)


class AlertMetricsDB(Base):
    __tablename__ = "alert_metrics"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(String(64), unique=True, nullable=False)
    total_triggered = Column(Integer, default=0)
    total_overridden = Column(Integer, default=0)
    total_accepted = Column(Integer, default=0)
    last_triggered_at = Column(DateTime, nullable=True)


def init_db():
    from sqlalchemy import text
    Base.metadata.create_all(bind=engine)
    # Perform column migrations for SQLite if columns were added
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE patients ADD COLUMN display_name VARCHAR(128) DEFAULT 'Synthetic Patient'",
            "ALTER TABLE patients ADD COLUMN medical_history_json TEXT DEFAULT '[]'",
            "ALTER TABLE patients ADD COLUMN updated_at DATETIME",
            "ALTER TABLE prescriptions ADD COLUMN visit_id VARCHAR(64)",
            "ALTER TABLE appointments ADD COLUMN patient_phone VARCHAR(32)",
            "ALTER TABLE appointments ADD COLUMN advance_notice_sent BOOLEAN DEFAULT 0",
            "ALTER TABLE appointments ADD COLUMN same_day_alert_sent BOOLEAN DEFAULT 0",
            "ALTER TABLE appointments ADD COLUMN same_day_alert_timestamp DATETIME",
            "ALTER TABLE appointments ADD COLUMN delivery_status_json TEXT DEFAULT '{}'"
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass
