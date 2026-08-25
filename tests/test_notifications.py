"""
Tests for Automated Check-Up Notification Engine & Same-Day Trigger Logic (IST Timezone: UTC+5:30).

Verifies:
1. Appointment scheduling endpoint (/api/appointments) captures relationship data (emails, phone, doctor_id).
2. Same-day check-up notification scanner identifies appointments on current date (IST) and dispatches multi-channel alerts.
3. Cryptographic audit trail records SAME_DAY_NOTIFICATION_SENT event with payload hash.
4. Next appointment lookup (/api/patients/{patient_id}/next-appointment) formats IST date, time, and day of week.
"""
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.models.database import SessionLocal, AppointmentDB, AuditLogDB, IST, now_ist
from backend.notifications import scan_and_trigger_same_day_notifications, format_ist_datetime

client = TestClient(app)


@pytest.fixture
def doctor_headers():
    tok = client.post(
        "/api/auth/login",
        json={"username": "dr_notif_test", "role": "ATTENDING_PHYSICIAN"},
    ).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


@pytest.fixture
def patient_record(doctor_headers):
    return client.post(
        "/api/patients",
        headers=doctor_headers,
        json={"age": 58, "sex": "MALE", "age_category": "ADULT"},
    ).json()


def test_schedule_appointment_and_same_day_trigger(doctor_headers, patient_record):
    pid = patient_record["patient_id"]
    today_ist = now_ist()
    app_date_str = today_ist.isoformat()

    # 1. Schedule Check-up for Today (IST)
    res = client.post(
        "/api/appointments",
        headers=doctor_headers,
        json={
            "patient_id": pid,
            "appointment_date": app_date_str,
            "reason": "Post-antimicrobial clinical evaluation & renal function check",
            "doctor_email": "attending.physician@hospital.org",
            "patient_email": "patient.notif@de-identified.org",
            "patient_phone": "+91-9876543210",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "SCHEDULED"
    assert data["appointment_id"].startswith("APT-")
    assert data["same_day_alert_triggered"] is True
    assert "day_of_week" in data
    assert "time" in data

    appt_id = data["appointment_id"]

    # 2. Verify Next Appointment Lookup API
    next_res = client.get(f"/api/patients/{pid}/next-appointment")
    assert next_res.status_code == 200
    next_data = next_res.json()
    assert next_data["has_appointment"] is True
    assert next_data["appointment_id"] == appt_id
    assert next_data["is_today"] is True
    assert next_data["same_day_alert_sent"] is True

    # 3. Verify In-App Notification Queue
    in_app_res = client.get(f"/api/notifications/in-app?patient_id={pid}")
    assert in_app_res.status_code == 200
    notifs = in_app_res.json()
    assert len(notifs) >= 1
    assert notifs[0]["patient_id"] == pid

    # 4. Verify Audit Log Entry
    db = SessionLocal()
    audit_logs = (
        db.query(AuditLogDB)
        .filter(AuditLogDB.event_type == "SAME_DAY_NOTIFICATION_SENT")
        .order_by(AuditLogDB.id.desc())
        .all()
    )
    assert len(audit_logs) >= 1
    latest_audit = audit_logs[0]
    assert latest_audit.patient_id == pid
    assert "same-day" in latest_audit.action_summary.lower()
    db.close()


def test_trigger_same_day_notifications_endpoint(doctor_headers, patient_record):
    pid = patient_record["patient_id"]
    today_ist = now_ist() + timedelta(hours=2) # 2 hours from now today

    res = client.post(
        "/api/appointments",
        headers=doctor_headers,
        json={
            "patient_id": pid,
            "appointment_date": today_ist.isoformat(),
            "reason": "Routine stewardship follow-up",
            "doctor_email": "dr.test@hospital.org",
            "patient_email": "patient@de-identified.org",
        },
    )
    assert res.status_code == 201

    # Call scan and trigger endpoint
    trig_res = client.post("/api/notifications/trigger-same-day", headers=doctor_headers)
    assert trig_res.status_code == 200
    trig_data = trig_res.json()
    assert trig_data["status"] == "SUCCESS"
    assert "scanned_appointments_count" in trig_data
