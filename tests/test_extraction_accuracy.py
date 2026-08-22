"""
Extraction Parser Accuracy & Precision/Recall Benchmark Suite (Spec §3A)
Evaluates structured extraction performance against a curated benchmark set of >= 20 clinical prescription strings.
"""
import pytest
from backend.extraction.parser import clinical_parser

BENCHMARK_PRESCRIPTIONS = [
    {
        "text": "Amoxicillin 500mg PO TID x 7 days for CAP",
        "expected_med": "Amoxicillin",
        "expected_dose": 500.0,
        "expected_route": "PO",
        "expected_freq": "TID",
        "expected_dur": 7
    },
    {
        "text": "Amoxicillin-Clavulanate 625 mg PO TID x 10 days",
        "expected_med": "Amoxicillin-Clavulanate",
        "expected_dose": 625.0,
        "expected_route": "PO",
        "expected_freq": "TID",
        "expected_dur": 10
    },
    {
        "text": "Augmentin 875/125 mg PO BID x 7 days for sinusitis",
        "expected_med": "Amoxicillin-Clavulanate",
        "expected_dose": 1000.0,  # 875 + 125 combination strength
        "expected_route": "PO",
        "expected_freq": "BID",
        "expected_dur": 7
    },
    {
        "text": "Ciprofloxacin 500mg PO BID x 5 days",
        "expected_med": "Ciprofloxacin",
        "expected_dose": 500.0,
        "expected_route": "PO",
        "expected_freq": "BID",
        "expected_dur": 5
    },
    {
        "text": "Levofloxacin 750mg IV QD x 5 days",
        "expected_med": "Levofloxacin",
        "expected_dose": 750.0,
        "expected_route": "IV",
        "expected_freq": "QD",
        "expected_dur": 5
    },
    {
        "text": "Azithromycin 500 mg PO QD x 3 days",
        "expected_med": "Azithromycin",
        "expected_dose": 500.0,
        "expected_route": "PO",
        "expected_freq": "QD",
        "expected_dur": 3
    },
    {
        "text": "Clarithromycin 500mg PO BID x 7 days",
        "expected_med": "Clarithromycin",
        "expected_dose": 500.0,
        "expected_route": "PO",
        "expected_freq": "BID",
        "expected_dur": 7
    },
    {
        "text": "Metronidazole 400mg PO TID x 7 days",
        "expected_med": "Metronidazole",
        "expected_dose": 400.0,
        "expected_route": "PO",
        "expected_freq": "TID",
        "expected_dur": 7
    },
    {
        "text": "Flagyl 500mg IV TID x 10 days",
        "expected_med": "Metronidazole",
        "expected_dose": 500.0,
        "expected_route": "IV",
        "expected_freq": "TID",
        "expected_dur": 10
    },
    {
        "text": "Ceftriaxone 1g IV QD x 7 days for sepsis",
        "expected_med": "Ceftriaxone",
        "expected_dose": 1.0,
        "expected_route": "IV",
        "expected_freq": "QD",
        "expected_dur": 7
    },
    {
        "text": "Rocephin 2g IV QD x 14 days for meningitis",
        "expected_med": "Ceftriaxone",
        "expected_dose": 2.0,
        "expected_route": "IV",
        "expected_freq": "QD",
        "expected_dur": 14
    },
    {
        "text": "Piperacillin-Tazobactam 4.5g IV Q8H x 7 days",
        "expected_med": "Piperacillin-Tazobactam",
        "expected_dose": 4.5,
        "expected_route": "IV",
        "expected_freq": "Q8H",
        "expected_dur": 7
    },
    {
        "text": "Piptaz 4.5g IV Q6H x 10 days",
        "expected_med": "Piperacillin-Tazobactam",
        "expected_dose": 4.5,
        "expected_route": "IV",
        "expected_freq": "Q6H",
        "expected_dur": 10
    },
    {
        "text": "Meropenem 1g IV TID x 7 days",
        "expected_med": "Meropenem",
        "expected_dose": 1.0,
        "expected_route": "IV",
        "expected_freq": "TID",
        "expected_dur": 7
    },
    {
        "text": "Vancomycin 1g IV Q12H x 14 days",
        "expected_med": "Vancomycin",
        "expected_dose": 1.0,
        "expected_route": "IV",
        "expected_freq": "Q12H",
        "expected_dur": 14
    },
    {
        "text": "Doxycycline 100mg PO BID x 7 days",
        "expected_med": "Doxycycline",
        "expected_dose": 100.0,
        "expected_route": "PO",
        "expected_freq": "BID",
        "expected_dur": 7
    },
    {
        "text": "Nitrofurantoin 100mg PO BID x 5 days for acute cystitis",
        "expected_med": "Nitrofurantoin",
        "expected_dose": 100.0,
        "expected_route": "PO",
        "expected_freq": "BID",
        "expected_dur": 5
    },
    {
        "text": "Macrobid 100mg PO BID x 5 days",
        "expected_med": "Nitrofurantoin",
        "expected_dose": 100.0,
        "expected_route": "PO",
        "expected_freq": "BID",
        "expected_dur": 5
    },
    {
        "text": "Linezolid 600mg PO BID x 10 days",
        "expected_med": "Linezolid",
        "expected_dose": 600.0,
        "expected_route": "PO",
        "expected_freq": "BID",
        "expected_dur": 10
    },
    {
        "text": "Zyvox 600mg IV BID x 14 days for MRSA pneumonia",
        "expected_med": "Linezolid",
        "expected_dose": 600.0,
        "expected_route": "IV",
        "expected_freq": "BID",
        "expected_dur": 14
    },
    {
        "text": "Gentamicin 80mg IV TID x 5 days",
        "expected_med": "Gentamicin",
        "expected_dose": 80.0,
        "expected_route": "IV",
        "expected_freq": "TID",
        "expected_dur": 5
    }
]


def test_extraction_accuracy_benchmark_21_cases():
    """Verify >= 95% precision/recall across all fields on benchmark suite."""
    med_matches = 0
    dose_matches = 0
    route_matches = 0
    freq_matches = 0
    dur_matches = 0
    total = len(BENCHMARK_PRESCRIPTIONS)

    for case in BENCHMARK_PRESCRIPTIONS:
        extracted = clinical_parser.parse_free_text(case["text"])
        assert len(extracted.items) >= 1, f"Failed to extract item for: {case['text']}"
        item = extracted.items[0]

        if item.medication_name == case["expected_med"]:
            med_matches += 1
        if item.dose == case["expected_dose"]:
            dose_matches += 1
        if item.route == case["expected_route"]:
            route_matches += 1
        if item.frequency == case["expected_freq"]:
            freq_matches += 1
        if item.duration_days == case["expected_dur"]:
            dur_matches += 1

    med_accuracy = med_matches / total
    dose_accuracy = dose_matches / total
    route_accuracy = route_matches / total
    freq_accuracy = freq_matches / total
    dur_accuracy = dur_matches / total

    assert med_accuracy >= 0.95, f"Medication extraction accuracy {med_accuracy:.2f} < 0.95"
    assert dose_accuracy >= 0.95, f"Dose extraction accuracy {dose_accuracy:.2f} < 0.95"
    assert route_accuracy >= 0.95, f"Route extraction accuracy {route_accuracy:.2f} < 0.95"
    assert freq_accuracy >= 0.95, f"Frequency extraction accuracy {freq_accuracy:.2f} < 0.95"
    assert dur_accuracy >= 0.95, f"Duration extraction accuracy {dur_accuracy:.2f} < 0.95"


def test_multi_drug_prescription_extraction():
    """Verify multiple drugs in a single order are both parsed and flag confirmation."""
    text = "Ciprofloxacin 500mg PO BID and Metronidazole 400mg PO TID x 7 days"
    extracted = clinical_parser.parse_free_text(text)

    assert len(extracted.items) == 2, "Must extract both co-prescribed items"
    med_names = [i.medication_name for i in extracted.items]
    assert "Ciprofloxacin" in med_names
    assert "Metronidazole" in med_names
    assert extracted.needs_clinician_confirmation is True, "Multi-drug order must require confirmation"


def test_combination_strength_forces_clinician_confirmation():
    """Punch List Defect 4: Combination doses (e.g. 875/125 mg) must require clinician confirmation."""
    text = "Augmentin 875/125 mg PO BID x 7 days for sinusitis"
    extracted = clinical_parser.parse_free_text(text)

    assert len(extracted.items) == 1
    assert extracted.items[0].medication_name == "Amoxicillin-Clavulanate"
    assert extracted.items[0].dose == 1000.0
    assert extracted.needs_clinician_confirmation is True, "Combination strength must set needs_clinician_confirmation = True"
