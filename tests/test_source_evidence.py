"""
Regulatory product-label evidence attachment and source-threshold divergence.
Spec §17 (evidence citations), §19 (evidence panel), §21 (source traceability).
"""
import pytest

from backend.models.schemas import (
    PatientCreate, PrescriptionCreate, PrescriptionItem, PregnancyStatus,
    SeverityLevel,
)
from backend.rules.engine import rule_engine
from backend.guidelines.label_evidence import label_evidence_store


def _item(name, **kw):
    return PrescriptionItem(
        medication_name=name, dose=kw.get("dose", 500), unit="mg",
        route=kw.get("route", "PO"), frequency="BID", duration_days=7,
    )


def _run(items, **patient_kw):
    patient = PatientCreate(patient_id="TEST-EV", **patient_kw)
    presc = PrescriptionCreate(patient_id="TEST-EV", items=items)
    return rule_engine.evaluate_prescription(patient, presc, prescription_id="RX-EV")


def test_label_corpus_loaded():
    assert len(label_evidence_store.labels) >= 15


def test_label_evidence_is_us_labelling_not_guideline():
    """Provenance boundary: product labelling must never present as ICMR/WHO."""
    ev = label_evidence_store.get_label_evidence("nitrofurantoin", "RENAL")
    assert ev is not None
    assert "United States" in ev["geographic_scope"]
    assert "Food and Drug Administration" in ev["issuing_org"]
    assert "ICMR" not in ev["issuing_org"]
    assert "WHO" not in ev["issuing_org"]


def test_irrelevant_concept_returns_no_citation():
    """An absent citation is preferable to an irrelevant one."""
    assert label_evidence_store.get_label_evidence("amoxicillin", "NOT_A_CATEGORY") is None
    assert label_evidence_store.get_label_evidence("no_such_drug", "RENAL") is None


def test_specific_probe_is_not_satisfied_by_generic_text():
    """A caller-supplied concept must not fall back to unrelated label prose."""
    assert label_evidence_store.get_label_evidence(
        "amoxicillin", "DRUG_INTERACTION", probes=["zzzznonexistentdrug"]
    ) is None


def test_allergy_warning_carries_label_evidence():
    ws = _run([_item("Amoxicillin")], age=40, allergies=["Penicillin"],
              allergy_status_known=True, egfr_ml_min=95.0)
    allergy = [w for w in ws if w.category.value == "ALLERGY"]
    assert allergy
    labels = allergy[0].supporting_labels
    assert labels, "allergy warning should carry product-label evidence"
    assert "hypersensitivity" in labels[0].verbatim_passage.lower()
    assert labels[0].source_url and "dailymed" in labels[0].source_url


def test_ddi_label_evidence_names_the_actual_interacting_drug():
    ws = _run([_item("Ciprofloxacin")], age=60, egfr_ml_min=95.0,
              active_medications=["Warfarin 5mg PO QD"])
    ddi = [w for w in ws if w.category.value == "DRUG_INTERACTION"]
    assert ddi
    assert ddi[0].supporting_labels
    assert "warfarin" in ddi[0].supporting_labels[0].verbatim_passage.lower()


def test_pregnancy_label_evidence_is_about_pregnancy_not_paediatrics():
    """Regression: this previously cited the Pediatric Use section."""
    ws = _run([_item("Doxycycline")], age=28, sex="FEMALE",
              pregnancy_status=PregnancyStatus.PREGNANT_TRIMESTER_1, egfr_ml_min=95.0)
    vuln = [w for w in ws if w.rule_id == "VULN-002"]
    assert vuln
    passage = vuln[0].supporting_labels[0].verbatim_passage.lower()
    assert "pregnancy" in passage


def test_guideline_citation_is_not_replaced_by_label():
    """Product labelling supplements the guideline citation; it never substitutes."""
    ws = _run([_item("Amoxicillin")], age=40, allergies=["Penicillin"],
              allergy_status_known=True, egfr_ml_min=95.0)
    w = [x for x in ws if x.category.value == "ALLERGY"][0]
    assert "ICMR" in w.evidence.document_title
    assert w.supporting_labels[0].document_title != w.evidence.document_title


@pytest.mark.parametrize("egfr,expected", [
    (95.0, None),
    (70.0, None),
    (55.0, "RENAL-004"),
    (30.0, "RENAL-004"),
    (29.9, "RENAL-002"),
    (12.0, "RENAL-002"),
])
def test_nitrofurantoin_source_divergence_band(egfr, expected):
    """
    FDA label contraindicates below CrCl 60; the ICMR-derived threshold flags
    below 30. The 30-59 band surfaces the divergence instead of picking one.
    """
    ws = _run([_item("Nitrofurantoin", dose=100)], age=70, egfr_ml_min=egfr,
              renal_status_known=True)
    renal = [w for w in ws if w.category.value == "RENAL"]
    if expected is None:
        assert not renal
    else:
        assert [w.rule_id for w in renal] == [expected]


def test_divergence_band_is_not_critical():
    """The band must not over-alert: CRITICAL is reserved for below 30."""
    ws = _run([_item("Nitrofurantoin", dose=100)], age=70, egfr_ml_min=45.0,
              renal_status_known=True)
    w = [x for x in ws if x.rule_id == "RENAL-004"][0]
    assert w.severity == SeverityLevel.MODERATE
    assert "diverge" in (w.clinical_concern + w.evidence.verbatim_passage).lower()
