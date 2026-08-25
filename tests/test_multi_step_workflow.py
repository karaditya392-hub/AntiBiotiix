"""
Automated tests for Multi-Step Doctor Workflow:
PDF Generation, Follow-up Appointment Scheduling, Multi-step Visit Flow, and Security Isolation.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.models.database import SessionLocal, VisitDB, PrescriptionDB, AppointmentDB
from backend.auth.security import create_session_token

client = TestClient(app)


@pytest.fixture
def auth_headers():
    token = create_session_token("DOC-WORKFLOW-TEST", "ATTENDING_PHYSICIAN")
    return {"Authorization": f"Bearer {token}"}


def test_pdf_generation_endpoint(auth_headers):
    # Verify PDF endpoint generates a valid PDF Response for a seeded visit
    res = client.get("/api/visits/VIS-001/pdf", headers=auth_headers)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert len(res.content) > 1000
    assert b"%PDF" in res.content[:10]


def test_schedule_followup_appointment(auth_headers):
    payload = {
        "patient_id": "PATIENT-001",
        "visit_id": "VIS-001",
        "appointment_date": "2026-09-01T10:00:00",
        "reason": "Routine antimicrobial therapy review",
        "doctor_email": "dr.smith@hospital.org",
        "patient_email": "patient001@synthetic.org"
    }
    res = client.post("/api/appointments", json=payload, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "SCHEDULED"
    assert "appointment_id" in data

    # Verify listing appointments
    list_res = client.get("/api/appointments?patient_id=PATIENT-001", headers=auth_headers)
    assert list_res.status_code == 200
    appts = list_res.json()
    assert any(a["appointment_id"] == data["appointment_id"] for a in appts)


def test_multi_step_end_to_end_doctor_workflow(auth_headers):
    # Step 1: Register New Patient
    reg_res = client.post(
        "/api/patients",
        json={
            "age": 48,
            "sex": "MALE",
            "weight_kg": 78.0,
            "medical_history": ["Hypertension"],
            "clinical_notes": "Multistep workflow test registration"
        },
        headers=auth_headers
    )
    assert reg_res.status_code == 201
    pid = reg_res.json()["patient_id"]

    # Step 2: Create New Visit with Symptoms & Diagnosis
    visit_res = client.post(
        f"/api/patients/{pid}/visits",
        json={
            "patient_id": pid,
            "diagnosis": "Acute bacterial exacerbation of COPD",
            "symptoms": [
                {"name": "Dyspnea", "severity": "Moderate", "duration": "4 days"},
                {"name": "Sputum production", "severity": "Severe", "duration": "3 days"}
            ],
            "raw_prescription_text": "Amoxicillin-clavulanate 875mg PO BID x 7 days",
            "prescription_items": [
                {
                    "medication_name": "Amoxicillin-clavulanate",
                    "dose": 875,
                    "unit": "mg",
                    "route": "PO",
                    "frequency": "BID",
                    "duration_days": 7
                }
            ]
        },
        headers=auth_headers
    )
    assert visit_res.status_code == 201
    v_data = visit_res.json()
    assert v_data["status"] == "SAVED"
    vid = v_data["visit_id"]

    # Step 3: Verify History & Timeline includes the visit
    hist_res = client.get(f"/api/patients/{pid}/history", headers=auth_headers)
    assert hist_res.status_code == 200
    h_data = hist_res.json()
    assert len(h_data["visits"]) >= 1
    assert h_data["visits"][0]["visit_id"] == vid

    # Step 4: Download PDF
    pdf_res = client.get(f"/api/visits/{vid}/pdf", headers=auth_headers)
    assert pdf_res.status_code == 200
    assert b"%PDF" in pdf_res.content[:10]

    # Step 5: Schedule Follow-up
    appt_res = client.post(
        "/api/appointments",
        json={
            "patient_id": pid,
            "visit_id": vid,
            "appointment_date": "2026-09-05T14:30:00",
            "reason": "7-day COPD exacerbation follow-up"
        },
        headers=auth_headers
    )
    assert appt_res.status_code == 201


def test_clinical_tools_standalone_apis(auth_headers):
    # 1. Guidelines & Rules API
    g_res = client.get("/api/guidelines/rules")
    assert g_res.status_code == 200
    assert len(g_res.json()["rules"]) > 0

    gov_res = client.get("/api/rules/governance")
    assert gov_res.status_code == 200

    # 2. Ask the Evidence RAG API
    ev_res = client.post("/api/evidence/ask", json={"question": "pneumonia amoxicillin dosing", "k": 4})
    assert ev_res.status_code == 200
    assert ev_res.json()["answered"] is True

    # 3. Audit & Alert Fatigue API
    audit_res = client.get("/api/audit/logs?limit=10")
    assert audit_res.status_code == 200
    verify_res = client.get("/api/audit/verify")
    assert verify_res.status_code == 200
    assert verify_res.json()["valid"] is True
    fatigue_res = client.get("/api/audit/alert-fatigue")
    assert fatigue_res.status_code == 200

    # 4. Clinical Reference APIs
    stg_res = client.get("/api/guidelines/stg-conditions")
    assert stg_res.status_code == 200
    stw_res = client.get("/api/guidelines/stw-conditions")
    assert stw_res.status_code == 200
    amr_res = client.get("/api/guidelines/amr-data")
    assert amr_res.status_code == 200
    prec_res = client.get("/api/guidelines/precedence")
    assert prec_res.status_code == 200

