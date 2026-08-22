"""
Knowledge Base Coverage Fail-Safe Test Suite (Spec §17, §23, §32)
Verifies that medications absent from the validated knowledge base explicitly trigger COVERAGE-001
and produce 'unable to assess' guidance rather than false all-clear conclusions.
Verifies that non-antimicrobial concomitant medications do NOT trigger COVERAGE-001.
"""
import pytest
from backend.models.schemas import PatientCreate, PrescriptionCreate, PrescriptionItem, SeverityLevel
from backend.rules.engine import rule_engine
from backend.rules.priority import compute_stewardship_priority
from backend.llm.explainer import clinical_explainer


def test_unknown_fictional_drug_triggers_coverage_warning():
    patient = PatientCreate(
        patient_id="TEST-COV-001",
        age=50,
        egfr_ml_min=12.0,
        child_pugh_class="C",
        allergies=["Penicillin"],
        active_medications=["Warfarin 5mg PO QD"]
    )
    presc = PrescriptionCreate(
        patient_id="TEST-COV-001",
        items=[PrescriptionItem(medication_name="Fictionalcillin", dose=500, unit="mg", route="PO", frequency="TID")]
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    cov_warns = [w for w in warnings if w.rule_id == "COVERAGE-001"]
    
    assert len(cov_warns) == 1, "Must emit COVERAGE-001 for fictional/unsupported drug"
    assert cov_warns[0].severity == SeverityLevel.HIGH
    assert "outside the validated clinical knowledge base" in cov_warns[0].clinical_concern.lower()

    # Priority tier must be HIGH due to coverage fail-safe
    prio = compute_stewardship_priority(warnings, presc.items)
    assert prio["tier"] == "HIGH"
    assert "COVERAGE-001" in prio["contributing_rule_ids"]

    # Explainer verification
    expl_res = clinical_explainer.generate_explanation(patient, presc.items, warnings)
    assert "outside validated knowledge base" in expl_res["explanation"].lower()
    assert "No contraindications" not in expl_res["explanation"]


def test_real_but_uncovered_drug_amikacin():
    patient = PatientCreate(patient_id="TEST-COV-002", age=45, egfr_ml_min=20.0)
    presc = PrescriptionCreate(
        patient_id="TEST-COV-002",
        items=[PrescriptionItem(medication_name="Amikacin", dose=500, unit="mg", route="IV", frequency="QD")]
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    cov_warns = [w for w in warnings if w.rule_id == "COVERAGE-001"]
    
    assert len(cov_warns) == 1, "Must emit COVERAGE-001 for real but uncovered drug Amikacin"
    assert "Amikacin" in cov_warns[0].prescribed_drug

    prio = compute_stewardship_priority(warnings, presc.items)
    assert prio["tier"] == "HIGH"


def test_covered_drug_does_not_trigger_coverage_warning():
    patient = PatientCreate(patient_id="TEST-COV-003", age=30, egfr_ml_min=100.0, allergies=[])
    presc = PrescriptionCreate(
        patient_id="TEST-COV-003",
        items=[PrescriptionItem(medication_name="Amoxicillin", dose=500, unit="mg", route="PO", frequency="TID")]
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    cov_warns = [w for w in warnings if w.rule_id == "COVERAGE-001"]
    assert len(cov_warns) == 0, "Covered drug Amoxicillin must not trigger COVERAGE-001"


def test_coprescribed_ondansetron_does_not_trigger_coverage_escalation():
    """
    Defect 3: Co-prescribing Ondansetron with Ciprofloxacin triggers DDI-002 (QTc risk)
    but must NOT emit COVERAGE-001 for Ondansetron and must NOT escalate to HIGH via coverage.
    """
    patient = PatientCreate(patient_id="TEST-COV-004", age=50, egfr_ml_min=90.0, allergies=[])
    presc = PrescriptionCreate(
        patient_id="TEST-COV-004",
        items=[
            PrescriptionItem(medication_name="Ciprofloxacin", dose=500, unit="mg", route="PO", frequency="BID"),
            PrescriptionItem(medication_name="Ondansetron", dose=8, unit="mg", route="PO", frequency="TID")
        ]
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    rule_ids = {w.rule_id for w in warnings}

    assert "DDI-002" in rule_ids, "Must trigger QTc prolongation interaction (DDI-002)"
    assert "COVERAGE-001" not in rule_ids, "Ondansetron (concomitant non-antimicrobial) must NOT trigger COVERAGE-001"

    prio = compute_stewardship_priority(warnings, presc.items)
    assert prio["tier"] == "MODERATE", "Single DDI-002 without coverage warning should remain MODERATE, not HIGH"
