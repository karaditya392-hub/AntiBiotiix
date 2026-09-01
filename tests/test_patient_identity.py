"""
Patients are shown by name, not only by record key.

"PATIENT-014" is a usable database key and it is not a patient. A prescription or
a safety report that identifies its subject only by that string cannot be checked
against the person in front of the clinician signing it. The key stays everywhere
it is a key -- API paths, foreign keys, the audit trail -- and the human-facing
surfaces carry the name alongside it.
"""
import pymupdf
import pytest

from backend.guidelines.knowledge_base import knowledge_base  # noqa: F401  (seeds import path)
from backend.pdf_generator import _patient_label, generate_prescription_pdf

PATIENT = {
    "patient_id": "PATIENT-001", "display_name": "Rajesh Sharma", "age": 45,
    "sex": "MALE", "weight_kg": 72.0, "egfr_ml_min": 92.0,
    "allergies": ["Penicillin"], "active_medications": [],
}
ITEMS = [{"medication_name": "Amoxicillin", "dose": 500, "unit": "mg", "route": "PO",
          "frequency": "TID", "duration_days": 5, "indication": "Pneumonia"}]


@pytest.mark.parametrize("record,expected", [
    ({"patient_id": "PATIENT-001", "display_name": "Rajesh Sharma"},
     "Rajesh Sharma (PATIENT-001)"),
    # Records seeded before display_name held a bare name.
    ({"patient_id": "PATIENT-001", "display_name": "PATIENT-001 (Rajesh Sharma)"},
     "Rajesh Sharma (PATIENT-001)"),
    # No name recorded: the id is all there is, and inventing one would be worse.
    ({"patient_id": "PATIENT-050", "display_name": ""}, "PATIENT-050"),
    ({"patient_id": "PATIENT-051", "display_name": "Patient Record"}, "PATIENT-051"),
    ({"patient_id": "PATIENT-052", "display_name": "PATIENT-052"}, "PATIENT-052"),
])
def test_patient_label_shows_the_name_without_repeating_the_id(record, expected):
    assert _patient_label(record) == expected


def test_prescription_pdf_names_its_patient():
    pdf = generate_prescription_pdf(
        PATIENT, {"visit_id": "VIS-TEST", "diagnosis": "Pneumonia", "visit_date": None},
        ITEMS, warnings=[], overrides=[],
        clinician_id="CLINICIAN-DEMO", clinician_role="ATTENDING_PHYSICIAN",
    )
    text = pymupdf.open(stream=pdf, filetype="pdf")[0].get_text()
    assert "Rajesh Sharma" in text, "the prescription does not name its patient"
    assert "PATIENT-001" in text, "the record key must remain on the document"


def test_a_visit_with_no_recorded_date_still_produces_a_prescription():
    """
    The fallback that stamps the current time referenced `timedelta`, which was not
    imported, so this raised NameError instead of generating the document. The branch
    only runs when visit_date is absent, which is how it survived.
    """
    pdf = generate_prescription_pdf(
        PATIENT, {"visit_id": "VIS-NO-DATE", "diagnosis": "Pneumonia", "visit_date": None},
        ITEMS, warnings=[], overrides=[],
    )
    assert pdf and pdf[:4] == b"%PDF"
    assert "IST" in pymupdf.open(stream=pdf, filetype="pdf")[0].get_text()


def test_seeded_patients_carry_a_bare_name_not_an_id_prefixed_one():
    import re
    import pathlib

    source = pathlib.Path("backend/seed_data.py").read_text(encoding="utf-8")
    names = re.findall(r'"display_name":\s*"([^"]*)"', source)
    assert names, "expected seeded patients to carry display names"
    for name in names:
        assert not re.match(r"^PATIENT-\d+", name), f"display_name still prefixed: {name!r}"
