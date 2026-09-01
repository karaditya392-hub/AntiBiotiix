"""
ICMR Treatment Guidelines 2022-23 edition syndrome index test suite.

The seven operator-supplied chapter files are Google Docs exports carrying no issuing
organization, author or date of their own. The operator has attested they are chapters of
the ICMR 2022-23 edition, and that attribution is recorded as resting on attestation
rather than on any verification this repository can perform.

The load-bearing assertions here are the provenance ones, and they turn on keeping two
claims apart:

  * the EDITION attribution is operator-attested and unverified, and no record may carry
    a page in the 2022-23 document, because no official 2022-23 PDF is held;
  * the PRIOR-EDITION cross-reference is independently verifiable against the ingested,
    hash-verified 2019 corpus, and is re-checked here from that corpus rather than from
    the scores stored in the file.

A cross-reference is never evidence for the edition claim, and the tests below assert
that the two never leak into one another.
"""
import json
import re

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

AUTHORITY = "ICMR-STG-2022-23"
PRIOR = "ICMR-STG-2019-ED2"


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    init_db()


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def test_authority_is_the_2022_23_edition_and_declares_itself_unverified():
    coll = knowledge_base.stg_syndromes
    assert coll["collection_id"] == "ICMR-STG-2022-23-SYNDROMES"
    assert coll["authority_document_id"] == AUTHORITY
    assert coll["prior_edition_document_id"] == PRIOR

    auth = coll["documents"][AUTHORITY]
    assert auth["version"] == "2022-23 edition"
    assert auth["official_pdf_held"] is False
    assert auth["file_sha256"] is None
    assert auth["provenance_basis"] == "OPERATOR_ATTESTATION"
    assert "cannot be cryptographically or bibliographically verified" in auth["provenance_statement"]
    assert auth["coverage_caveat"], "the seven-chapter limit must be stated"

    for cond in coll["conditions"].values():
        assert cond["source_document_id"] == AUTHORITY
        assert cond["attribution_basis"] == "OPERATOR_ATTESTATION"


def test_transcriptions_are_recorded_but_never_used_as_authorities():
    coll = knowledge_base.stg_syndromes
    sources = coll["transcription_sources"]
    assert len(sources) == 7

    for name, meta in sources.items():
        assert len(meta["sha256"]) == 64
        assert meta["maps_to_chapter"]
        # A transcription must never be promoted to a source_document_id.
        for cond in coll["conditions"].values():
            assert cond["source_document_id"] != name

    note = coll["provenance_note"]
    assert "no issuing organization, author or date of their own" in note
    assert "never as independent authorities" in note
    assert "NO record in this file carries a page number in the authority document" in note


def test_no_condition_claims_a_page_in_the_unheld_2022_23_document():
    """
    No official 2022-23 PDF is held, so a page number in that edition cannot be
    substantiated. Any page shown must belong to the prior edition instead.
    """
    conditions = knowledge_base.stg_syndromes["conditions"]
    assert len(conditions) == 82

    for key, cond in conditions.items():
        assert cond["source_page"] is None, (
            f"{key} claims a page in an edition this repository does not hold"
        )
        assert cond["source_page_status"] == "NO_OFFICIAL_PDF_HELD_PAGE_CITATION_UNAVAILABLE"


def test_prior_edition_pages_are_labelled_as_such_never_as_this_edition():
    for key, cond in knowledge_base.stg_syndromes["conditions"].items():
        xref = cond.get("prior_edition_cross_reference")
        if xref is None:
            assert cond.get("edition_note"), f"{key} has neither a cross-reference nor an edition note"
            continue
        assert xref["document_id"] == PRIOR
        assert 1 <= xref["page"] <= 206, f"{key} cross-references outside the 206-page 2019 PDF"
        assert "NOT a page of the 2022-23 edition" in xref["note"]


def test_cross_referenced_text_really_occurs_in_the_2019_corpus():
    """
    Independent re-verification of the CROSS-REFERENCE only: recompute the match from
    the RAG corpus rather than trusting the score stored in the file. This says nothing
    about the 2022-23 attribution, which no test in this repository can confirm.
    """
    import io
    import os

    rag_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "backend", "guidelines", "data", "rag", "ICMR-STG-2019-ED2.json",
    )
    with io.open(rag_path, encoding="utf-8") as f:
        doc = json.load(f)

    def norm(t):
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())).strip()

    corpus = norm(" ".join(c.get("text") or "" for c in doc["chunks"]))
    tokens = corpus.split()
    shingles = set(" ".join(tokens[i:i + 4]) for i in range(len(tokens) - 4))

    for key, cond in knowledge_base.stg_syndromes["conditions"].items():
        if not cond.get("prior_edition_cross_reference"):
            continue
        toks = norm(cond["verbatim_extract"]).split()
        grams = [" ".join(toks[i:i + 4]) for i in range(len(toks) - 4)]
        if len(grams) < 4:
            continue
        hit = sum(1 for g in grams if g in shingles) / len(grams)
        assert hit >= 0.60, (
            f"{key} carries a 2019 cross-reference but only {hit:.0%} of its text is in that corpus"
        )


def test_content_absent_from_the_prior_edition_is_marked_new_in_this_one():
    """
    Ceftazidime-avibactam appears in the supplied Hospital Acquired Infection chapter,
    but the string 'avibactam' does not occur anywhere in the 2019 corpus. Under the
    2022-23 attribution that is the expected signature of new content, so it carries no
    cross-reference and states why.
    """
    dosing = knowledge_base.drugs_db["ceftazidime_avibactam"]["dosing_from_held_sources"]
    assert dosing["source_document_id"] == AUTHORITY
    assert dosing["prior_edition_cross_reference"] is None
    assert "new or revised content introduced in the 2022-23 edition" in dosing["edition_note"]


# ---------------------------------------------------------------------------
# Coverage of the seven supplied chapters
# ---------------------------------------------------------------------------

def test_all_seven_chapters_contributed_conditions():
    chapters = {c["chapter"] for c in knowledge_base.stg_syndromes["conditions"].values()}
    assert len(chapters) == 7
    for expected in ("5. Intra-abdominal", "6. Skin and soft tissue", "7. Bone and joint",
                     "8. Central nervous system", "9. Urinary tract",
                     "10. Hospital acquired", "11. Infections in the immunocompromised"):
        assert any(ch.startswith(expected) for ch in chapters), f"missing chapter {expected}"


@pytest.mark.parametrize("diagnosis,expected_key", [
    # Chapter 5
    ("liver abscess", "iai_liver_abscess"),
    ("cholangitis", "iai_cholangitis_cholecystitis"),
    ("healthcare associated intra-abdominal infection", "iai_healthcare_associated"),
    ("bacillary dysentery", "acute_bloody_diarrhea"),
    ("giardiasis", "diarrhea_giardiasis"),
    # Chapter 6
    ("necrotizing fasciitis", "necrotizing_fasciitis"),
    ("Ludwig's angina", "ludwigs_angina"),
    ("Lemierre syndrome", "lemierre_syndrome"),
    # Chapter 7
    ("prosthetic joint infection", "prosthetic_joint_infection"),
    ("septic arthritis", "septic_arthritis_native"),
    ("chronic osteomyelitis", "chronic_osteomyelitis"),
    # Chapter 8
    ("acute bacterial meningitis", "acute_bacterial_meningitis"),
    ("post-neurosurgical meningitis", "healthcare_associated_meningitis"),
    ("CSF shunt infection", "csf_shunt_infection"),
    # Chapter 9
    ("acute pyelonephritis", "acute_pyelonephritis"),
    ("asymptomatic bacteriuria", "asymptomatic_bacteriuria"),
    ("acute prostatitis", "acute_prostatitis"),
    # Chapter 10
    ("ventilator associated pneumonia", "hap_vap"),
    ("CLABSI", "clabsi"),
    ("C. difficile infection", "clostridioides_difficile_infection"),
    ("catheter associated urinary tract infection", "catheter_associated_uti"),
    # Chapter 11
    ("febrile neutropenia", "febrile_neutropenia"),
    ("mucormycosis", "mucormycosis"),
    ("pneumocystis pneumonia", "pneumocystis_jirovecii_pneumonia"),
])
def test_diagnosis_dispatch(diagnosis, expected_key):
    match = knowledge_base.match_stg_condition(diagnosis)
    assert match is not None, f"no ICMR 2019 condition matched '{diagnosis}'"
    assert match["condition_key"] == expected_key


def test_severity_tiers_carry_the_escalation_the_source_states():
    hap = knowledge_base.get_stg_condition("hap_vap")
    tiers = hap["severity_tiers"]
    assert "Cefoperazone-sulbactam or Piperacillin-tazobactam, either alone or with Amikacin" in \
        tiers["EMPIRIC_EARLY_ONSET"]["medications"]
    assert any("Colistin" in m for m in tiers["EMPIRIC_LATE_ONSET"]["medications"])
    assert tiers["MRSA"]["medications"] == ["Inj. Linezolid"]

    cdi = knowledge_base.get_stg_condition("clostridioides_difficile_infection")
    assert "Vancomycin 125 mg given 4 times daily for 10 days" in \
        cdi["severity_tiers"]["INITIAL_NON_SEVERE"]["medications"]


def test_negative_recommendations_are_preserved_not_dropped():
    """
    Guidance that an agent must NOT be used is as clinically important as guidance
    that it should. These must survive ingestion intact.
    """
    watery = knowledge_base.get_stg_condition("acute_watery_diarrhea")
    assert watery["medications"]["first_choice"] == ["No antimicrobial therapy - oral rehydration solution (ORS)"]

    asb = knowledge_base.get_stg_condition("asymptomatic_bacteriuria")
    assert asb["medications"]["first_choice"] == ["No antibiotic treatment required"]

    bronchitis = knowledge_base.get_stg_condition("acute_bronchitis_sot")
    assert bronchitis["medications"]["empiric"] == ["Antibiotics not needed"]

    hiv_abscess = knowledge_base.get_stg_condition("brain_abscess_immunocompromised")
    assert hiv_abscess["medications"]["empiric"] == ["No empiric therapy"]

    faropenem = knowledge_base.drugs_db["faropenem"]
    assert "should NOT be used as step-down therapy" in faropenem["indications_from_held_sources"][0]


def test_india_specific_resistance_caveats_are_preserved():
    sbp = knowledge_base.get_stg_condition("spontaneous_bacterial_peritonitis_stg")
    assert "resistance" in sbp["caveat"].lower()
    assert "20%" in sbp["caveat"]

    dysentery = knowledge_base.get_stg_condition("acute_bloody_diarrhea")
    assert "no longer drugs of choice in India" in dysentery["comments"]


# ---------------------------------------------------------------------------
# Medications
# ---------------------------------------------------------------------------

STG_DRUGS = [
    "cefazolin", "cefoperazone_sulbactam", "ampicillin_sulbactam", "ertapenem", "imipenem",
    "amikacin", "fosfomycin", "colistin", "polymyxin_b", "tigecycline", "teicoplanin",
    "moxifloxacin", "ofloxacin", "norfloxacin", "ceftazidime", "cefepime", "cefotaxime",
    "ampicillin", "benzathine_penicillin", "chloramphenicol", "rifaximin", "primaquine",
    "fluconazole", "voriconazole", "micafungin", "anidulafungin", "caspofungin",
    "amphotericin_b", "flucytosine", "acyclovir", "valacyclovir", "ganciclovir",
    "valganciclovir", "foscarnet", "cidofovir", "oseltamivir", "artesunate",
    "ceftazidime_avibactam", "aztreonam", "faropenem",
]


def test_all_referenced_medications_were_added():
    # Counts the drugs THIS batch contributed, not the size of the whole knowledge
    # base. The global total was pinned at 69 here, which meant adding a drug from
    # any other source failed this test for a reason that had nothing to do with the
    # 2022-23 syndromes it exists to guard -- the hepatitis antivirals from
    # MOHFW-NVHCP-VIRAL-HEPATITIS-2018 broke it that way.
    from_this_authority = [
        key for key, info in knowledge_base.drugs_db.items()
        if (info.get("dosing_from_held_sources") or {}).get("source_document_id") == AUTHORITY
    ]
    assert len(from_this_authority) == 40
    for key in STG_DRUGS:
        info = knowledge_base.drugs_db[key]
        assert info["knowledge_coverage"] == "PARTIAL"
        assert info["dosing_from_held_sources"]["source_document_id"] == AUTHORITY
        assert info["dosing_from_held_sources"]["source_page"] is None
        assert info["unverified_sources"] == []


@pytest.mark.parametrize("written,expected", [
    ("Imipenem-cilastatin", "imipenem"),
    ("Cefoperazone", "cefoperazone_sulbactam"),
    ("Ertapenam", "ertapenem"),          # the spelling used in the source table
    ("Polymyxin", "polymyxin_b"),
    ("Colistimethate", "colistin"),
    ("Liposomal amphotericin B", "amphotericin_b"),
    ("Aciclovir", "acyclovir"),
    ("Valgancyclovir", "valganciclovir"),
    ("Tamiflu", "oseltamivir"),
])
def test_medication_aliases_resolve(written, expected):
    assert knowledge_base.normalize_drug_name(written) == expected
    assert knowledge_base.get_drug_info(written) is not None


def test_reserve_agents_trigger_stewardship_review():
    """Colistin, polymyxin B, tigecycline and ceftazidime-avibactam are RESERVE."""
    for key in ("colistin", "polymyxin_b", "tigecycline", "ceftazidime_avibactam"):
        assert knowledge_base.get_aware_category(key) == "RESERVE"

    patient = PatientCreate(
        patient_id="TEST-STG-RES", age=60, allergy_status_known=True,
        allergies=[], active_medications=[],
    )
    presc = PrescriptionCreate(
        patient_id="TEST-STG-RES",
        items=[PrescriptionItem(medication_name="Colistin", dose=45, unit="mg", route="IV", frequency="Q12H")],
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    steward = [w for w in warnings if w.rule_id == "STEWARD-001"]
    assert len(steward) == 1
    assert steward[0].severity == SeverityLevel.HIGH


def test_non_antibacterials_are_not_given_an_invented_aware_group():
    for key in ("fluconazole", "voriconazole", "acyclovir", "ganciclovir", "artesunate",
                "micafungin", "amphotericin_b"):
        info = knowledge_base.drugs_db[key]
        assert info["aware_category"] == "NOT_APPLICABLE"
        assert info["aware_classification_status"] == "NOT_AN_ANTIBACTERIAL"


def test_aware_groups_that_are_held_are_carried_through():
    expected = {
        "cefazolin": "ACCESS", "ampicillin": "ACCESS", "benzathine_penicillin": "ACCESS",
        "cefotaxime": "WATCH", "ceftazidime": "WATCH", "cefepime": "WATCH",
        "moxifloxacin": "WATCH", "imipenem": "WATCH",
        "colistin": "RESERVE", "polymyxin_b": "RESERVE", "tigecycline": "RESERVE",
    }
    for key, group in expected.items():
        assert knowledge_base.drugs_db[key]["aware_category"] == group


def test_new_beta_lactams_reach_the_allergy_rules():
    patient = PatientCreate(
        patient_id="TEST-STG-ALG", age=50, allergy_status_known=True,
        allergies=["Penicillin"], active_medications=[],
    )
    presc = PrescriptionCreate(
        patient_id="TEST-STG-ALG",
        items=[
            PrescriptionItem(medication_name="Cefazolin", dose=2, unit="g", route="IV", frequency="Q8H"),
            PrescriptionItem(medication_name="Ampicillin-sulbactam", dose=3, unit="g", route="IV", frequency="Q6H"),
        ],
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    fired = {(w.rule_id, w.prescribed_drug) for w in warnings}
    assert ("ALLERGY-003", "Cefazolin") in fired
    assert ("ALLERGY-002", "Ampicillin-sulbactam") in fired


def test_partial_coverage_failsafe_applies_to_the_new_agents():
    patient = PatientCreate(
        patient_id="TEST-STG-COV", age=70, egfr_ml_min=20.0, child_pugh_class="C",
        allergy_status_known=True, allergies=[], active_medications=[],
    )
    presc = PrescriptionCreate(
        patient_id="TEST-STG-COV",
        items=[PrescriptionItem(medication_name="Ertapenem", dose=1, unit="g", route="IV", frequency="Q24H")],
    )
    warnings = rule_engine.evaluate_prescription(patient, presc)
    cov = [w for w in warnings if w.rule_id == "COVERAGE-001"]
    assert len(cov) == 1
    assert cov[0].interacting_factor == "Partial Knowledge Base Coverage"
    assert "absence of data, not a finding of safety" in cov[0].evidence.verbatim_passage


def test_supportive_agents_are_not_treated_as_antimicrobials():
    for name in ("Loperamide", "ORS", "Noradrenaline", "IVIG"):
        assert knowledge_base.is_known_non_antimicrobial(name), f"{name} should not raise coverage warnings"


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------

def test_stg_index_endpoint_carries_provenance():
    res = client.get("/api/guidelines/stg-conditions")
    assert res.status_code == 200
    data = res.json()
    assert data["total_conditions"] == 82
    assert data["authority_document_id"] == AUTHORITY
    assert data["authority_document"]["official_pdf_held"] is False
    assert data["prior_edition_document_id"] == PRIOR
    assert len(data["transcription_sources"]) == 7
    assert data["verification_note"]


def test_stg_lookup_by_diagnosis_and_by_key():
    res = client.get("/api/guidelines/stg-conditions", params={"diagnosis": "acute pyelonephritis"})
    body = res.json()
    assert body["matched"] is True
    assert body["condition"]["medications"]["drug_of_choice"] == ["Piperacillin-tazobactam"]

    res_key = client.get("/api/guidelines/stg-conditions", params={"condition": "febrile_neutropenia"})
    assert res_key.status_code == 200

    assert client.get("/api/guidelines/stg-conditions", params={"condition": "nope"}).status_code == 404


def test_analysis_response_separates_the_three_corpora():
    create_res = client.post("/api/prescriptions", json={
        "patient_id": "PATIENT-003",
        "diagnosis": "Acute pyelonephritis",
        "raw_text": "Piperacillin-tazobactam 4.5g IV q6h",
        "items": [{"medication_name": "Piperacillin-Tazobactam", "dose": 4.5, "unit": "g",
                   "route": "IV", "frequency": "Q6H"}],
        "clinician_id": "DOC-STG-01",
        "clinician_role": "ATTENDING_PHYSICIAN",
    })
    assert create_res.status_code == 200
    presc_id = create_res.json()["prescription_id"]

    res = client.post(f"/api/prescriptions/{presc_id}/analyze")
    assert res.status_code == 200
    data = res.json()

    stg = data["stg_2022_23_condition"]
    assert stg is not None
    assert stg["condition_name"] == "Acute pyelonephritis"
    assert stg["source_document_id"] == AUTHORITY
    assert stg["source_page"] is None
    assert stg["attribution_basis"] == "OPERATOR_ATTESTATION"
    assert stg["authority_document"]["official_pdf_held"] is False

    # Each corpus keeps its own field; none is folded into another.
    assert "stw_workflow_condition" in data
    assert "guideline_recommendations" in data
    for rec in data["guideline_recommendations"]:
        assert "condition_key" not in rec
