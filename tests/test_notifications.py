"""
Appointment notification engine (IST timezone: UTC+5:30).

The engine used to report DELIVERED from functions whose docstrings said
"Simulate", stamp advance_notice_sent=True at booking for a notice nothing ever
sent, keep the in-app queue in a module-level list that emptied on restart, and
run only when a human called an endpoint. These tests hold the fixes in place:

1. Booking claims nothing. No flag is set, no delivery status is invented.
2. An unconfigured channel reports NOT_CONFIGURED and never DELIVERED.
3. A missing address reports NO_CONTACT_ON_RECORD instead of a placeholder.
4. The advance reminder actually exists, fires at the configured offset, and is
   idempotent.
5. In-app notifications are persisted and survive a new session.
6. The e-mail and SMS paths are real code paths, exercised here against fakes.

The audit event is SAME_DAY_ALERT_DISPATCHED / ADVANCE_NOTICE_DISPATCHED. It was
renamed from SAME_DAY_NOTIFICATION_SENT because "SENT" was precisely the claim
that could not be supported.
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.models.database import (
    AppointmentDB,
    AuditLogDB,
    NotificationDB,
    SessionLocal,
    now_ist,
)
from backend import notifications as notif
from backend.notifications import (
    DELIVERED,
    FAILED,
    NO_CONTACT,
    NOT_CONFIGURED,
    format_ist_datetime,
    scan_and_trigger_advance_notifications,
    scan_and_trigger_same_day_notifications,
)

client = TestClient(app)


@pytest.fixture
def doctor_headers():
    tok = client.post(
        "/api/auth/login",
        json={"username": "dr_notif_test", "role": "ATTENDING_PHYSICIAN"},
    ).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


@pytest.fixture
def fresh_doctor_headers():
    """
    A clinician with no e-mail remembered yet.

    The shared `doctor_headers` clinician accumulates a stored address as soon as
    any test books with one -- which is the feature working -- so tests asserting
    "nothing on file" need an identity of their own.
    """
    import uuid
    username = f"dr_fresh_{uuid.uuid4().hex[:8]}"
    tok = client.post(
        "/api/auth/login",
        json={"username": username, "role": "ATTENDING_PHYSICIAN"},
    ).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


@pytest.fixture
def patient_record(doctor_headers):
    return client.post(
        "/api/patients",
        headers=doctor_headers,
        json={"age": 58, "sex": "MALE", "age_category": "ADULT"},
    ).json()


def _book(headers, patient_id, when, **contact):
    payload = {
        "patient_id": patient_id,
        "appointment_date": when.isoformat(),
        "reason": "Post-antimicrobial clinical evaluation",
    }
    payload.update(contact)
    return client.post("/api/appointments", headers=headers, json=payload)


def _appointment(appointment_id):
    db = SessionLocal()
    try:
        return db.query(AppointmentDB).filter(
            AppointmentDB.appointment_id == appointment_id).first()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Booking makes no delivery claim
# ---------------------------------------------------------------------------

def test_booking_does_not_claim_any_notification_was_sent(doctor_headers, patient_record):
    """
    advance_notice_sent used to be set True at booking, alongside a stored
    "SCHEDULED_2_DAYS_PRIOR" status, for a notice no code path ever sent.
    """
    future = now_ist() + timedelta(days=30)
    res = _book(doctor_headers, patient_record["patient_id"], future,
                doctor_email="dr@hospital.org", patient_email="p@example.org")
    assert res.status_code == 201

    appt = _appointment(res.json()["appointment_id"])
    assert appt.advance_notice_sent is False
    assert appt.same_day_alert_sent is False
    assert appt.notification_sent is False
    assert appt.delivery_status_json in ("{}", None)
    assert "SCHEDULED_2_DAYS_PRIOR" not in (appt.delivery_status_json or "")


def test_missing_contact_details_are_not_replaced_with_placeholders(
    fresh_doctor_headers, patient_record
):
    """A patient with nothing on file used to be 'notified' at a fabricated address."""
    res = _book(fresh_doctor_headers, patient_record["patient_id"],
                now_ist() + timedelta(days=40))
    appt = _appointment(res.json()["appointment_id"])
    assert appt.patient_email is None
    assert appt.patient_phone is None
    assert appt.doctor_email is None


# ---------------------------------------------------------------------------
# Channels report what actually happened
# ---------------------------------------------------------------------------

def test_unconfigured_channels_never_report_delivered(doctor_headers, patient_record):
    pid = patient_record["patient_id"]
    res = _book(doctor_headers, pid, now_ist(), doctor_email="dr@hospital.org",
                patient_email="patient@example.org", patient_phone="+91-9000000000")
    assert res.status_code == 201
    assert res.json()["same_day_alert_triggered"] is True

    appt = _appointment(res.json()["appointment_id"])
    import json as _json
    delivery = _json.loads(appt.delivery_status_json)["same_day_alert"]

    # Nothing is configured in the test environment, so both remote channels must
    # say so. In-app is genuinely real and may report DELIVERED.
    assert delivery["doctor_email"] == NOT_CONFIGURED
    assert delivery["patient_email"] == NOT_CONFIGURED
    assert delivery["patient_sms"] == NOT_CONFIGURED
    assert delivery["in_app"] == DELIVERED
    assert "No SMTP server configured" in delivery["detail"]["doctor_email"]


def test_no_contact_is_distinguished_from_not_configured(doctor_headers, patient_record):
    pid = patient_record["patient_id"]
    res = _book(doctor_headers, pid, now_ist())  # no contact details at all
    appt_id = res.json()["appointment_id"]

    db = SessionLocal()
    try:
        rows = db.query(NotificationDB).filter(
            NotificationDB.appointment_id == appt_id).all()
        by_channel = {(r.channel, r.recipient_type): r.status for r in rows}
    finally:
        db.close()

    assert by_channel[("EMAIL", "PATIENT")] == NO_CONTACT
    assert by_channel[("SMS", "PATIENT")] == NO_CONTACT
    assert by_channel[("IN_APP", "DOCTOR")] == DELIVERED


def test_every_attempt_is_persisted_including_the_ones_that_sent_nothing(
    doctor_headers, patient_record
):
    res = _book(doctor_headers, patient_record["patient_id"], now_ist(),
                patient_email="p@example.org", patient_phone="+91-9000000001")
    appt_id = res.json()["appointment_id"]

    db = SessionLocal()
    try:
        rows = db.query(NotificationDB).filter(
            NotificationDB.appointment_id == appt_id).all()
    finally:
        db.close()

    # doctor e-mail, patient e-mail, patient SMS, in-app.
    assert len(rows) == 4
    for row in rows:
        assert row.status in (DELIVERED, FAILED, NOT_CONFIGURED, NO_CONTACT)
        assert row.detail or row.status == DELIVERED


def test_in_app_notifications_survive_a_new_session(doctor_headers, patient_record):
    """They used to live in a module-level list that emptied on restart."""
    pid = patient_record["patient_id"]
    _book(doctor_headers, pid, now_ist(), patient_email="p@example.org")

    listed = client.get(f"/api/notifications/in-app?patient_id={pid}").json()
    assert len(listed) >= 1
    assert listed[0]["patient_id"] == pid

    db = SessionLocal()
    try:
        stored = db.query(NotificationDB).filter(
            NotificationDB.patient_id == pid,
            NotificationDB.channel == "IN_APP",
        ).count()
    finally:
        db.close()
    assert stored >= 1


# ---------------------------------------------------------------------------
# The channels are real code paths
# ---------------------------------------------------------------------------

def test_email_path_actually_talks_to_smtp_when_configured(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            sent["starttls"] = True

        def login(self, user, password):
            sent["user"] = user

        def send_message(self, message):
            sent["to"] = message["To"]
            sent["subject"] = message["Subject"]

    monkeypatch.setattr(notif, "NOTIFICATION_SMTP_HOST", "smtp.example.org")
    monkeypatch.setattr(notif, "NOTIFICATION_SMTP_FROM", "noreply@example.org")
    monkeypatch.setattr(notif, "NOTIFICATION_SMTP_USER", "")
    monkeypatch.setattr(notif, "email_channel_configured", lambda: True)
    monkeypatch.setattr(notif.smtplib, "SMTP", FakeSMTP)

    result = notif.send_email("doctor@hospital.org", "Subject line", "Body text")
    assert result["status"] == DELIVERED
    assert sent["host"] == "smtp.example.org"
    assert sent["to"] == "doctor@hospital.org"


def test_email_failure_is_reported_as_failure_not_delivery(monkeypatch):
    def explode(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(notif, "email_channel_configured", lambda: True)
    monkeypatch.setattr(notif.smtplib, "SMTP", explode)

    result = notif.send_email("doctor@hospital.org", "Subject", "Body")
    assert result["status"] == FAILED
    assert "connection refused" in result["detail"]


def test_sms_path_posts_to_the_configured_webhook(monkeypatch):
    posted = {}

    class FakeResponse:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        posted["url"] = request.full_url
        posted["body"] = request.data.decode("utf-8")
        return FakeResponse()

    monkeypatch.setattr(notif, "NOTIFICATION_SMS_WEBHOOK_URL", "https://sms.example.org/send")
    monkeypatch.setattr(notif, "sms_channel_configured", lambda: True)
    monkeypatch.setattr(notif.urllib.request, "urlopen", fake_urlopen)

    result = notif.send_sms("+91-9000000000", "Reminder text")
    assert result["status"] == DELIVERED
    assert posted["url"] == "https://sms.example.org/send"
    assert "+91-9000000000" in posted["body"]


# ---------------------------------------------------------------------------
# The advance reminder exists
# ---------------------------------------------------------------------------

def test_advance_notice_fires_at_the_configured_offset_and_only_once(
    doctor_headers, patient_record
):
    pid = patient_record["patient_id"]
    two_days_out = now_ist() + timedelta(days=2)
    res = _book(doctor_headers, pid, two_days_out, patient_email="p@example.org")
    appt_id = res.json()["appointment_id"]

    assert _appointment(appt_id).advance_notice_sent is False

    db = SessionLocal()
    try:
        report = scan_and_trigger_advance_notifications(db, advance_days=2)
    finally:
        db.close()
    assert any(r["appointment_id"] == appt_id for r in report["dispatched_records"])

    appt = _appointment(appt_id)
    assert appt.advance_notice_sent is True
    assert appt.advance_notice_timestamp is not None

    # Idempotent: the scheduler runs repeatedly and must not re-send.
    db = SessionLocal()
    try:
        second = scan_and_trigger_advance_notifications(db, advance_days=2)
    finally:
        db.close()
    assert all(r["appointment_id"] != appt_id for r in second["dispatched_records"])


def test_advance_notice_does_not_fire_for_an_appointment_outside_the_window(
    doctor_headers, patient_record
):
    res = _book(doctor_headers, patient_record["patient_id"],
                now_ist() + timedelta(days=25), patient_email="p@example.org")
    appt_id = res.json()["appointment_id"]

    db = SessionLocal()
    try:
        report = scan_and_trigger_advance_notifications(db, advance_days=2)
    finally:
        db.close()

    assert all(r["appointment_id"] != appt_id for r in report["dispatched_records"])
    assert _appointment(appt_id).advance_notice_sent is False


# ---------------------------------------------------------------------------
# Same-day scan, audit trail, and status reporting
# ---------------------------------------------------------------------------

def test_same_day_scan_and_next_appointment_lookup(doctor_headers, patient_record):
    pid = patient_record["patient_id"]
    res = _book(doctor_headers, pid, now_ist(), doctor_email="dr@hospital.org",
                patient_email="p@example.org", patient_phone="+91-9876543210")
    assert res.status_code == 201
    data = res.json()
    assert data["same_day_alert_triggered"] is True
    assert "day_of_week" in data and "time" in data

    next_data = client.get(f"/api/patients/{pid}/next-appointment").json()
    assert next_data["has_appointment"] is True
    assert next_data["appointment_id"] == data["appointment_id"]
    assert next_data["is_today"] is True
    assert next_data["same_day_alert_sent"] is True


def test_audit_event_records_the_real_per_channel_outcome(doctor_headers, patient_record):
    pid = patient_record["patient_id"]
    _book(doctor_headers, pid, now_ist(), patient_email="p@example.org")

    db = SessionLocal()
    try:
        logs = (
            db.query(AuditLogDB)
            .filter(AuditLogDB.event_type == "SAME_DAY_ALERT_DISPATCHED")
            .order_by(AuditLogDB.id.desc())
            .all()
        )
    finally:
        db.close()

    assert logs, "no dispatch audit event was written"
    summary = logs[0].action_summary
    assert "dispatched" in summary.lower()
    # The outcome, not a bare assertion that it was sent.
    assert NOT_CONFIGURED in summary or DELIVERED in summary


def test_trigger_endpoint_still_works(doctor_headers, patient_record):
    _book(doctor_headers, patient_record["patient_id"], now_ist() + timedelta(hours=2),
          patient_email="p@example.org")
    res = client.post("/api/notifications/trigger-same-day", headers=doctor_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "SUCCESS"


def test_run_scan_endpoint_runs_both_scans(doctor_headers):
    res = client.post("/api/notifications/run-scan", headers=doctor_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["advance"]["notification_kind"] == "ADVANCE_NOTICE"
    assert body["same_day"]["notification_kind"] == "SAME_DAY_ALERT"


def test_status_endpoint_states_plainly_what_cannot_be_delivered():
    body = client.get("/api/notifications/status").json()
    assert body["channels"]["email"]["configured"] is False
    assert "NOT sent" in body["channels"]["email"]["note"]
    assert body["channels"]["sms"]["configured"] is False
    assert body["channels"]["in_app"]["configured"] is True
    assert "scheduler" in body
    assert "interval_seconds" in body["scheduler"]
    assert isinstance(body["delivery_attempts_by_status"], dict)


def test_ist_formatting_is_unchanged():
    info = format_ist_datetime(now_ist())
    assert "IST" in info["formatted"]
    assert info["day_of_week"]


# ---------------------------------------------------------------------------
# Contact resolution: a returning patient is not asked twice
# ---------------------------------------------------------------------------

def _register(headers, **extra):
    payload = {"age": 44, "sex": "FEMALE", "age_category": "ADULT"}
    payload.update(extra)
    return client.post("/api/patients", headers=headers, json=payload).json()


def test_email_given_at_registration_is_used_without_being_asked_again(doctor_headers):
    patient = _register(doctor_headers, display_name="Returning Patient",
                        contact_email="returning@example.org",
                        contact_phone="+91-9000000123")
    pid = patient["patient_id"]

    # Booking supplies no contact details at all.
    res = _book(doctor_headers, pid, now_ist() + timedelta(days=2))
    assert res.status_code == 201
    contacts = res.json()["reminder_contacts"]
    assert contacts["patient_email"] == "returning@example.org"
    assert contacts["patient_phone"] == "+91-9000000123"
    assert contacts["patient_email_source"] == "PATIENT_RECORD"

    appt = _appointment(res.json()["appointment_id"])
    assert appt.patient_email == "returning@example.org"


def test_an_email_supplied_at_booking_is_remembered_for_next_time(doctor_headers):
    pid = _register(doctor_headers, display_name="New Patient")["patient_id"]

    first = _book(doctor_headers, pid, now_ist() + timedelta(days=2),
                  patient_email="first.time@example.org")
    assert first.json()["reminder_contacts"]["patient_email_source"] == "SUPPLIED_NOW"

    # Second booking asks for nothing and still resolves.
    second = _book(doctor_headers, pid, now_ist() + timedelta(days=9))
    contacts = second.json()["reminder_contacts"]
    assert contacts["patient_email"] == "first.time@example.org"
    assert contacts["patient_email_source"] == "PATIENT_RECORD"


def test_contact_endpoint_adds_and_clears_reminder_details(doctor_headers):
    pid = _register(doctor_headers, display_name="Contact Update")["patient_id"]

    added = client.put(f"/api/patients/{pid}/contact", headers=doctor_headers,
                       json={"contact_email": "added@example.org"}).json()
    assert added["contact_email"] == "added@example.org"
    assert added["reminders_reachable"] is True

    # An empty string is how consent is withdrawn.
    cleared = client.put(f"/api/patients/{pid}/contact", headers=doctor_headers,
                         json={"contact_email": "", "contact_phone": ""}).json()
    assert cleared["contact_email"] is None
    assert cleared["reminders_reachable"] is False


def test_booking_reports_when_nobody_can_be_reached(doctor_headers, fresh_doctor_headers):
    pid = _register(doctor_headers, display_name="Unreachable")["patient_id"]
    res = _book(fresh_doctor_headers, pid, now_ist() + timedelta(days=2))
    contacts = res.json()["reminder_contacts"]
    assert contacts["patient_email"] is None
    assert contacts["patient_email_source"] == "NONE_ON_FILE"
    assert contacts["doctor_email_source"] == "NONE_ON_FILE"


def test_the_doctor_reminder_names_the_patient_and_the_time(doctor_headers):
    """
    The doctor half of the reminder: which patient, on what day, at what time.
    """
    patient = _register(doctor_headers, display_name="Sunita Devi")
    pid = patient["patient_id"]
    when = now_ist()
    res = _book(doctor_headers, pid, when, doctor_email="clinician@hospital.org")
    appt_id = res.json()["appointment_id"]

    db = SessionLocal()
    try:
        doctor_note = (
            db.query(NotificationDB)
            .filter(
                NotificationDB.appointment_id == appt_id,
                NotificationDB.recipient_type == "DOCTOR",
                NotificationDB.channel == "EMAIL",
            )
            .first()
        )
    finally:
        db.close()

    assert doctor_note is not None
    assert doctor_note.recipient == "clinician@hospital.org"
    body = doctor_note.message
    assert "Sunita Devi" in body            # which patient
    assert format_ist_datetime(when)["day_of_week"] in body   # which day
    assert format_ist_datetime(when)["time"] in body          # at what time
    assert "Reason for visit" in body


def test_doctor_email_is_remembered_on_the_doctor_record(doctor_headers):
    pid = _register(doctor_headers, display_name="Doctor Recall")["patient_id"]
    _book(doctor_headers, pid, now_ist() + timedelta(days=3),
          doctor_email="remembered.clinician@hospital.org")

    # A later booking that supplies no clinician address still reaches them.
    second = _book(doctor_headers, pid, now_ist() + timedelta(days=11))
    contacts = second.json()["reminder_contacts"]
    assert contacts["doctor_email"] == "remembered.clinician@hospital.org"
    assert contacts["doctor_email_source"] == "DOCTOR_RECORD"
