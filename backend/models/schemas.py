"""
Pydantic Schemas for S11 Explainable Antimicrobial Stewardship & Prescription Safety Assistant
"""
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class SeverityLevel(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RuleCategory(str, Enum):
    ALLERGY = "ALLERGY"
    RENAL = "RENAL"
    HEPATIC = "HEPATIC"
    DUPLICATION = "DUPLICATION"
    DRUG_INTERACTION = "DRUG_INTERACTION"
    VULNERABLE_POPULATION = "VULNERABLE_POPULATION"
    STEWARDSHIP = "STEWARDSHIP"
    DIAGNOSIS_GUIDELINE = "DIAGNOSIS_GUIDELINE"


class PregnancyStatus(str, Enum):
    CONFIRMED_NOT_PREGNANT = "CONFIRMED_NOT_PREGNANT"
    PREGNANT_TRIMESTER_1 = "PREGNANT_TRIMESTER_1"
    PREGNANT_TRIMESTER_2 = "PREGNANT_TRIMESTER_2"
    PREGNANT_TRIMESTER_3 = "PREGNANT_TRIMESTER_3"
    UNKNOWN = "UNKNOWN"


class LactationStatus(str, Enum):
    CONFIRMED_NOT_LACTATING = "CONFIRMED_NOT_LACTATING"
    LACTATING = "LACTATING"
    UNKNOWN = "UNKNOWN"


class AgeCategory(str, Enum):
    NEONATAL = "NEONATAL"      # < 28 days
    PEDIATRIC = "PEDIATRIC"    # 28 days - 17 years
    ADULT = "ADULT"            # 18 - 64 years
    GERIATRIC = "GERIATRIC"    # >= 65 years
    UNKNOWN = "UNKNOWN"


class ClinicianRole(str, Enum):
    ATTENDING_PHYSICIAN = "ATTENDING_PHYSICIAN"
    CLINICAL_PHARMACIST = "CLINICAL_PHARMACIST"
    INFECTIOUS_DISEASE_SPECIALIST = "INFECTIOUS_DISEASE_SPECIALIST"
    RESIDENT_PHYSICIAN = "RESIDENT_PHYSICIAN"
    STAFF_NURSE = "STAFF_NURSE"


class AWaReCategory(str, Enum):
    ACCESS = "ACCESS"
    WATCH = "WATCH"
    RESERVE = "RESERVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# Patient Models
# ---------------------------------------------------------------------------

class PatientCreate(BaseModel):
    patient_id: str = Field(..., description="Synthetic patient identifier, e.g. PATIENT-001")
    age: Optional[int] = Field(None, ge=0, le=125, description="Patient age in years")
    age_category: AgeCategory = Field(AgeCategory.UNKNOWN)
    weight_kg: Optional[float] = Field(None, ge=0.5, le=300.0, description="Patient weight in kg")
    sex: Optional[str] = Field(None, description="Biological sex (MALE, FEMALE, UNKNOWN)")
    allergies: List[str] = Field(default_factory=list, description="List of documented medication allergies")
    allergy_status_known: bool = Field(True, description="False if allergy history has not been elicited")
    egfr_ml_min: Optional[float] = Field(None, ge=0.0, le=200.0, description="eGFR using CKD-EPI 2021 non-race formula")
    serum_creatinine_mg_dl: Optional[float] = Field(None, ge=0.1, le=25.0)
    renal_status_known: bool = Field(True, description="False if renal labs are unavailable")
    child_pugh_class: Optional[str] = Field(None, description="A, B, C, or None")
    hepatic_status_known: bool = Field(True, description="False if hepatic evaluation is unavailable")
    pregnancy_status: PregnancyStatus = Field(PregnancyStatus.UNKNOWN)
    lactation_status: LactationStatus = Field(LactationStatus.UNKNOWN)
    active_medications: List[str] = Field(default_factory=list, description="Concurrent home/inpatient medications")
    clinical_notes: Optional[str] = Field(None, description="Free text clinical notes/context")


class PatientResponse(PatientCreate):
    id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Prescription Item & Order Models
# ---------------------------------------------------------------------------

class PrescriptionItem(BaseModel):
    medication_name: str = Field(..., description="Generic or proprietary medication name")
    dose: Optional[float] = Field(None, description="Numerical dose")
    unit: Optional[str] = Field(None, description="mg, g, mcg, ml, IU")
    route: Optional[str] = Field(None, description="PO, IV, IM, TOPICAL, INHALED")
    frequency: Optional[str] = Field(None, description="QD, BID, TID, QID, Q8H, Q12H, Q24H, PRN")
    duration_days: Optional[int] = Field(None, ge=1, le=365, description="Treatment duration in days")
    indication: Optional[str] = Field(None, description="Documented clinical indication")
    antimicrobial_class: Optional[str] = None
    aware_category: Optional[AWaReCategory] = None
    extraction_confidence: Optional[Dict[str, float]] = None


class PrescriptionCreate(BaseModel):
    prescription_id: Optional[str] = None
    patient_id: str
    diagnosis: Optional[str] = Field(None, description="Clinical diagnosis, e.g. Community-Acquired Pneumonia")
    raw_text: Optional[str] = Field(None, description="Free-text prescription order for extraction")
    items: List[PrescriptionItem] = Field(default_factory=list)
    clinician_id: str = Field("DOC-DEMO-01")
    clinician_role: ClinicianRole = Field(ClinicianRole.ATTENDING_PHYSICIAN)


class ExtractedPrescription(BaseModel):
    raw_text: str
    patient_id: Optional[str] = None
    diagnosis: Optional[str] = None
    items: List[PrescriptionItem]
    field_confidences: Dict[str, float]
    overall_confidence: float
    needs_clinician_confirmation: bool
    unparsed_tokens: List[str] = Field(default_factory=list)
    extraction_method: str = "HYBRID_REGEX_NER_CLINICAL_PARSER"


# ---------------------------------------------------------------------------
# Clinical Evidence & Warnings
# ---------------------------------------------------------------------------

class EvidenceCitation(BaseModel):
    document_title: str
    issuing_org: str
    geographic_scope: str = "National (India - ICMR) / Global (WHO)"
    guideline_version: str
    publication_date: Optional[str] = None
    source_url: Optional[str] = None
    section_page: Optional[str] = None
    verbatim_passage: str
    retrieval_score: Optional[float] = None
    unverified_sources: List[str] = Field(
        default_factory=list,
        description="Authorities named in this rule's clinical rationale that have NO ingested document in this repository. Must not be presented to a clinician as retrievable evidence."
    )


class SafetyWarning(BaseModel):
    warning_id: str
    rule_id: str
    category: RuleCategory
    severity: SeverityLevel
    title: str
    clinical_concern: str
    recommendation: str
    prescribed_drug: str
    interacting_factor: Optional[str] = None
    evidence: EvidenceCitation
    supporting_labels: List[EvidenceCitation] = Field(
        default_factory=list,
        description="Drug-specific regulatory product-label evidence. Distinct evidence class from the guideline citation above; never a substitute for it."
    )
    rule_author: str = "SYSTEM_GENERATED"
    rule_approval_status: str = "PENDING_CLINICAL_REVIEW"
    rule_effective_date: Optional[str] = None
    status: str = "ACTIVE"  # ACTIVE, OVERRIDDEN, REVIEWED
    override_details: Optional[Dict[str, Any]] = None


class PrescriptionAnalysisResponse(BaseModel):
    prescription_id: str
    patient_id: str
    patient_summary: Dict[str, Any]
    diagnosis: Optional[str]
    items: List[PrescriptionItem]
    warnings: List[SafetyWarning]
    total_warnings: int
    critical_warnings_count: int
    high_warnings_count: int
    moderate_warnings_count: int
    stewardship_summary: Dict[str, Any]
    guideline_recommendations: List[Dict[str, Any]]
    local_amr_context: List[Dict[str, Any]]
    explanation: Optional[str] = None
    model_version_info: Dict[str, str]
    created_at: datetime


# ---------------------------------------------------------------------------
# Clinician Override & Audit Models
# ---------------------------------------------------------------------------

class OverrideRequest(BaseModel):
    warning_id: Optional[str] = None
    override_reason: str = Field(..., min_length=10, description="Mandatory substantive clinical rationale for override")
    clinician_id: Optional[str] = None
    clinician_role: Optional[ClinicianRole] = None
    password: Optional[str] = None


class OverrideResponse(BaseModel):
    status: str = "CONFIRMED"
    warning_id: str
    override_id: str
    prescription_id: str
    clinician_id: str
    clinician_role: str
    timestamp: datetime
    message: str = "Warning successfully overridden and logged in immutable audit trail."


class AuditLogEntry(BaseModel):
    log_id: str
    timestamp: datetime
    event_type: str
    prescription_id: str
    patient_id: str
    clinician_id: str
    clinician_role: str
    action_summary: str
    details: Dict[str, Any]
    integrity_hash: str
