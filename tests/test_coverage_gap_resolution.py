"""
Coverage-gap resolution: external evidence for drugs no rule could assess.

The tests that matter are the boundaries. This layer may add content to a gap the
deterministic engine already reported; it may never change which rules fired,
what severity they carry, or what the stewardship rollup decided.

Network is stubbed throughout. A clinical safety suite must not depend on an
external endpoint being up, and a test that passes only when openFDA answers is
a test that reports the weather.
"""
import pytest

from backend.agents import external_safety
from backend.agents.external_safety import (
    STANDING_NOTICE, findings_from_label, resolve_coverage_gap, resolve_uncovered_items,
)
from backend.models.schemas import (
    AgeCategory, LactationStatus, PatientCreate, PregnancyStatus, PrescriptionCreate,
    PrescriptionItem,
)
from backend.rules.engine import ClinicalRuleEngine
from backend.rules.priority import compute_stewardship_priority

LABEL = {
    "openfda": {"brand_name": ["Ceftaroline Fosamil"], "manufacturer_name": ["Apotex Corp."]},
    "contraindications": [
        "4. CONTRAINDICATIONS Ceftaroline fosamil is contraindicated in patients with known "
        "serious hypersensitivity to ceftaroline or other members of the cephalosporin class."
    ],
    "warnings_and_cautions": [
        "Consider dosage adjustments in patients with renal impairment. Direct Coombs' test "
        "seroconversion has been reported."
    ],
    "drug_interactions": [
        "Monitor prothrombin time and INR when warfarin is co-administered. "
        "Metoprolol was not studied."
    ],
    "use_in_specific_populations": [
        "Pregnancy: There are no adequate and well-controlled studies in pregnant women. "
        "Pediatric use has been established in patients aged 2 months and older."
    ],
}


def _patient(**kw):
    base = dict(
        patient_id="PATIENT-EXT", age=67, age_category=AgeCategory.GERIATRIC, weight_kg=70,
        sex="FEMALE", allergies=[], medical_history=[], egfr_ml_min=None,
        child_pugh_class=None, pregnancy_status=PregnancyStatus.CONFIRMED_NOT_PREGNANT,
        lactation_status=LactationStatus.CONFIRMED_NOT_LACTATING, active_medications=[],
    )
    base.update(kw)
    return PatientCreate(**base)


def _item(name="Ceftaroline"):
    return PrescriptionItem(medication_name=name, dose=600, unit="mg", route="IV",
                            frequency="BID", duration_days=7)


# --- matching is driven by the patient's own recorded details ----------------

def test_documented_allergy_matches_the_contraindication():
    findings = findings_from_label(_patient(allergies=["Cephalosporins"]), _item(), LABEL)
    allergy = [f for f in findings if "cross-reactivity" in f.concern.lower()]
    assert allergy, [f.concern for f in findings]
    assert "cephalosporin class" in allergy[0].excerpt
    assert allergy[0].matched_on == "allergy: Cephalosporins"
    assert allergy[0].section == "CONTRAINDICATIONS"


def test_no_allergy_recorded_produces_no_allergy_finding():
    findings = findings_from_label(_patient(), _item(), LABEL)
    assert not [f for f in findings if "cross-reactivity" in f.concern.lower()]


def test_renal_impairment_matches_only_when_egfr_is_low():
    assert [f for f in findings_from_label(_patient(egfr_ml_min=24.0), _item(), LABEL)
            if "Renal" in f.concern]
    assert not [f for f in findings_from_label(_patient(egfr_ml_min=95.0), _item(), LABEL)
                if "Renal" in f.concern]


def test_pregnancy_matches_only_when_pregnant():
    pregnant = _patient(pregnancy_status=PregnancyStatus.PREGNANT_TRIMESTER_2)
    assert [f for f in findings_from_label(pregnant, _item(), LABEL) if f.concern == "Pregnancy"]
    assert not [f for f in findings_from_label(_patient(), _item(), LABEL)
                if f.concern == "Pregnancy"]


def test_home_medication_matches_the_interactions_section():
    patient = _patient(active_medications=["Warfarin 3mg PO QD"])
    findings = [f for f in findings_from_label(patient, _item(), LABEL)
                if "home medication" in f.concern]
    assert findings
    assert "warfarin" in findings[0].excerpt.lower()
    assert findings[0].section == "DRUG INTERACTIONS"


def test_a_boxed_warning_is_reported_even_with_no_matching_patient_detail():
    label = dict(LABEL, boxed_warning=["WARNING: SERIOUS RISK. This drug carries a risk of death."])
    boxed = [f for f in findings_from_label(_patient(), _item(), label)
             if f.section == "BOXED WARNING"]
    assert boxed
    assert boxed[0].matched_on == "applies to all patients"


# --- every finding declares what it is and where it came from ---------------

def test_every_finding_carries_its_origin_and_standing():
    findings = findings_from_label(_patient(allergies=["Cephalosporins"], egfr_ml_min=24.0),
                                   _item(), LABEL)
    assert findings
    for f in findings:
        d = f.to_dict()
        assert d["is_deterministic_rule_finding"] is False
        assert d["standing"] == STANDING_NOTICE
        assert d["source"].startswith("FDA label - Ceftaroline Fosamil")
        assert d["source_kind"] == "FDA_LABEL"
        assert d["matched_on"]
        assert d["excerpt"]


def test_the_standing_notice_denies_national_authority():
    assert "NOT NATIONAL GUIDANCE" in STANDING_NOTICE
    assert "NOT A DETERMINISTIC RULE FINDING" in STANDING_NOTICE


def test_excerpts_are_verbatim_from_the_label():
    findings = findings_from_label(_patient(allergies=["Cephalosporins"]), _item(), LABEL)
    source_text = " ".join(LABEL["contraindications"])
    assert findings[0].excerpt.replace("...", "") in " ".join(source_text.split())


# --- failure is safe ---------------------------------------------------------

def test_no_label_found_leaves_the_gap_unresolved(monkeypatch):
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: None)
    res = resolve_coverage_gap(_patient(), _item(), include_web=False)
    assert res.resolved is False
    assert res.findings == []
    assert "clinician review" in res.note


def test_a_label_with_no_patient_match_says_so_rather_than_implying_safety(monkeypatch):
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: LABEL)
    res = resolve_coverage_gap(_patient(), _item(), include_web=False)
    assert res.label_found is True
    assert "absence of a match, not a finding of safety" in res.note


def test_a_failing_endpoint_never_raises(monkeypatch):
    def boom(_, route=None):
        raise RuntimeError("openFDA is down")
    monkeypatch.setattr(external_safety, "fetch_label", boom)
    with pytest.raises(RuntimeError):
        external_safety.fetch_label("x")          # the stub itself raises
    # resolve_coverage_gap must still not propagate it
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: (_ for _ in ()).throw(RuntimeError()))
    try:
        res = resolve_coverage_gap(_patient(), _item(), include_web=False)
    except RuntimeError:
        pytest.fail("resolve_coverage_gap must not propagate a source failure")
    assert res.resolved is False


# --- the boundary: this layer cannot touch the deterministic verdict ---------

def _analysis(drug, **patient_kw):
    patient = _patient(**patient_kw)
    rx = PrescriptionCreate(patient_id=patient.patient_id, diagnosis="MRSA bacteraemia",
                            items=[_item(drug)])
    warnings = ClinicalRuleEngine().evaluate_prescription(patient, rx, "RX-EXT")
    return patient, rx, warnings


def test_only_drugs_the_engine_reported_uncovered_are_looked_up(monkeypatch):
    """Driven by COVERAGE-001, not by a second guess at the knowledge base."""
    looked_up = []
    monkeypatch.setattr(external_safety, "fetch_label",
                        lambda d, route=None: looked_up.append(d) or LABEL)

    patient, rx, warnings = _analysis("Ceftriaxone")   # in the knowledge base
    assert not any(w.rule_id == "COVERAGE-001" for w in warnings)
    assert resolve_uncovered_items(patient, rx.items, warnings, include_web=False) == []
    assert looked_up == []

    patient, rx, warnings = _analysis("Ceftaroline")   # not in the knowledge base
    assert any(w.rule_id == "COVERAGE-001" for w in warnings)
    assert resolve_uncovered_items(patient, rx.items, warnings, include_web=False)
    assert looked_up == ["Ceftaroline"]


def test_resolution_does_not_change_the_warnings_or_the_priority(monkeypatch):
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: LABEL)
    patient, rx, warnings = _analysis("Ceftaroline", allergies=["Cephalosporins"],
                                      egfr_ml_min=24.0)

    before_ids = [w.rule_id for w in warnings]
    before_sev = [w.severity for w in warnings]
    before_tier = compute_stewardship_priority(warnings, rx.items)["tier"]

    findings = resolve_uncovered_items(patient, rx.items, warnings, include_web=False)
    assert findings and findings[0]["finding_count"] >= 2

    assert [w.rule_id for w in warnings] == before_ids
    assert [w.severity for w in warnings] == before_sev
    assert compute_stewardship_priority(warnings, rx.items)["tier"] == before_tier
    assert findings[0]["affects_stewardship_priority"] is False


def test_the_rule_engine_still_does_not_import_this_layer():
    import inspect

    import backend.rules.engine as engine
    import backend.rules.priority as priority

    for module in (engine, priority):
        assert "external_safety" not in inspect.getsource(module)
        assert "backend.agents" not in inspect.getsource(module)


# --- false positives are worse than silence ---------------------------------

VANCO_LABEL = {
    "openfda": {"brand_name": ["Vancomycin Hydrochloride"]},
    "contraindications": [
        "CONTRAINDICATIONS Vancomycin hydrochloride for injection is contraindicated in "
        "patients with known hypersensitivity to vancomycin."
    ],
}


def test_a_generic_hypersensitivity_sentence_is_not_a_cross_reactivity_finding():
    """
    Regression guard. An earlier matcher accepted any excerpt containing the word
    "hypersensitivity", so a cephalosporin-allergic patient was told vancomycin
    might cross-react on the strength of a sentence that only said vancomycin is
    contraindicated in vancomycin hypersensitivity. Almost every label carries
    that sentence, so this fired on nearly every drug for nearly every patient.
    """
    patient = _patient(allergies=["Cephalosporins"])
    findings = findings_from_label(patient, _item("Vancomycin"), VANCO_LABEL)
    assert not [f for f in findings if "cross-reactivity" in f.concern.lower()], (
        "a label that never names the patient's allergen must not produce a "
        "cross-reactivity finding"
    )


def test_a_label_that_names_the_allergen_still_produces_the_finding():
    """The true positive the guard above must not suppress."""
    patient = _patient(allergies=["Cephalosporins"])
    findings = findings_from_label(patient, _item("Ceftaroline"), LABEL)
    cross = [f for f in findings if "cross-reactivity" in f.concern.lower()]
    assert cross
    assert "cephalosporin" in cross[0].excerpt.lower()


# --- the escalation chain: national first, external only as fallback ---------

def _items(*names):
    return [_item(n) for n in names]


def test_national_guidance_is_reported_as_national_even_though_safety_is_checked(monkeypatch):
    """
    GUIDANCE and SAFETY are separate questions, and this test changed when that
    distinction was drawn.

    It previously asserted that nothing external was consulted at all when a held
    passage named the drug. That rule was superseded: an allergy cross-reactivity
    or a drug interaction does not stop applying to this patient because a
    guideline mentions the agent, so the label is now read for every drug.

    What survives, and what this asserts: the GUIDANCE tier is still reported as
    national, and the drug is still marked as assessed by the rules.
    """
    monkeypatch.setattr(external_safety, "national_evidence_for",
                        lambda drug, dx, k=3: [{"issuing_org": "ICMR", "section_page": "p. 44",
                                                "verbatim_passage": "…", "precedence_rank": 2,
                                                "retrieval_score": 0.7, "document_title": "ICMR STG"}])
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: None)

    out = external_safety.evidence_for_items(_patient(), _items("Vancomycin"), [], include_web=False)
    assert out[0]["source_tier"] == "NATIONAL_GUIDELINE"
    assert out[0]["escalated_to_external"] is False
    assert out[0]["in_knowledge_base"] is True
    assert "answered by the held national corpus" in out[0]["note"].lower()


def test_a_drug_the_national_corpus_does_not_answer_escalates(monkeypatch):
    monkeypatch.setattr(external_safety, "national_evidence_for", lambda drug, dx, k=3: [])
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: LABEL)

    out = external_safety.evidence_for_items(
        _patient(allergies=["Cephalosporins"]), _items("Ceftaroline"), [], include_web=False)
    assert out[0]["source_tier"] == "EXTERNAL_FALLBACK"
    assert out[0]["escalated_to_external"] is True
    assert out[0]["finding_count"] >= 1
    assert "No held national passage names" in out[0]["note"]


def test_each_drug_is_escalated_independently(monkeypatch):
    """One order, one drug held and one not: each takes its own path."""
    monkeypatch.setattr(external_safety, "national_evidence_for",
                        lambda drug, dx, k=3: ([{"issuing_org": "ICMR", "section_page": "p. 44",
                                                 "verbatim_passage": "…", "precedence_rank": 2,
                                                 "retrieval_score": 0.7, "document_title": "ICMR"}]
                                               if drug == "Vancomycin" else []))
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: LABEL)

    out = external_safety.evidence_for_items(
        _patient(egfr_ml_min=24.0), _items("Vancomycin", "Ceftaroline"), [], include_web=False)
    tiers = {r["drug"]: r["source_tier"] for r in out}
    assert tiers == {"Vancomycin": "NATIONAL_GUIDELINE", "Ceftaroline": "EXTERNAL_FALLBACK"}


def test_escalation_still_cannot_change_the_deterministic_verdict(monkeypatch):
    monkeypatch.setattr(external_safety, "national_evidence_for", lambda drug, dx, k=3: [])
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: LABEL)

    patient, rx, warnings = _analysis("Ceftaroline", allergies=["Cephalosporins"], egfr_ml_min=24.0)
    before = ([w.rule_id for w in warnings], [w.severity for w in warnings],
              compute_stewardship_priority(warnings, rx.items)["tier"])

    out = external_safety.evidence_for_items(patient, rx.items, warnings, include_web=False)
    assert out[0]["affects_stewardship_priority"] is False
    assert ([w.rule_id for w in warnings], [w.severity for w in warnings],
            compute_stewardship_priority(warnings, rx.items)["tier"]) == before


# --- unassessed domains escalate even when the corpus names the drug ---------

PARTIAL_NATIONAL = [{"issuing_org": "ICMR", "section_page": "p. 144", "verbatim_passage": "…",
                     "precedence_rank": 2, "retrieval_score": 0.6, "document_title": "ICMR STG"}]


def test_a_partially_covered_drug_escalates_even_though_the_corpus_names_it(monkeypatch):
    """
    Regression guard. Clindamycin is named by three national passages -- solid
    organ transplant, endocarditis, an antibiotics list -- while COVERAGE-001
    fires because its renal dosing, hepatic dosing, pregnancy category, lactation
    safety, paediatric review and interactions are not held. Treating "the corpus
    mentions it" as "the corpus answers it" left exactly those domains unfilled.
    """
    monkeypatch.setattr(external_safety, "national_evidence_for",
                        lambda drug, dx, k=3: PARTIAL_NATIONAL)
    monkeypatch.setattr(external_safety, "_coverage_gaps",
                        lambda drug: ["renal_dosing", "hepatic_dosing"])
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: LABEL)

    class _W:
        rule_id = "COVERAGE-001"
        prescribed_drug = "Clindamycin"

    out = external_safety.evidence_for_items(
        _patient(egfr_ml_min=24.0), _items("Clindamycin"), [_W()], include_web=False)
    assert out[0]["source_tier"] == "EXTERNAL_FALLBACK"
    assert out[0]["coverage_gaps"] == ["renal_dosing", "hepatic_dosing"]
    # the national passages are kept, not discarded, so both are visible
    assert out[0]["national_evidence"] == PARTIAL_NATIONAL
    assert "could not assess" in out[0]["note"]


def test_a_fully_assessed_drug_named_nationally_is_not_escalated_for_guidance(monkeypatch):
    """Guidance stays national; only the escalation flag is asserted here."""
    monkeypatch.setattr(external_safety, "national_evidence_for",
                        lambda drug, dx, k=3: PARTIAL_NATIONAL)
    monkeypatch.setattr(external_safety, "_coverage_gaps", lambda drug: [])
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: None)

    out = external_safety.evidence_for_items(_patient(), _items("Vancomycin"), [], include_web=False)
    assert out[0]["source_tier"] == "NATIONAL_GUIDELINE"
    assert out[0]["escalated_to_external"] is False
    assert out[0]["coverage_gaps"] == []


# --- the label must match the formulation prescribed ------------------------

TOPICAL = {"openfda": {"brand_name": ["Clindamycin Gel"], "route": ["TOPICAL"]},
           "contraindications": ["Short topical section."]}
INJECTABLE = {"openfda": {"brand_name": ["Cleocin Phosphate"],
                          "route": ["INTRAMUSCULAR", "INTRAVENOUS"]},
              "boxed_warning": ["WARNING: Clostridioides difficile-associated diarrhea."],
              "contraindications": ["Contraindicated in known hypersensitivity."],
              "drug_interactions": ["Neuromuscular blocking agents."],
              "dosage_and_administration": ["Serious infections: 600-1200 mg/day."]}


def test_an_intravenous_order_selects_the_injectable_label_not_the_topical_one():
    """
    openFDA holds every marketed formulation and returns an arbitrary one. For an
    IV clindamycin order it returned a topical gel whose sections are 279
    characters and mention neither renal nor hepatic use -- a false negative about
    the exact domains the coverage warning said were unassessed.
    """
    assert (external_safety._label_score(INJECTABLE, "IV")
            > external_safety._label_score(TOPICAL, "IV"))


def test_route_is_part_of_the_cache_key(monkeypatch):
    """The same drug IV and topically are different documents."""
    external_safety._LABEL_CACHE.clear()
    calls = []

    class _Resp:
        status_code = 200
        @staticmethod
        def json():
            return {"results": [INJECTABLE]}

    def fake_get(url, params=None, timeout=None):
        calls.append(params["search"])
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)
    external_safety.fetch_label("Clindamycin", "IV")
    first = len(calls)
    external_safety.fetch_label("Clindamycin", "IV")      # cached
    assert len(calls) == first
    external_safety.fetch_label("Clindamycin", "TOPICAL")  # different key
    assert len(calls) > first


# --- a lexical match that means the opposite is not a finding ---------------

NEGATED_LABEL = {
    "openfda": {"brand_name": ["Cleocin Phosphate"], "route": ["INTRAVENOUS"]},
    "dosage_and_administration": [
        "No incompatibility has been demonstrated with the antibacterial drugs cephalothin, "
        "kanamycin, gentamicin, penicillin G."
    ],
    "drug_interactions": [
        "No clinically relevant interaction with warfarin has been observed in trials."
    ],
}


def test_a_negated_sentence_is_not_reported_as_a_concern():
    """
    Regression guard. "cephalothin" matched a cephalosporin allergy inside the
    sentence "No incompatibility has been demonstrated with ... cephalothin",
    which says the opposite of a concern, and it came from the dosing section --
    no place for a hypersensitivity claim at all.
    """
    findings = findings_from_label(
        _patient(allergies=["Cephalosporins"]), _item("Clindamycin"), NEGATED_LABEL)
    assert not [f for f in findings if "cross-reactivity" in f.concern.lower()]


def test_a_negated_interaction_sentence_is_not_reported():
    findings = findings_from_label(
        _patient(active_medications=["Warfarin 3mg PO QD"]), _item("Clindamycin"), NEGATED_LABEL)
    assert not [f for f in findings if "Interaction" in f.concern]


def test_allergy_claims_come_only_from_hypersensitivity_sections():
    """A dosing-section mention can never produce an allergy finding."""
    label = {"openfda": {"brand_name": ["X"]},
             "dosage_and_administration": ["Compatible with cephalothin in solution."]}
    assert not findings_from_label(_patient(allergies=["Cephalosporins"]), _item(), label)


# --- interactions are checked against the rest of the same order ------------

CO_LABEL = {
    "openfda": {"brand_name": ["Ciprofloxacin"], "route": ["INTRAVENOUS"]},
    "drug_interactions": [
        "Concomitant administration with tizanidine is contraindicated. Monitor prothrombin "
        "time when given with warfarin."
    ],
}


def test_a_drug_on_the_same_order_is_checked_for_interactions():
    """
    Home medications were checked and co-prescribed drugs were not, which is the
    wrong half to miss: two agents started together are the interaction a
    prescriber can still prevent.
    """
    findings = findings_from_label(_patient(), _item("Ciprofloxacin"), CO_LABEL,
                                   co_prescribed=["Tizanidine 4mg PO TID"])
    co = [f for f in findings if "co-prescribed" in f.concern]
    assert co, [f.concern for f in findings]
    assert "tizanidine" in co[0].excerpt.lower()


def test_safety_checks_run_even_when_the_national_corpus_answers_the_drug(monkeypatch):
    """
    Allergy and interaction checks do not stop applying because a guideline names
    the drug. Guidance is answered nationally; whether THIS patient can take it is
    a different question.
    """
    monkeypatch.setattr(external_safety, "national_evidence_for",
                        lambda drug, dx, k=3: PARTIAL_NATIONAL)
    monkeypatch.setattr(external_safety, "_coverage_gaps", lambda drug: [])
    monkeypatch.setattr(external_safety, "fetch_label", lambda d, route=None: CO_LABEL)

    out = external_safety.evidence_for_items(
        _patient(active_medications=["Warfarin 3mg PO QD"]),
        _items("Ciprofloxacin"), [], include_web=False)
    assert out[0]["source_tier"] == "NATIONAL_GUIDELINE"
    assert out[0]["finding_count"] >= 1
    assert any("Warfarin" in f["concern"] for f in out[0]["findings"])
