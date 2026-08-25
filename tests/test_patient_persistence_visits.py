"""
Tests for Persistent Patient Storage & Visit History Timeline with Day of Week, Date, and Time.

Verifies:
1. Patients added to the system persist across database re-initialization and app restarts.
2. Visits created for existing patients accurately append to their history with correct
   date, time, day_of_week, and formatted_date fields.
"""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.models.database import SessionLocal, PatientDB, VisitDB
from backend.seed_data import seed_database

client = TestClient(app)


@pytest.fixture
def doctor_headers():
    tok = client.post(
        "/api/auth/login",
        json={"username": "dr_persistence_test", "role": "ATTENDING_PHYSICIAN"},
    ).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_new_patient_persistence_across_app_restart(doctor_headers):
    """
    Ensure any new patient registered via API is persisted in SQLite DB
    and remains present after simulating an application restart (re-running seed_database).
    """
    # 1. Register a new patient
    res = client.post(
        "/api/patients",
        headers=doctor_headers,
        json={
            "age": 42,
            "sex": "FEMALE",
            "age_category": "ADULT",
            "weight_kg": 65.0,
            "clinical_notes": "Persistent storage integration test patient.",
        },
    )
    assert res.status_code == 201
    patient_data = res.json()
    patient_id = patient_data["patient_id"]
    assert patient_id.startswith("PATIENT-")

    # 2. Verify patient appears in patient list immediately
    list_res = client.get("/api/patients")
    assert list_res.status_code == 200
    pids = [p["patient_id"] for p in list_res.json()]
    assert patient_id in pids

    # 3. Simulate App Restart by running seed_database(reset_patients=False)
    seed_database(reset_patients=False)

    # 4. Verify patient is still retained in patient list after restart
    list_after = client.get("/api/patients")
    assert list_after.status_code == 200
    pids_after = [p["patient_id"] for p in list_after.json()]
    assert patient_id in pids_after, f"Patient {patient_id} must persist across app restarts"

    # Direct database check
    db = SessionLocal()
    db_patient = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
    assert db_patient is not None
    assert db_patient.age == 42
    db.close()


def test_visit_appends_to_patient_history_with_date_time_and_day_of_week(doctor_headers):
    """
    Ensure a new visit recorded for an existing patient appends to their history
    and captures date, time, and day of the week accurately.
    """
    # 1. Create patient
    reg = client.post(
        "/api/patients",
        headers=doctor_headers,
        json={"age": 50, "sex": "MALE", "age_category": "ADULT"},
    ).json()
    pid = reg["patient_id"]

    # 2. Append First Visit
    v1_res = client.post(
        f"/api/patients/{pid}/visits",
        headers=doctor_headers,
        json={
            "patient_id": pid,
            "diagnosis": "Acute Bronchitis",
            "symptoms_text": "Cough and mild fever",
            "symptoms": [{"name": "Cough", "severity": "Moderate", "duration": "4 days"}],
            "raw_prescription_text": "Azithromycin 500mg PO QD x 3 days",
            "prescription_items": [
                {
                    "medication_name": "Azithromycin",
                    "dose": 500,
                    "unit": "mg",
                    "route": "PO",
                    "frequency": "QD",
                    "duration_days": 3,
                }
            ],
        },
    )
    assert v1_res.status_code == 201
    v1_data = v1_res.json()
    assert v1_data["status"] == "SAVED"
    assert "day_of_week" in v1_data
    assert "time" in v1_data
    assert "date" in v1_data
    assert "formatted_date" in v1_data

    # 3. Append Second Visit (Follow-up visit)
    v2_res = client.post(
        f"/api/patients/{pid}/visits",
        headers=doctor_headers,
        json={
            "patient_id": pid,
            "diagnosis": "Follow-up Resolution",
            "symptoms_text": "Symptoms resolved",
            "symptoms": [{"name": "Cough", "severity": "Mild", "duration": "1 day"}],
            "raw_prescription_text": "",
            "prescription_items": [],
        },
    )
    assert v2_res.status_code == 201
    v2_data = v2_res.json()
    assert v2_data["status"] == "SAVED"

    # 4. Fetch Patient History Timeline
    hist_res = client.get(f"/api/patients/{pid}/history")
    assert hist_res.status_code == 200
    history = hist_res.json()

    visits = history["visits"]
    assert len(visits) == 2, "Both visits must be appended to the patient's history timeline"

    # Verify visit ordering (descending by date)
    latest_visit = visits[0]
    first_visit = visits[1]

    assert latest_visit["diagnosis"] == "Follow-up Resolution"
    assert first_visit["diagnosis"] == "Acute Bronchitis"

    # Verify date, time, and day of week attributes
    for v in visits:
        assert v["day_of_week"] != "", "Visit must capture day of week (e.g. Tuesday)"
        assert v["time"] != "", "Visit must capture time (e.g. 03:37 PM)"
        assert v["date"] != "", "Visit must capture date"
        assert v["day_of_week"] in [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        assert v["formatted_date"].startswith(v["day_of_week"])
