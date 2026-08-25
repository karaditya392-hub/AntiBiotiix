"""
Comprehensive Tests for Doctor-Centric Longitudinal Patient Record, Immutable Visits,
Prescription Memory, RAG History Assistant, and CRITICAL Cross-Patient Security Isolation.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.models.database import SessionLocal, init_db, PatientDB, VisitDB, SymptomDB, DiagnosisDB, PrescriptionDB, PatientRAGDocumentDB
from backend.auth.security import create_session_token

client = TestClient(app)


@pytest.fixture(scope="module")
def clinician_auth_headers():
    token = create_session_token("DOC-DEMO-TEST", "ATTENDING_PHYSICIAN")
    return {"Authorization": f"Bearer {token}"}


def test_01_patient_creation(clinician_auth_headers):
    payload = {
        "display_name": "Test Patient Alpha",
        "age": 42,
        "age_category": "ADULT",
        "sex": "MALE",
        "weight_kg": 75.0,
        "egfr_ml_min": 90.0,
        "renal_status_known": True,
        "allergy_status_known": True,
        "medical_history": ["Hypertension", "Asthma"],
        "active_medications": ["Amlodipine 5mg PO QD"],
        "clinical_notes": "Test registration for longitudinal record."
    }
    response = client.post("/api/patients", json=payload, headers=clinician_auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert "patient_id" in data
    assert data["status"] == "CREATED"


def test_02_patient_retrieval(clinician_auth_headers):
    # Fetch PATIENT-001
    res = client.get("/api/patients/PATIENT-001", headers=clinician_auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["patient_id"] == "PATIENT-001"
    assert "allergies" in data


def test_03_patient_search(clinician_auth_headers):
    # Search by patient_id
    res = client.get("/api/patients?q=PATIENT-001", headers=clinician_auth_headers)
    assert res.status_code == 200
    results = res.json()
    assert len(results) > 0
    assert any(r["patient_id"] == "PATIENT-001" for r in results)

    # Search non-existent
    res_none = client.get("/api/patients?q=NONEXISTENT_999", headers=clinician_auth_headers)
    assert res_none.status_code == 200
    assert len(res_none.json()) == 0


def test_04_patient_update_medications_and_allergies(clinician_auth_headers):
    patient_id = "PATIENT-001"
    med_payload = {
        "active_medications": ["Pantoprazole 40mg PO QD", "Aspirin 81mg PO QD"],
        "reason": "Cardiovascular prophylaxis"
    }
    res = client.put(f"/api/patients/{patient_id}/medications", json=med_payload, headers=clinician_auth_headers)
    assert res.status_code == 200
    assert res.json()["current_count"] == 2


def test_05_visit_creation_and_preservation(clinician_auth_headers):
    patient_id = "PATIENT-001"
    visit_payload = {
        "patient_id": patient_id,
        "doctor_id": "DOC-DEMO-TEST",
        "diagnosis": "Community-acquired pneumonia",
        "symptoms": [
            {"name": "Fever", "severity": "Moderate", "duration": "3 days"},
            {"name": "Cough", "severity": "Moderate", "duration": "4 days"},
            {"name": "Chest discomfort", "severity": "Mild", "duration": "2 days"}
        ],
        "symptoms_text": "Fever, cough and chest discomfort.",
        "clinical_notes": "Worsening lower respiratory symptoms.",
        "raw_prescription_text": "Amoxicillin 500mg PO TID for 5 days",
        "prescription_items": [
            {
                "medication_name": "Amoxicillin",
                "dose": 500,
                "unit": "mg",
                "route": "PO",
                "frequency": "TID",
                "duration_days": 5,
                "indication": "Community-acquired pneumonia"
            }
        ]
    }
    res = client.post(f"/api/patients/{patient_id}/visits", json=visit_payload, headers=clinician_auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "SAVED"
    assert data["message"] == "Visit saved successfully."
    assert "visit_id" in data
    assert data["indexed_in_rag"] is True


def test_06_multiple_visits_and_immutability(clinician_auth_headers):
    patient_id = "PATIENT-001"
    # Fetch initial visits
    res_before = client.get(f"/api/patients/{patient_id}/history", headers=clinician_auth_headers)
    before_count = len(res_before.json()["visits"])

    # Create a 2nd visit
    v2_payload = {
        "patient_id": patient_id,
        "doctor_id": "DOC-DEMO-TEST",
        "diagnosis": "Acute exacerbation of bronchitis",
        "symptoms": [{"name": "Cough", "severity": "Severe", "duration": "5 days"}],
        "clinical_notes": "Follow-up visit for persistent cough.",
        "prescription_items": [
            {
                "medication_name": "Azithromycin",
                "dose": 500,
                "unit": "mg",
                "route": "PO",
                "frequency": "QD",
                "duration_days": 3
            }
        ]
    }
    res_v2 = client.post(f"/api/patients/{patient_id}/visits", json=v2_payload, headers=clinician_auth_headers)
    assert res_v2.status_code == 201

    # Verify history count increased and PREVIOUS visit was not overwritten!
    res_after = client.get(f"/api/patients/{patient_id}/history", headers=clinician_auth_headers)
    after_visits = res_after.json()["visits"]
    assert len(after_visits) == before_count + 1
    # Check that previous visit diagnosis is still present
    diagnoses = [v.get("diagnosis") for v in after_visits]
    assert "Community-acquired pneumonia" in diagnoses
    assert "Acute exacerbation of bronchitis" in diagnoses


def test_07_symptom_and_diagnosis_storage(clinician_auth_headers):
    db = SessionLocal()
    try:
        visit = db.query(VisitDB).filter(VisitDB.patient_id == "PATIENT-001").first()
        assert visit is not None
        symptoms = db.query(SymptomDB).filter(SymptomDB.visit_id == visit.visit_id).all()
        assert len(symptoms) > 0
        diagnoses = db.query(DiagnosisDB).filter(DiagnosisDB.visit_id == visit.visit_id).all()
        assert len(diagnoses) > 0
    finally:
        db.close()


def test_08_medication_history_view(clinician_auth_headers):
    res = client.get("/api/patients/PATIENT-001/medications", headers=clinician_auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["patient_id"] == "PATIENT-001"
    assert "medication_history" in data
    assert len(data["medication_history"]) > 0


def test_09_prescription_safety_analysis_integration(clinician_auth_headers):
    # Penicillin allergy patient PATIENT-001 receiving Amoxicillin should trigger safety warning
    patient_id = "PATIENT-001"
    visit_payload = {
        "patient_id": patient_id,
        "diagnosis": "Bacterial sinusitis",
        "prescription_items": [
            {
                "medication_name": "Amoxicillin",
                "dose": 500,
                "unit": "mg",
                "route": "PO",
                "frequency": "TID",
                "duration_days": 7
            }
        ]
    }
    res = client.post(f"/api/patients/{patient_id}/visits", json=visit_payload, headers=clinician_auth_headers)
    assert res.status_code == 201
    data = res.json()
    # AntiBioTix 24-rule engine fires allergy rule
    assert data["warnings_count"] >= 1


def test_10_rag_indexing_and_provenance(clinician_auth_headers):
    db = SessionLocal()
    try:
        doc = db.query(PatientRAGDocumentDB).filter(PatientRAGDocumentDB.patient_id == "PATIENT-001").first()
        assert doc is not None
        assert doc.patient_id == "PATIENT-001"
        assert doc.visit_id is not None
        assert "DIAGNOSIS:" in doc.content
    finally:
        db.close()


def test_11_ask_patient_history_exact_questions(clinician_auth_headers):
    patient_id = "PATIENT-001"

    # Ask last diagnosis
    res1 = client.post(
        f"/api/patients/{patient_id}/ask",
        json={"question": "What was the diagnosis during this patient's last visit?"},
        headers=clinician_auth_headers
    )
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["answered"] is True
    assert d1["source_visit_id"] is not None
    assert "Source:" in d1["answer"]

    # Ask medications
    res2 = client.post(
        f"/api/patients/{patient_id}/ask",
        json={"question": "What medications has this patient previously received?"},
        headers=clinician_auth_headers
    )
    assert res2.status_code == 200
    assert res2.json()["answered"] is True


def test_12_ask_patient_history_semantic_questions(clinician_auth_headers):
    patient_id = "PATIENT-001"
    res = client.post(
        f"/api/patients/{patient_id}/ask",
        json={"question": "Has this patient previously had chest symptoms or respiratory infection?"},
        headers=clinician_auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["answered"] is True
    assert data["source_visit_id"] is not None


def test_13_ask_patient_history_unknown_info(clinician_auth_headers):
    patient_id = "PATIENT-001"
    res = client.post(
        f"/api/patients/{patient_id}/ask",
        json={"question": "What was the patient's fracture treatment in 1990?"},
        headers=clinician_auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    # If no matching historical record, returns polite notification
    assert "No matching information was found" in data["answer"] or data["answered"] is False or "fracture" not in data["answer"].lower()


def test_14_ask_patient_history_empty_history(clinician_auth_headers):
    # Register a new empty patient
    create_res = client.post(
        "/api/patients",
        json={"age": 30, "sex": "FEMALE", "clinical_notes": "New empty record"},
        headers=clinician_auth_headers
    )
    new_id = create_res.json()["patient_id"]

    res = client.post(
        f"/api/patients/{new_id}/ask",
        json={"question": "What was her previous diagnosis?"},
        headers=clinician_auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    print("DEBUG DATA:", data)
    assert data["answered"] is False or "first recorded visit" in data["answer"]


# ===========================================================================
# CRITICAL SECURITY TEST: CROSS-PATIENT RETRIEVAL ISOLATION
# ===========================================================================

def test_15_critical_security_cross_patient_isolation(clinician_auth_headers):
    """
    CRITICAL SECURITY TEST:
    Create PATIENT-A and PATIENT-B.
    Put a unique secret medication ('SecretX-PharmaDrug-99') in Patient B's visit record.
    Ask the system about Patient A.
    The answer MUST NOT contain Patient B's medication under any circumstances.
    """
    token_a = create_session_token("DOC-DEMO-TEST", "ATTENDING_PHYSICIAN")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register Patient A
    res_a = client.post("/api/patients", json={"age": 50, "sex": "MALE"}, headers=headers_a)
    pat_a_id = res_a.json()["patient_id"]

    # Register Patient B
    res_b = client.post("/api/patients", json={"age": 55, "sex": "FEMALE"}, headers=headers_a)
    pat_b_id = res_b.json()["patient_id"]

    # Save visit for Patient B with UNIQUE secret drug
    secret_drug = "SecretX-PharmaDrug-99"
    v_b = client.post(
        f"/api/patients/{pat_b_id}/visits",
        json={
            "patient_id": pat_b_id,
            "diagnosis": "Rare Syndrome Alpha",
            "prescription_items": [
                {
                    "medication_name": secret_drug,
                    "dose": 250,
                    "unit": "mg",
                    "route": "PO",
                    "frequency": "QD",
                    "duration_days": 10
                }
            ]
        },
        headers=headers_a
    )
    assert v_b.status_code == 201

    # Save visit for Patient A with ordinary drug
    v_a = client.post(
        f"/api/patients/{pat_a_id}/visits",
        json={
            "patient_id": pat_a_id,
            "diagnosis": "Common Cold",
            "prescription_items": [
                {
                    "medication_name": "Paracetamol",
                    "dose": 500,
                    "unit": "mg",
                    "route": "PO",
                    "frequency": "TID",
                    "duration_days": 3
                }
            ]
        },
        headers=headers_a
    )
    assert v_a.status_code == 201

    # Query Patient A asking about previous medications or rare drugs
    ask_a1 = client.post(
        f"/api/patients/{pat_a_id}/ask",
        json={"question": "What medications has this patient previously received?"},
        headers=headers_a
    )
    assert ask_a1.status_code == 200
    ans1 = ask_a1.json()["answer"]
    assert secret_drug not in ans1, f"SECURITY VIOLATION: Patient B's drug {secret_drug} leaked into Patient A query answer!"

    ask_a2 = client.post(
        f"/api/patients/{pat_a_id}/ask",
        json={"question": "Has this patient taken SecretX-PharmaDrug-99 or received therapy for Rare Syndrome Alpha?"},
        headers=headers_a
    )
    assert ask_a2.status_code == 200
    ans2 = ask_a2.json()["answer"]
    assert secret_drug not in ans2, f"SECURITY VIOLATION: Patient B's drug {secret_drug} leaked into Patient A query answer!"


def test_16_dashboard_stats_endpoint(clinician_auth_headers):
    res = client.get("/api/dashboard/stats", headers=clinician_auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "total_patients" in data
    assert "total_visits" in data
    assert data["total_patients"] > 0
    assert "recent_patients" in data


def test_17_audit_log_verification(clinician_auth_headers):
    res = client.get("/api/audit/verify", headers=clinician_auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
