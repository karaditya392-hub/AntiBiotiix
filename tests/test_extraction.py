"""
Prescription Extraction & Parsing Accuracy Benchmark (Section 3A)
Measures precision and recall per clinical entity field independently of the rule engine.
"""
import pytest
from backend.extraction.parser import clinical_parser


BENCHMARK_CASES = [
    {
        "raw": "Amoxicillin 500mg PO TID x 7 days for CAP",
        "expected_med": "Amoxicillin",
        "expected_dose": 500.0,
        "expected_unit": "mg",
        "expected_route": "PO",
        "expected_freq": "TID",
        "expected_dur": 7,
        "expected_diag": "Cap"
    },
    {
        "raw": "Ceftriaxone 1g IV daily x 5 days for acute pyelonephritis",
        "expected_med": "Ceftriaxone",
        "expected_dose": 1.0,
        "expected_unit": "g",
        "expected_route": "IV",
        "expected_freq": "QD",
        "expected_dur": 5,
        "expected_diag": "Acute Pyelonephritis"
    },
    {
        "raw": "Ciprofloxacin 500mg oral BD for 3 days",
        "expected_med": "Ciprofloxacin",
        "expected_dose": 500.0,
        "expected_unit": "mg",
        "expected_route": "PO",
        "expected_freq": "BID",
        "expected_dur": 3,
        "expected_diag": None
    },
    {
        "raw": "Augmentin 625mg PO TDS x 10 days for sinusitis",
        "expected_med": "Amoxicillin-Clavulanate",
        "expected_dose": 625.0,
        "expected_unit": "mg",
        "expected_route": "PO",
        "expected_freq": "TID",
        "expected_dur": 10,
        "expected_diag": "Sinusitis"
    },
    {
        "raw": "Metronidazole 400mg PO TID * 7 days",
        "expected_med": "Metronidazole",
        "expected_dose": 400.0,
        "expected_unit": "mg",
        "expected_route": "PO",
        "expected_freq": "TID",
        "expected_dur": 7,
        "expected_diag": None
    }
]


def test_extraction_precision_recall_benchmark():
    field_matches = {
        "medication": 0,
        "dose": 0,
        "unit": 0,
        "route": 0,
        "frequency": 0,
        "duration": 0
    }
    total_cases = len(BENCHMARK_CASES)

    for case in BENCHMARK_CASES:
        res = clinical_parser.parse_free_text(case["raw"])
        assert len(res.items) >= 1
        item = res.items[0]

        if item.medication_name.lower() == case["expected_med"].lower():
            field_matches["medication"] += 1
        if item.dose == case["expected_dose"]:
            field_matches["dose"] += 1
        if item.unit and item.unit.lower() == case["expected_unit"].lower():
            field_matches["unit"] += 1
        if item.route == case["expected_route"]:
            field_matches["route"] += 1
        if item.frequency == case["expected_freq"]:
            field_matches["frequency"] += 1
        if item.duration_days == case["expected_dur"]:
            field_matches["duration"] += 1

    # Compute accuracy per field
    accuracies = {k: v / total_cases for k, v in field_matches.items()}
    print("\nExtraction Benchmark Accuracy:")
    for field, acc in accuracies.items():
        print(f"  - {field}: {acc * 100:.1f}%")
        assert acc >= 0.80, f"Field '{field}' accuracy ({acc*100}%) below minimum clinical benchmark 80%."


def test_ambiguous_low_confidence_requires_confirmation():
    ambiguous = "Give patient standard antibiotic tablet once"
    res = clinical_parser.parse_free_text(ambiguous)
    assert res.needs_clinician_confirmation is True
