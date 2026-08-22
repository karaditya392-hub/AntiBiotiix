"""
Deterministic Stewardship Priority Rollup Test Suite (Spec §14, §15, §20, §29)
Verifies the pure, transparent severity rollup function replacing the ML subsystem.
Asserts proper triage prioritization, allergy escalation to HIGH, and determinism.
"""
import pytest
from backend.models.schemas import (
    PatientCreate, PrescriptionCreate, PrescriptionItem, AWaReCategory, SeverityLevel,
    PregnancyStatus
)
from backend.rules.engine import rule_engine
from backend.rules.priority import compute_stewardship_priority


def test_penicillin_allergic_amoxicillin_single_warning_is_high_priority():
    """Defect 2: Penicillin allergy + Amoxicillin (triggering ALLERGY-002 [HIGH]) must escalate to HIGH priority."""
    patient = PatientCreate(
        patient_id="TEST-PRIO-001A",
        age=40,
        allergies=["Penicillin"],
        allergy_status_known=True,
        egfr_ml_min=95.0,  # Normal renal function
        renal_status_known=True
    )
    items = [PrescriptionItem(medication_name="Amoxicillin", dose=500, unit="mg", route="PO", frequency="TID")]
    presc = PrescriptionCreate(patient_id="TEST-PRIO-001A", items=items)

    warnings = rule_engine.evaluate_prescription(patient, presc)
    prio = compute_stewardship_priority(warnings=warnings, items=items)

    assert prio["tier"] == "HIGH", "Beta-lactam allergy cross-reactivity warning (ALLERGY-002) must escalate tier to HIGH."
    assert "ALLERGY-002" in prio["contributing_rule_ids"]
    assert "allergy" in prio["rationale"].lower()


def test_direct_allergy_anaphylaxis_is_high_priority():
    """Direct allergy match (ALLERGY-001 [CRITICAL]) must yield HIGH priority."""
    patient = PatientCreate(
        patient_id="TEST-PRIO-001B",
        age=40,
        allergies=["Amoxicillin"],
        allergy_status_known=True,
        egfr_ml_min=100.0
    )
    items = [PrescriptionItem(medication_name="Amoxicillin", dose=500, unit="mg", route="PO", frequency="TID")]
    presc = PrescriptionCreate(patient_id="TEST-PRIO-001B", items=items)

    warnings = rule_engine.evaluate_prescription(patient, presc)
    prio = compute_stewardship_priority(warnings=warnings, items=items)

    assert prio["tier"] == "HIGH", "Direct allergy match (CRITICAL warning) must yield HIGH stewardship priority."
    assert "ALLERGY-001" in prio["contributing_rule_ids"]


def test_nitrofurantoin_severe_ckd_is_high_priority():
    """Contraindicated medication in severe renal impairment must be HIGH priority."""
    patient = PatientCreate(
        patient_id="TEST-PRIO-002",
        age=70,
        egfr_ml_min=18.0,
        renal_status_known=True
    )
    items = [PrescriptionItem(medication_name="Nitrofurantoin", dose=100, unit="mg", route="PO", frequency="BID")]
    presc = PrescriptionCreate(patient_id="TEST-PRIO-002", items=items)

    warnings = rule_engine.evaluate_prescription(patient, presc)
    prio = compute_stewardship_priority(warnings=warnings, items=items)

    assert prio["tier"] == "HIGH", "Nitrofurantoin in CKD-4 (eGFR < 30) is CRITICAL and must yield HIGH priority."
    assert "RENAL-002" in prio["contributing_rule_ids"]


def test_pregnant_t1_doxycycline_is_high_priority():
    """Teratogenic medication in pregnancy must be HIGH priority."""
    patient = PatientCreate(
        patient_id="TEST-PRIO-PREG",
        age=28,
        pregnancy_status=PregnancyStatus.PREGNANT_TRIMESTER_1
    )
    items = [PrescriptionItem(medication_name="Doxycycline", dose=100, unit="mg", route="PO", frequency="BID")]
    presc = PrescriptionCreate(patient_id="TEST-PRIO-PREG", items=items)

    warnings = rule_engine.evaluate_prescription(patient, presc)
    prio = compute_stewardship_priority(warnings=warnings, items=items)

    assert prio["tier"] == "HIGH", "Doxycycline in pregnancy (VULN-002) is CRITICAL and must yield HIGH priority."
    assert "VULN-002" in prio["contributing_rule_ids"]


def test_healthy_adult_meropenem_zero_warnings_is_low_priority():
    """Healthy adult with appropriate indication and zero safety warnings yields LOW priority."""
    patient = PatientCreate(
        patient_id="TEST-PRIO-003",
        age=35,
        egfr_ml_min=110.0,
        allergies=[],
        allergy_status_known=True
    )
    items = [PrescriptionItem(medication_name="Meropenem", dose=1000, unit="mg", route="IV", frequency="TID", aware_category=AWaReCategory.WATCH)]
    presc = PrescriptionCreate(patient_id="TEST-PRIO-003", diagnosis="Severe Intra-abdominal Sepsis", items=items)

    warnings = rule_engine.evaluate_prescription(patient, presc)
    prio = compute_stewardship_priority(warnings=warnings, items=items)

    assert prio["tier"] == "LOW", "Standard appropriate therapy with zero safety warnings yields LOW priority."


def test_uncovered_drug_is_high_priority():
    """Medications outside validated knowledge base must yield HIGH priority (unable to assess)."""
    patient = PatientCreate(patient_id="TEST-PRIO-004", age=30)
    items = [PrescriptionItem(medication_name="Fictionalcillin", dose=500, unit="mg", route="PO", frequency="TID")]
    presc = PrescriptionCreate(patient_id="TEST-PRIO-004", items=items)

    warnings = rule_engine.evaluate_prescription(patient, presc)
    prio = compute_stewardship_priority(warnings=warnings, items=items)

    assert prio["tier"] == "HIGH"
    assert "COVERAGE-001" in prio["contributing_rule_ids"]
    assert "outside validated knowledge base" in prio["rationale"].lower()


def test_priority_is_deterministic_and_reproducible():
    """Spec §29: The same input evaluated multiple times must always return the exact same tier and rule IDs."""
    patient = PatientCreate(
        patient_id="TEST-PRIO-005",
        age=65,
        allergies=["Penicillin"],
        allergy_status_known=True,
        egfr_ml_min=25.0
    )
    items = [PrescriptionItem(medication_name="Amoxicillin-Clavulanate", dose=625, unit="mg", route="PO", frequency="TID")]
    presc = PrescriptionCreate(patient_id="TEST-PRIO-005", items=items)

    warnings1 = rule_engine.evaluate_prescription(patient, presc)
    prio1 = compute_stewardship_priority(warnings=warnings1, items=items)

    warnings2 = rule_engine.evaluate_prescription(patient, presc)
    prio2 = compute_stewardship_priority(warnings=warnings2, items=items)

    assert prio1 == prio2
    assert prio1["tier"] == "HIGH"
