"""
Rules and syndromes derived from documents held in the retrieval corpus.

Two rules were added on the strength of the expanded corpus, and both close a
STRUCTURAL gap rather than asserting a new clinical position:

  VULN-005  reads `lactation_status` and the drug record's `lactation_safety`.
            Both existed and neither was read by any rule: the system collected
            lactation status from clinicians and discarded it.
  DIAG-002  acts on a matched syndrome that names no agent to avoid. Four of the
            nine syndromes held here are in that position, so before this rule they
            matched a diagnosis and changed nothing.

The tests below pin the behaviour that makes them safe rather than noisy: each
fires only on its own trigger, and DIAG-002 stays silent whenever the guideline
does name the prescribed agent.
"""
import pytest

from backend.guidelines.knowledge_base import knowledge_base
from backend.models.schemas import (
    AgeCategory, LactationStatus, PatientCreate, PregnancyStatus,
    PrescriptionCreate, PrescriptionItem,
)
from backend.rules.engine import ClinicalRuleEngine

engine = ClinicalRuleEngine()


def _patient(lactation=LactationStatus.CONFIRMED_NOT_LACTATING, **kw):
    base = dict(
        patient_id="T-1", age=30, age_category=AgeCategory.ADULT, sex="FEMALE",
        allergies=[], medical_history=[], allergy_status_known=True,
        renal_status_known=True, hepatic_status_known=True,
        pregnancy_status=PregnancyStatus.CONFIRMED_NOT_PREGNANT,
        lactation_status=lactation, active_medications=[],
    )
    base.update(kw)
    return PatientCreate(**base)


def _rule_ids(patient, diagnosis, drug):
    rx = PrescriptionCreate(
        patient_id=patient.patient_id, diagnosis=diagnosis,
        items=[PrescriptionItem(medication_name=drug, dose=100, unit="mg",
                                route="PO", frequency="BD", duration_days=7)],
    )
    return [w.rule_id for w in engine.evaluate_prescription(patient, rx, "RX-T")]


# ---------------------------------------------------------------------------
# Syndromes derived from held documents
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("diagnosis,expected_source", [
    ("Scrub Typhus", "DHR-ICMR-RICKETTSIAL-2015"),
    ("Rickettsial fever", "DHR-ICMR-RICKETTSIAL-2015"),
    ("Leptospirosis", "NCDC-LEPTOSPIROSIS-2015"),
    ("Acute Bacterial Meningitis", "NCDC-NTG-AMR-2016"),
    ("Enteric fever", "WHO-AWARE-BOOK-2022"),
    ("Typhoid fever", "WHO-AWARE-BOOK-2022"),
])
def test_new_syndromes_match_and_name_their_own_source(diagnosis, expected_source):
    syndrome = knowledge_base.match_syndrome_guideline(diagnosis)
    assert syndrome, f"{diagnosis} matched no syndrome"
    assert syndrome["source_document_id"] == expected_source


def test_every_syndrome_declares_where_it_came_from():
    """
    The file is labelled ICMR "Edition 3" at the document level. Entries drawn from
    NCDC and WHO documents must not inherit that attribution silently.
    """
    for key, entry in knowledge_base.icmr_guidelines["syndromes"].items():
        assert entry.get("source_document_id"), f"{key} declares no source"


@pytest.mark.parametrize("diagnosis", [
    "Viral meningitis", "Tuberculous meningitis", "Pyelonephritis",
])
def test_excluded_diagnoses_still_match_nothing(diagnosis):
    """The held antibacterial guidance does not apply to these."""
    assert knowledge_base.match_syndrome_guideline(diagnosis) is None


# ---------------------------------------------------------------------------
# VULN-005: lactation
# ---------------------------------------------------------------------------

def test_lactation_rule_fires_for_a_lactating_patient():
    ids = _rule_ids(_patient(lactation=LactationStatus.LACTATING),
                    "Leptospirosis", "Doxycycline")
    assert "VULN-005" in ids


def test_lactation_rule_is_silent_when_the_patient_is_not_lactating():
    ids = _rule_ids(_patient(), "Leptospirosis", "Doxycycline")
    assert "VULN-005" not in ids


def test_lactation_warning_quotes_the_drug_record_rather_than_asserting_its_own():
    """
    The rule carries no clinical claim of its own: it surfaces whatever the drug
    knowledge base records. If the knowledge base says nothing, nothing is claimed.
    """
    patient = _patient(lactation=LactationStatus.LACTATING)
    rx = PrescriptionCreate(
        patient_id="T-1", diagnosis="Leptospirosis",
        items=[PrescriptionItem(medication_name="Doxycycline", dose=100, unit="mg",
                                route="PO", frequency="BD", duration_days=7)],
    )
    warnings = [w for w in engine.evaluate_prescription(patient, rx, "RX-T")
                if w.rule_id == "VULN-005"]
    assert warnings
    recorded = knowledge_base.get_drug_info("doxycycline")["lactation_safety"]
    assert recorded in warnings[0].recommendation


# ---------------------------------------------------------------------------
# DIAG-002: agent not among the guideline's named options
# ---------------------------------------------------------------------------

def test_agent_not_named_by_the_guideline_is_reported():
    ids = _rule_ids(_patient(), "Scrub Typhus", "Amoxicillin")
    assert "DIAG-002" in ids


@pytest.mark.parametrize("diagnosis,drug", [
    ("Scrub Typhus", "Doxycycline"),
    ("Acute Bacterial Meningitis", "Ceftriaxone"),
    ("Pneumonia", "Amoxicillin"),
    ("Enteric fever", "Azithromycin"),
])
def test_an_agent_the_guideline_does_name_is_not_reported(diagnosis, drug):
    assert "DIAG-002" not in _rule_ids(_patient(), diagnosis, drug)


def test_no_syndrome_match_means_no_diag_002():
    """DIAG-002 compares against a guideline. With no guideline there is nothing to say."""
    assert "DIAG-002" not in _rule_ids(_patient(), "Pyelonephritis", "Amoxicillin")


def test_diag_002_is_low_severity():
    """
    "Not named by this guideline" is not "wrong". A guideline lists common options,
    not every acceptable one, and raising this above LOW would manufacture alarm
    out of an absence.
    """
    rule = knowledge_base.get_rule_by_id("DIAG-002")
    assert rule["severity"] == "LOW"


def test_new_rules_ship_pending_clinical_review():
    for rule_id in ("VULN-005", "DIAG-002"):
        rule = knowledge_base.get_rule_by_id(rule_id)
        assert rule["approval_status"] == "PENDING_CLINICAL_REVIEW"
        assert rule["approved_by"] is None


# ---------------------------------------------------------------------------
# Rules grounded in ICMR-STG-2019-ED2 (a hash-verified PDF held here)
#
# These exist because the knowledge base was UNDER-claiming its own coverage.
# The records for voriconazole and primaquine both stated that no held document
# gave their pregnancy, interaction, renal or hepatic data. ICMR-STG-2019-ED2
# states all of it, and had done all along, so COVERAGE-001 was reporting safety
# checks as unevaluable while the evidence sat in the corpus.
# ---------------------------------------------------------------------------

def _patient_with(**kw):
    return _patient(**kw)


def test_voriconazole_contraindicated_combination_is_critical():
    """
    ICMR-STG-2019-ED2 p.184 lists this as CONTRAINDICATED. Routing it through the
    generic interaction rule would report it as an ordinary interaction, which is a
    weaker claim than the source makes.
    """
    patient = _patient()
    patient.active_medications = ["Rifampicin"]
    rx = PrescriptionCreate(
        patient_id="T-1", diagnosis="Candidemia",
        items=[PrescriptionItem(medication_name="Voriconazole", dose=200, unit="mg",
                                route="IV", frequency="BD", duration_days=7)],
    )
    warnings = [w for w in engine.evaluate_prescription(patient, rx, "RX-T")
                if w.rule_id == "DDI-005"]
    assert warnings, "voriconazole + rifampicin did not raise DDI-005"
    assert warnings[0].severity.value == "CRITICAL"


@pytest.mark.parametrize("interacting", ["Rifampicin", "Carbamazepine", "Phenytoin"])
def test_each_listed_contraindicated_agent_is_detected(interacting):
    patient = _patient()
    patient.active_medications = [interacting]
    rx = PrescriptionCreate(
        patient_id="T-1", diagnosis="Candidemia",
        items=[PrescriptionItem(medication_name="Voriconazole", dose=200, unit="mg",
                                route="IV", frequency="BD", duration_days=7)],
    )
    assert any(w.rule_id == "DDI-005"
               for w in engine.evaluate_prescription(patient, rx, "RX-T")), interacting


def test_voriconazole_alone_raises_no_interaction_warning():
    patient = _patient()
    rx = PrescriptionCreate(
        patient_id="T-1", diagnosis="Candidemia",
        items=[PrescriptionItem(medication_name="Voriconazole", dose=200, unit="mg",
                                route="IV", frequency="BD", duration_days=7)],
    )
    assert not any(w.rule_id == "DDI-005"
                   for w in engine.evaluate_prescription(patient, rx, "RX-T"))


def _primaquine_ids(patient):
    rx = PrescriptionCreate(
        patient_id="T-1", diagnosis="Malaria",
        items=[PrescriptionItem(medication_name="Primaquine", dose=15, unit="mg",
                                route="PO", frequency="OD", duration_days=14)],
    )
    return [w.rule_id for w in engine.evaluate_prescription(patient, rx, "RX-T")]


def test_primaquine_is_flagged_in_pregnancy():
    assert "VULN-006" in _primaquine_ids(
        _patient(pregnancy_status=PregnancyStatus.PREGNANT_TRIMESTER_2))


def test_primaquine_is_flagged_in_lactation():
    """
    The source excludes women breastfeeding infants UNDER 6 MONTHS. This system does
    not record the infant's age, so the alert is raised for any documented lactation
    and the recommendation says the age must be confirmed.
    """
    patient = _patient(lactation=LactationStatus.LACTATING)
    rx = PrescriptionCreate(
        patient_id="T-1", diagnosis="Malaria",
        items=[PrescriptionItem(medication_name="Primaquine", dose=15, unit="mg",
                                route="PO", frequency="OD", duration_days=14)],
    )
    warnings = [w for w in engine.evaluate_prescription(patient, rx, "RX-T")
                if w.rule_id == "VULN-006"]
    assert warnings
    assert "under 6 months" in warnings[0].recommendation


def test_g6pd_rule_fires_only_when_status_is_undocumented():
    assert "VULN-007" in _primaquine_ids(_patient())
    assert "VULN-007" not in _primaquine_ids(
        _patient(medical_history=["G6PD deficiency screened - normal"]))


def test_g6pd_rule_accepts_a_status_of_either_kind():
    """The rule asks whether the status is known, not what it is."""
    for history in (["G6PD normal"], ["G6PD deficient"], ["glucose-6-phosphate dehydrogenase tested"]):
        assert "VULN-007" not in _primaquine_ids(_patient(medical_history=history)), history


def test_primaquine_rules_do_not_fire_for_other_drugs():
    patient = _patient(pregnancy_status=PregnancyStatus.PREGNANT_TRIMESTER_2)
    rx = PrescriptionCreate(
        patient_id="T-1", diagnosis="Malaria",
        items=[PrescriptionItem(medication_name="Doxycycline", dose=100, unit="mg",
                                route="PO", frequency="BD", duration_days=7)],
    )
    ids = [w.rule_id for w in engine.evaluate_prescription(patient, rx, "RX-T")]
    assert "VULN-006" not in ids and "VULN-007" not in ids


def test_closed_coverage_gaps_are_no_longer_reported_as_unassessed():
    """
    The point of closing the gaps: COVERAGE-001 must stop naming domains the corpus
    demonstrably covers, while still naming the ones it does not.
    """
    vori = knowledge_base.get_drug_info("voriconazole")
    prim = knowledge_base.get_drug_info("primaquine")
    for closed in ("interactions", "hepatic_dosing", "renal_dosing"):
        assert closed not in vori["coverage_gaps"], closed
    for closed in ("pregnancy_category", "lactation_safety"):
        assert closed not in prim["coverage_gaps"], closed
    # And the honest remainder is still declared.
    assert prim["coverage_gaps"], "primaquine should still declare its open gaps"
    assert vori["coverage_gaps"], "voriconazole should still declare its open gaps"


def test_the_stale_no_held_evidence_claim_is_gone():
    for key in ("voriconazole", "primaquine"):
        note = knowledge_base.get_drug_info(key).get("coverage_note", "")
        assert "That was incorrect" in note, key


def test_stg_2019_rules_ship_pending_clinical_review():
    for rule_id in ("DDI-005", "VULN-006", "VULN-007"):
        rule = knowledge_base.get_rule_by_id(rule_id)
        assert rule["approval_status"] == "PENDING_CLINICAL_REVIEW"
        assert rule["approved_by"] is None


# ---------------------------------------------------------------------------
# Hepatitis antivirals, and the pregnancy contraindications they made actionable
# ---------------------------------------------------------------------------

HEPATITIS_ANTIVIRALS = [
    "tenofovir", "tenofovir_alafenamide", "entecavir", "lamivudine",
    "sofosbuvir", "daclatasvir", "velpatasvir", "ribavirin",
]


@pytest.mark.parametrize("key", HEPATITIS_ANTIVIRALS)
def test_hepatitis_antiviral_is_held_and_declares_its_own_gaps(key):
    """
    Added from a national treatment guideline, which states indication, dose and a
    few contraindications and nothing else. What it does not state stays declared as
    a gap rather than being filled from memory.
    """
    drug = knowledge_base.get_drug_info(key)
    assert drug, f"{key} not in the knowledge base"
    assert drug["knowledge_coverage"] == "PARTIAL"
    assert drug["coverage_gaps"], f"{key} claims complete coverage"
    assert drug["dosing_from_held_sources"]["source_document_id"] == "MOHFW-NVHCP-VIRAL-HEPATITIS-2018"


def _hep_ids(drugs, meds=None, preg=PregnancyStatus.CONFIRMED_NOT_PREGNANT):
    patient = _patient(pregnancy_status=preg)
    patient.active_medications = meds or []
    rx = PrescriptionCreate(
        patient_id="T-1", diagnosis="Chronic Hepatitis C",
        items=[PrescriptionItem(medication_name=d, dose=400, unit="mg", route="PO",
                                frequency="OD", duration_days=84) for d in drugs],
    )
    return [w.rule_id for w in engine.evaluate_prescription(patient, rx, "RX-T")]


def test_sofosbuvir_with_amiodarone_is_contraindicated():
    """p.38: "significant bradyarrhythmias ... therefore it is contraindicated"."""
    assert "DDI-005" in _hep_ids(["Sofosbuvir"], ["Amiodarone"])


@pytest.mark.parametrize("daa", ["Sofosbuvir", "Daclatasvir", "Velpatasvir"])
@pytest.mark.parametrize("inducer", ["Carbamazepine", "Phenytoin"])
def test_cyp_inducers_are_contraindicated_with_every_daa(daa, inducer):
    """p.39: "contraindicated with all regimens"."""
    assert "DDI-005" in _hep_ids([daa], [inducer]), f"{daa} + {inducer}"


@pytest.mark.parametrize("regimen", [
    ["Sofosbuvir", "Daclatasvir"],
    ["Sofosbuvir", "Velpatasvir"],
    ["Sofosbuvir", "Velpatasvir", "Ribavirin"],
])
def test_the_guidelines_own_regimens_raise_no_duplication_warning(regimen):
    """
    DUP-002 fires on a shared super_class. Filing every direct-acting antiviral under
    one class would make the engine flag the exact combinations the guideline
    recommends, so they are classed by target instead.
    """
    assert "DUP-002" not in _hep_ids(regimen), regimen


def test_two_agents_against_the_same_target_are_still_flagged():
    assert "DUP-002" in _hep_ids(["Daclatasvir", "Velpatasvir"])


def test_a_drug_with_no_stated_renal_threshold_does_not_crash_the_engine():
    """
    The hepatitis guideline says renal function matters for ribavirin and gives no
    number. Recording that honestly as a null threshold used to raise TypeError in
    _check_renal and take down the entire analysis for the prescription.
    """
    patient = _patient()
    patient.egfr_ml_min = 20
    rx = PrescriptionCreate(
        patient_id="T-1", diagnosis="Chronic Hepatitis C",
        items=[PrescriptionItem(medication_name="Ribavirin", dose=800, unit="mg",
                                route="PO", frequency="OD", duration_days=84)],
    )
    assert engine.evaluate_prescription(patient, rx, "RX-T") is not None


# -- VULN-008 ---------------------------------------------------------------

@pytest.mark.parametrize("drug", ["Gentamicin", "Ribavirin", "Sofosbuvir", "Entecavir"])
def test_recorded_pregnancy_contraindication_now_fires(drug):
    assert "VULN-008" in _hep_ids([drug], preg=PregnancyStatus.PREGNANT_TRIMESTER_2), drug


@pytest.mark.parametrize("drug", ["Ciprofloxacin", "Doxycycline", "Primaquine"])
def test_no_double_pregnancy_warning_where_a_specific_rule_exists(drug):
    ids = _hep_ids([drug], preg=PregnancyStatus.PREGNANT_TRIMESTER_2)
    assert "VULN-008" not in ids, f"{drug} raised both a specific rule and VULN-008"


@pytest.mark.parametrize("drug", ["Nitrofurantoin", "Clarithromycin", "Amoxicillin-Clavulanate"])
def test_a_caution_is_not_treated_as_a_contraindication(drug):
    """
    Nitrofurantoin is the sharp case: its contraindication is real but applies at
    38-42 weeks gestation, and this system records only a trimester. A keyword match
    on the prose would raise a first-trimester alarm from a true sentence about term.
    """
    assert "VULN-008" not in _hep_ids([drug], preg=PregnancyStatus.PREGNANT_TRIMESTER_1), drug


def test_pregnancy_rule_is_silent_outside_pregnancy():
    assert "VULN-008" not in _hep_ids(["Gentamicin"])


def test_every_excluded_drug_records_why_it_was_excluded():
    """An omission nobody can see is indistinguishable from an oversight."""
    for key in ("nitrofurantoin", "clarithromycin", "amoxicillin_clavulanate"):
        drug = knowledge_base.get_drug_info(key)
        assert drug.get("pregnancy_contraindicated") is False, key
        assert drug.get("pregnancy_contraindication_basis"), key
