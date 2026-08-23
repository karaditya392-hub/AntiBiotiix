"""
ICMR Standard Treatment Workflows (2022) Test Suite.

Covers the conditions and medications ingested from the two held STW PDFs:
  - ICMR-STW-VOL3-2022      (Standard Treatment Workflows of India, Vol. 3, 2022)
  - ICMR-STW-PTB-EPTB-2022  (Paediatric and Extrapulmonary Tuberculosis, 2022)

The load-bearing assertions here are the provenance ones. This collection is a
DIFFERENT ICMR publication from the antimicrobial treatment guidelines, and the
partially-covered drugs it introduces must never be allowed to convert a loud
"not assessed" into a silent all-clear.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.guidelines.knowledge_base import knowledge_base
from backend.models.database import init_db
from backend.models.schemas import (
    PatientCreate,
    PrescriptionCreate,
    PrescriptionItem,
    SeverityLevel,
)
from backend.rules.engine import rule_engine

client = TestClient(app)

V3 = "ICMR-STW-VOL3-2022"
TB = "ICMR-STW-PTB-EPTB-2022"


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    init_db()


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def test_stw_collection_is_not_merged_into_the_treatment_guidelines():
    """The workflows must stay in their own attribute, under their own identity."""
    assert knowledge_base.stw_collection.get("collection_id") == "ICMR-STW-2022"

    # The antimicrobial treatment guidelines must be untouched by the STW load.
    tg_syndromes = knowledge_base.icmr_guidelines.get("syndromes", {})
    stw_conditions = knowledge_base.stw_collection.get("conditions", {})
    assert not (set(tg_syndromes) & set(stw_conditions)), (
        "An STW condition key collided with a treatment-guideline syndrome key; "
        "the two corpora must remain distinguishable."
    )


def test_every_condition_carries_a_resolvable_source_document_and_page():
    conditions = knowledge_base.stw_collection["conditions"]
    documents = knowledge_base.stw_collection["documents"]
    assert len(conditions) == 29

    for key, cond in conditions.items():
        assert cond.get("source_document_id") in documents, f"{key} has no resolvable document"
        assert cond.get("source_page"), f"{key} has no source page"
        assert cond.get("verbatim_extract"), f"{key} has no verbatim extract"
        assert cond.get("condition_name")
        assert cond.get("presentation"), f"{key} records no clinical presentation"


def test_both_source_documents_record_a_verified_hash():
    for doc_id in (V3, TB):
        doc = knowledge_base.stw_collection["documents"][doc_id]
        assert len(doc["file_sha256"]) == 64
        assert doc["hash_verified"] is True
        assert doc["source_file"].endswith(".pdf")
        # The scope caveat is what stops this being cited as stewardship guidance.
        assert doc["scope_caveat"]


def test_tb_document_is_not_presented_as_an_aware_source():
    doc = knowledge_base.stw_collection["documents"][TB]
    assert "AWaRe" in doc["scope_caveat"]
    for key, cond in knowledge_base.stw_collection["conditions"].items():
        if cond["source_document_id"] == TB:
            assert "aware" not in str(cond.get("medications", {})).lower(), (
                f"{key} attributes AWaRe content to a document that contains none"
            )


# ---------------------------------------------------------------------------
# Condition matching
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("diagnosis,expected", [
    ("Cellulitis of left leg", "Cellulitis"),
    ("impetigo", "Impetigo"),
    ("erysipelas", "Erysipelas"),
    ("cutaneous abscess", "Cutaneous abscess"),
    ("rosacea", "Rosacea"),
    ("diabetic foot ulcer with infection", "Diabetic Foot Infection"),
    ("spontaneous bacterial peritonitis", "Spontaneous Bacterial Peritonitis (in liver failure)"),
    ("empyema thoracis", "Empyema Thoracis in Children"),
    ("genitourinary tuberculosis", "Genitourinary Tuberculosis"),
    ("adult pericardial TB", "Adult Pericardial Tuberculosis"),
])
def test_diagnosis_dispatch(diagnosis, expected):
    match = knowledge_base.match_stw_condition(diagnosis)
    assert match is not None, f"No STW condition matched '{diagnosis}'"
    assert match["condition_name"] == expected


def test_paediatric_tb_never_matches_the_adult_workflow():
    """A child must not be handed an adult regimen; the paediatric pattern wins."""
    paediatric = knowledge_base.match_stw_condition("paediatric tubercular meningitis")
    adult = knowledge_base.match_stw_condition("tubercular meningitis")

    assert paediatric["condition_key"] == "paediatric_tubercular_meningitis"
    assert adult["condition_key"] == "adult_tubercular_meningitis"
    assert paediatric["medications"]["regimen"] != adult["medications"]["regimen"]

    for phrase in ("pediatric abdominal tuberculosis", "childhood lymph node TB"):
        assert knowledge_base.match_stw_condition(phrase)["condition_key"].startswith("paediatric_")


def test_unrelated_diagnosis_returns_nothing_rather_than_a_loose_match():
    for diagnosis in ("community acquired pneumonia", "uncomplicated UTI", ""):
        assert knowledge_base.match_stw_condition(diagnosis) is None


def test_match_attaches_document_and_referenced_regimen():
    match = knowledge_base.match_stw_condition("cellulitis")
    assert match["source_document"]["document_id"] == V3
    assert match["referenced_regimen"]["regimen_id"] == "STW-SSTI-ABX"
    # Severity tiers must carry the escalation the source actually states.
    assert "Inj Ceftriaxone 2g BD" in match["severity_tiers"]["MODERATE"]["medications"]
    assert "Vancomycin" in match["severity_tiers"]["SEVERE"]["medications"]


# ---------------------------------------------------------------------------
# Medications
# ---------------------------------------------------------------------------

NEW_DRUGS = [
    "cloxacillin", "cephalexin", "clindamycin", "erythromycin", "cotrimoxazole",
    "minocycline", "mupirocin", "fusidic_acid", "framycetin",
    "isoniazid", "rifampicin", "pyrazinamide", "ethambutol", "streptomycin",
]


def test_all_workflow_medications_are_present_with_sourced_dosing():
    for key in NEW_DRUGS:
        info = knowledge_base.drugs_db[key]
        assert info["knowledge_coverage"] == "PARTIAL"
        dosing = info["dosing_from_held_sources"]
        assert dosing["source_document_id"] in (V3, TB)
        assert dosing["source_page"]
        assert dosing["verbatim_passage"]
        assert info["unverified_sources"] == []


@pytest.mark.parametrize("written,expected", [
    ("Minocycine", "minocycline"),   # the misspelling printed in the source PDF
    ("cefalexin", "cephalexin"),     # WHO spelling
    ("Septran", "cotrimoxazole"),
    ("co-trimoxazole", "cotrimoxazole"),
    ("INH", "isoniazid"),
    ("Rifampin", "rifampicin"),
    ("Fucidin", "fusidic_acid"),
    ("Soframycin", "framycetin"),
])
def test_drug_name_aliases_resolve(written, expected):
    assert knowledge_base.normalize_drug_name(written) == expected
    assert knowledge_base.get_drug_info(written) is not None


def test_unverifiable_aware_group_is_not_guessed():
    """
    Clindamycin, erythromycin and the antituberculars are not classified by any
    AWaRe source held here. They must fall back to NOT_APPLICABLE rather than
    receiving an invented group that a stewardship rule would then act on.
    """
    for key in ("clindamycin", "erythromycin", "minocycline",
                "isoniazid", "rifampicin", "pyrazinamide", "ethambutol"):
        info = knowledge_base.drugs_db[key]
        assert info["aware_category"] == "NOT_APPLICABLE"
        assert info["aware_classification_status"].startswith("NOT_")
        assert knowledge_base.get_aware_category(key) == "NOT_APPLICABLE"

    # Where a held source DOES classify the drug, the group is carried through.
    for key in ("cloxacillin", "cephalexin", "cotrimoxazole"):
        assert knowledge_base.drugs_db[key]["aware_category"] == "ACCESS"


# ---------------------------------------------------------------------------
# Coverage fail-safe: adding a drug must not create a silent all-clear
# ---------------------------------------------------------------------------

def test_partially_covered_drug_still_raises_the_coverage_failsafe():
    patient = PatientCreate(
        patient_id="TEST-STW-001",
        age=64,
        egfr_ml_min=18.0,
        child_pugh_class="C",
        allergy_status_known=True,
        allergies=[],
        active_medications=[],
    )
    presc = PrescriptionCreate(
        patient_id="TEST-STW-001",
        items=[PrescriptionItem(medication_name="Cloxacillin", dose=500, unit="mg", route="PO", frequency="QID")],
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    cov = [w for w in warnings if w.rule_id == "COVERAGE-001"]

    assert len(cov) == 1, (
        "A drug held for indication and dose only must still raise COVERAGE-001; "
        "otherwise adding it silently cancels the renal/hepatic checks it never had."
    )
    assert cov[0].severity == SeverityLevel.HIGH
    assert cov[0].interacting_factor == "Partial Knowledge Base Coverage"

    passage = cov[0].evidence.verbatim_passage
    assert "renal dosing" in passage
    assert "hepatic dosing" in passage
    assert "absence of data, not a finding of safety" in passage


def test_fully_covered_drug_does_not_raise_a_partial_coverage_warning():
    patient = PatientCreate(
        patient_id="TEST-STW-002", age=40, allergy_status_known=True,
        allergies=[], active_medications=[],
    )
    presc = PrescriptionCreate(
        patient_id="TEST-STW-002",
        items=[PrescriptionItem(medication_name="Amoxicillin", dose=500, unit="mg", route="PO", frequency="TID")],
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    assert not [w for w in warnings if w.rule_id == "COVERAGE-001"]


def test_tb_regimen_adjuncts_do_not_raise_antimicrobial_coverage_warnings():
    """Pyridoxine accompanies every NTEP regimen; it is not an antimicrobial."""
    assert knowledge_base.is_known_non_antimicrobial("Pyridoxine")

    patient = PatientCreate(
        patient_id="TEST-STW-003", age=30, allergy_status_known=True,
        allergies=[], active_medications=[],
    )
    presc = PrescriptionCreate(
        patient_id="TEST-STW-003",
        items=[PrescriptionItem(medication_name="Pyridoxine", dose=10, unit="mg", route="PO", frequency="QD")],
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    assert not [w for w in warnings if w.rule_id == "COVERAGE-001"]


def test_beta_lactam_cross_reactivity_fires_for_the_new_agents():
    """
    Cephalexin does not start with 'cef', so it only reaches ALLERGY-003 via its
    super_class. This asserts the class wiring, not just the presence of a row.
    """
    patient = PatientCreate(
        patient_id="TEST-STW-004", age=45, allergy_status_known=True,
        allergies=["Penicillin"], active_medications=[],
    )
    presc = PrescriptionCreate(
        patient_id="TEST-STW-004",
        items=[
            PrescriptionItem(medication_name="Cephalexin", dose=500, unit="mg", route="PO", frequency="QID"),
            PrescriptionItem(medication_name="Cloxacillin", dose=500, unit="mg", route="PO", frequency="QID"),
        ],
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    fired = {(w.rule_id, w.prescribed_drug) for w in warnings}
    assert ("ALLERGY-003", "Cephalexin") in fired, "Cephalosporin cross-reactivity not detected"
    assert ("ALLERGY-002", "Cloxacillin") in fired, "Penicillin class match not detected"


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------

def test_stw_index_endpoint_returns_provenance_with_every_response():
    res = client.get("/api/guidelines/stw-conditions")
    assert res.status_code == 200
    data = res.json()
    assert data["total_conditions"] == 29
    assert set(data["documents"]) == {V3, TB}
    assert "SEPARATE ICMR publication series" in data["provenance_note"]
    assert data["verbatim_normalization"]


def test_stw_lookup_by_diagnosis_and_by_key():
    res = client.get("/api/guidelines/stw-conditions", params={"diagnosis": "cellulitis"})
    body = res.json()
    assert body["matched"] is True
    assert body["condition"]["source_page"] == 11

    res_key = client.get("/api/guidelines/stw-conditions", params={"condition": "adult_tubercular_meningitis"})
    assert res_key.status_code == 200
    assert "RHZE" in res_key.json()["condition"]["medications"]["regimen"]

    assert client.get("/api/guidelines/stw-conditions", params={"condition": "no_such_key"}).status_code == 404


def test_analysis_response_keeps_workflows_in_their_own_field():
    """
    The workflow condition must not be appended to guideline_recommendations,
    which is reserved for the antimicrobial treatment guidelines.
    """
    create_res = client.post("/api/prescriptions", json={
        "patient_id": "PATIENT-002",
        "diagnosis": "Cellulitis",
        "raw_text": "Cephalexin 500mg PO QID x 7 days",
        "items": [{"medication_name": "Cephalexin", "dose": 500, "unit": "mg", "route": "PO", "frequency": "QID"}],
        "clinician_id": "DOC-STW-01",
        "clinician_role": "ATTENDING_PHYSICIAN",
    })
    assert create_res.status_code == 200
    presc_id = create_res.json()["prescription_id"]

    res = client.post(f"/api/prescriptions/{presc_id}/analyze")
    assert res.status_code == 200
    data = res.json()

    stw = data["stw_workflow_condition"]
    assert stw is not None
    assert stw["condition_name"] == "Cellulitis"
    assert stw["source_document"]["document_id"] == V3

    for rec in data["guideline_recommendations"]:
        assert "condition_key" not in rec, (
            "An STW workflow leaked into guideline_recommendations, where it "
            "would be attributed to the ICMR antimicrobial treatment guidelines."
        )
