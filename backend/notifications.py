"""
Appointment notification engine (IST timezone: UTC+5:30).

WHAT CHANGED AND WHY
--------------------
This module used to return {"status": "DELIVERED"} from two functions whose own
docstrings said "Simulate". No SMTP server was contacted, no SMS provider existed,
and the appointment record was stamped as notified anyway. A record asserting a
delivery that never happened is the same class of false claim as a citation
asserting a page that does not exist, and it is worse here: a clinician reading
"patient reminded" would reasonably stop chasing the patient.

The channels are now real, and honest about themselves:

  EMAIL    real SMTP when configured; NOT_CONFIGURED when not
  SMS      real webhook POST when configured; NOT_CONFIGURED when not
  IN_APP   always real, persisted to the notifications table

No channel may report DELIVERED unless something actually accepted the message.
Every attempt -- delivered, failed, unconfigured, or skipped for want of an
address -- is written to the notifications table, so "nothing was sent" is a
recorded fact rather than an absence someone has to infer.
"""

import json
import smtplib
import urllib.error
import urllib.request
import uuid
from datetime import datetime, time, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.audit.logger import audit_logger
from backend.config import (
    NOTIFICATION_ADVANCE_NOTICE_DAYS,
    NOTIFICATION_SMS_AUTH_HEADER,
    NOTIFICATION_SMS_TIMEOUT_SECONDS,
    NOTIFICATION_SMS_WEBHOOK_URL,
    NOTIFICATION_SMTP_FROM,
    NOTIFICATION_SMTP_HOST,
    NOTIFICATION_SMTP_PASSWORD,
    NOTIFICATION_SMTP_PORT,
    NOTIFICATION_SMTP_STARTTLS,
    NOTIFICATION_SMTP_TIMEOUT_SECONDS,
    NOTIFICATION_SMTP_USER,
    email_channel_configured,
    sms_channel_configured,
)
from backend.models.database import (
    IST,
    AppointmentDB,
    NotificationDB,
    PatientDB,
    now_ist,
)

# Delivery outcomes. DELIVERED is reserved for a message a provider accepted.
DELIVERED = "DELIVERED"
FAILED = "FAILED"
NOT_CONFIGURED = "NOT_CONFIGURED"
NO_CONTACT = "NO_CONTACT_ON_RECORD"

SAME_DAY_ALERT = "SAME_DAY_ALERT"
ADVANCE_NOTICE = "ADVANCE_NOTICE"


def get_ist_bounds_for_date(target_date: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Calculate 00:00:00 and 23:59:59 bounds in IST for a given date."""
    ref_dt = target_date if target_date else now_ist()
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=IST)
    else:
        ref_dt = ref_dt.astimezone(IST)

    d = ref_dt.date()
    start_bound = datetime.combine(d, time.min, tzinfo=IST)
    end_bound = datetime.combine(d, time.max, tzinfo=IST)
    return start_bound, end_bound


def format_ist_datetime(dt: Optional[datetime]) -> Dict[str, str]:
    """
    Format a datetime into IST day, date, time, and full label.

    A NAIVE datetime is read as IST, not UTC. This is the difference between a
    reminder that states the appointment time and one that states a time five and a
    half hours later: every datetime in this system is written as IST wall-clock
    (now_ist, and the IST-normalised appointment_date), but SQLite drops the offset
    on storage. Treating what comes back as UTC re-applied the +05:30 on every
    read, so an appointment booked for 01:27 was announced to the patient and the
    clinician as 06:57.
    """
    if not dt:
        return {"date": "N/A", "time": "N/A", "day_of_week": "N/A", "formatted": "N/A"}

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)

    return {
        "date": dt.strftime("%d %B %Y"),
        "time": dt.strftime("%I:%M %p"),
        "day_of_week": dt.strftime("%A"),
        "formatted": f"{dt.strftime('%A')}, {dt.strftime('%d %B %Y')} at {dt.strftime('%I:%M %p')} IST",
        "iso": dt.isoformat(),
    }


# ---------------------------------------------------------------------------
# Message composition
# ---------------------------------------------------------------------------

def _compose(kind: str, recipient_type: str, patient_label: str, doctor_id: str,
             appointment_id: str, reason: str, formatted_time: str) -> tuple[str, str]:
    """Subject and body for one recipient. Pure, so it can be tested without a server."""
    when = "today" if kind == SAME_DAY_ALERT else f"on {formatted_time}"
    subject = (
        f"[AntiBioTix] Scheduled clinical check-up "
        f"{'today' if kind == SAME_DAY_ALERT else 'reminder'} ({formatted_time})"
    )

    if recipient_type == "DOCTOR":
        body = (
            f"Dear Clinician ({doctor_id}),\n\n"
            f"You have a scheduled clinical check-up {when} with patient {patient_label} "
            f"at {formatted_time}.\n"
            f"Reason for visit: {reason}\n"
            f"Appointment reference: {appointment_id}\n\n"
            "Please review the patient's active medications and rule history on the "
            "AntiBioTix console before the visit."
        )
    else:
        body = (
            "AntiBioTix appointment reminder\n\n"
            f"You have a clinical check-up {when} at {formatted_time} with Dr. {doctor_id}.\n"
            f"Reason: {reason}\n"
            f"Reference: {appointment_id}\n\n"
            "Please bring all your current medications with you.\n\n"
            "This is an appointment reminder only. It is not medical advice. If you feel "
            "unwell before your appointment, contact your clinician or your nearest "
            "health facility."
        )
    return subject, body


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

def send_email(recipient: Optional[str], subject: str, body: str) -> Dict[str, str]:
    """
    Send one e-mail over SMTP.

    Returns the real outcome. NOT_CONFIGURED is not a failure -- it is the correct
    description of a system with no mail server, and it must never be dressed up
    as a delivery.
    """
    if not recipient:
        return {"status": NO_CONTACT, "detail": "No e-mail address on record for this recipient."}
    if not email_channel_configured():
        return {
            "status": NOT_CONFIGURED,
            "detail": "No SMTP server configured (set S11_SMTP_HOST and S11_SMTP_FROM). "
                      "No e-mail was sent.",
        }

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = NOTIFICATION_SMTP_FROM or NOTIFICATION_SMTP_USER
    message["To"] = recipient
    message.set_content(body)

    try:
        with smtplib.SMTP(NOTIFICATION_SMTP_HOST, NOTIFICATION_SMTP_PORT,
                          timeout=NOTIFICATION_SMTP_TIMEOUT_SECONDS) as server:
            if NOTIFICATION_SMTP_STARTTLS:
                server.starttls()
            if NOTIFICATION_SMTP_USER:
                server.login(NOTIFICATION_SMTP_USER, NOTIFICATION_SMTP_PASSWORD)
            server.send_message(message)
        return {"status": DELIVERED, "detail": f"Accepted by {NOTIFICATION_SMTP_HOST}."}
    except Exception as exc:  # noqa: BLE001 - the reason is recorded, not swallowed
        return {"status": FAILED, "detail": f"{type(exc).__name__}: {exc}"}


def send_sms(recipient: Optional[str], message: str) -> Dict[str, str]:
    """POST the message to the configured SMS webhook. Provider-agnostic."""
    if not recipient:
        return {"status": NO_CONTACT, "detail": "No phone number on record for this recipient."}
    if not sms_channel_configured():
        return {
            "status": NOT_CONFIGURED,
            "detail": "No SMS webhook configured (set S11_SMS_WEBHOOK_URL). No SMS was sent.",
        }

    payload = json.dumps({"to": recipient, "message": message}).encode("utf-8")
    request = urllib.request.Request(
        NOTIFICATION_SMS_WEBHOOK_URL, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    if NOTIFICATION_SMS_AUTH_HEADER:
        request.add_header("Authorization", NOTIFICATION_SMS_AUTH_HEADER)

    try:
        with urllib.request.urlopen(request, timeout=NOTIFICATION_SMS_TIMEOUT_SECONDS) as response:
            if 200 <= response.status < 300:
                return {"status": DELIVERED, "detail": f"Provider responded {response.status}."}
            return {"status": FAILED, "detail": f"Provider responded {response.status}."}
    except urllib.error.HTTPError as exc:
        return {"status": FAILED, "detail": f"HTTP {exc.code} from SMS provider."}
    except Exception as exc:  # noqa: BLE001
        return {"status": FAILED, "detail": f"{type(exc).__name__}: {exc}"}


def _record(db: Session, *, kind: str, channel: str, recipient_type: str,
            recipient: Optional[str], appointment: AppointmentDB, title: str,
            message: str, outcome: Dict[str, str]) -> NotificationDB:
    """Persist one dispatch attempt, whatever its outcome."""
    row = NotificationDB(
        notification_id=f"NOTIF-{uuid.uuid4().hex[:10].upper()}",
        appointment_id=appointment.appointment_id,
        patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id,
        kind=kind,
        channel=channel,
        recipient_type=recipient_type,
        recipient=recipient,
        title=title,
        message=message,
        status=outcome["status"],
        detail=outcome.get("detail"),
        read=False,
    )
    db.add(row)
    return row


def _dispatch_all_channels(db: Session, appointment: AppointmentDB, kind: str,
                           patient_label: str, time_info: Dict[str, str]) -> Dict[str, Any]:
    """Run every channel for one appointment and return the real per-channel outcome."""
    doctor_subject, doctor_body = _compose(
        kind, "DOCTOR", patient_label, appointment.doctor_id,
        appointment.appointment_id, appointment.reason, time_info["formatted"])
    patient_subject, patient_body = _compose(
        kind, "PATIENT", patient_label, appointment.doctor_id,
        appointment.appointment_id, appointment.reason, time_info["formatted"])

    doctor_email = send_email(appointment.doctor_email, doctor_subject, doctor_body)
    _record(db, kind=kind, channel="EMAIL", recipient_type="DOCTOR",
            recipient=appointment.doctor_email, appointment=appointment,
            title=doctor_subject, message=doctor_body, outcome=doctor_email)

    patient_email = send_email(appointment.patient_email, patient_subject, patient_body)
    _record(db, kind=kind, channel="EMAIL", recipient_type="PATIENT",
            recipient=appointment.patient_email, appointment=appointment,
            title=patient_subject, message=patient_body, outcome=patient_email)

    sms_text = (
        f"AntiBioTix reminder: clinical check-up "
        f"{'today' if kind == SAME_DAY_ALERT else ''} at {time_info['formatted']} "
        f"with Dr. {appointment.doctor_id}. Ref {appointment.appointment_id}."
    ).replace("  ", " ")
    patient_sms = send_sms(appointment.patient_phone, sms_text)
    _record(db, kind=kind, channel="SMS", recipient_type="PATIENT",
            recipient=appointment.patient_phone, appointment=appointment,
            title="Appointment reminder", message=sms_text, outcome=patient_sms)

    # In-app is the one channel that is real without configuration, because the
    # console reads it straight back out of this table.
    in_app_title = ("Scheduled check-up today" if kind == SAME_DAY_ALERT
                    else f"Upcoming check-up on {time_info['date']}")
    in_app_message = (
        f"Check-up for patient {patient_label} at {time_info['formatted']}. "
        f"Reason: {appointment.reason}"
    )
    in_app = {"status": DELIVERED, "detail": "Queued to the in-app notification table."}
    _record(db, kind=kind, channel="IN_APP", recipient_type="DOCTOR",
            recipient=appointment.doctor_id, appointment=appointment,
            title=in_app_title, message=in_app_message, outcome=in_app)

    return {
        "doctor_email": doctor_email["status"],
        "patient_email": patient_email["status"],
        "patient_sms": patient_sms["status"],
        "in_app": in_app["status"],
        "dispatched_at_ist": now_ist().isoformat(),
        # Kept alongside the statuses so a reader never has to guess why a channel
        # says NOT_CONFIGURED.
        "detail": {
            "doctor_email": doctor_email.get("detail"),
            "patient_email": patient_email.get("detail"),
            "patient_sms": patient_sms.get("detail"),
        },
    }


def _run_scan(db: Session, appointments: List[AppointmentDB], kind: str,
              scan_label: str) -> Dict[str, Any]:
    """Dispatch for each appointment, update its flags, and write one audit event each."""
    dispatched = []
    for appt in appointments:
        patient = db.query(PatientDB).filter(PatientDB.patient_id == appt.patient_id).first()
        patient_label = patient.display_name if patient else appt.patient_id
        time_info = format_ist_datetime(appt.appointment_date)

        summary = _dispatch_all_channels(db, appt, kind, patient_label, time_info)

        if kind == SAME_DAY_ALERT:
            appt.same_day_alert_sent = True
            appt.same_day_alert_timestamp = now_ist()
        else:
            appt.advance_notice_sent = True
            appt.advance_notice_timestamp = now_ist()
        appt.notification_sent = True

        existing = {}
        try:
            existing = json.loads(appt.delivery_status_json or "{}")
        except ValueError:
            existing = {}
        existing[kind.lower()] = summary
        appt.delivery_status_json = json.dumps(existing)
        db.commit()

        audit_logger.log_event(
            db=db,
            event_type=f"{kind}_DISPATCHED",
            prescription_id="-",
            patient_id=appt.patient_id,
            clinician_id=appt.doctor_id,
            clinician_role="ATTENDING_PHYSICIAN",
            action_summary=(
                f"{scan_label} dispatched for appointment {appt.appointment_id} "
                f"({time_info['formatted']}). Channel outcomes: "
                f"doctor e-mail {summary['doctor_email']}, patient e-mail "
                f"{summary['patient_email']}, SMS {summary['patient_sms']}, "
                f"in-app {summary['in_app']}."
            ),
            payload={
                "appointment_id": appt.appointment_id,
                "appointment_date_ist": time_info["iso"],
                "reason": appt.reason,
                "notification_kind": kind,
                "delivery_summary": summary,
            },
        )

        dispatched.append({
            "appointment_id": appt.appointment_id,
            "patient_id": appt.patient_id,
            "doctor_id": appt.doctor_id,
            "reason": appt.reason,
            "formatted_time": time_info["formatted"],
            "delivery_status": summary,
        })

    return {
        "status": "SUCCESS",
        "notification_kind": kind,
        "scanned_appointments_count": len(appointments),
        "newly_dispatched_count": len(dispatched),
        "dispatched_records": dispatched,
    }


def scan_and_trigger_same_day_notifications(
    db: Session, force_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """Dispatch alerts for appointments falling on today (IST)."""
    start_bound, end_bound = get_ist_bounds_for_date(force_date)
    query = (
        db.query(AppointmentDB)
        .filter(
            AppointmentDB.appointment_date >= start_bound,
            AppointmentDB.appointment_date <= end_bound,
            AppointmentDB.status == "SCHEDULED",
        )
    )
    appointments = [a for a in query.all() if force_date or not a.same_day_alert_sent]
    report = _run_scan(db, appointments, SAME_DAY_ALERT, "Same-day check-up alert")
    report["scan_date_ist"] = start_bound.strftime("%d %B %Y")
    return report


def scan_and_trigger_advance_notifications(
    db: Session, force_date: Optional[datetime] = None,
    advance_days: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Dispatch the advance reminder for appointments N days out.

    This is the notice the appointment record used to claim it had sent. Booking
    stamped advance_notice_sent=True and wrote "SCHEDULED_2_DAYS_PRIOR" into the
    delivery status, while no code path anywhere sent anything. The flag is now
    written here, after a dispatch attempt, and never at booking.
    """
    days = NOTIFICATION_ADVANCE_NOTICE_DAYS if advance_days is None else advance_days
    reference = force_date or now_ist()
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=IST)
    target = reference.astimezone(IST) + timedelta(days=days)
    start_bound, end_bound = get_ist_bounds_for_date(target)

    query = (
        db.query(AppointmentDB)
        .filter(
            AppointmentDB.appointment_date >= start_bound,
            AppointmentDB.appointment_date <= end_bound,
            AppointmentDB.status == "SCHEDULED",
        )
    )
    appointments = [a for a in query.all() if not a.advance_notice_sent]
    report = _run_scan(db, appointments, ADVANCE_NOTICE, f"Advance ({days}-day) reminder")
    report["scan_date_ist"] = start_bound.strftime("%d %B %Y")
    report["advance_notice_days"] = days
    return report


def run_all_scans(db: Session) -> Dict[str, Any]:
    """Both scans, as the scheduler runs them."""
    return {
        "advance": scan_and_trigger_advance_notifications(db),
        "same_day": scan_and_trigger_same_day_notifications(db),
        "ran_at_ist": now_ist().isoformat(),
    }


def list_in_app_notifications(db: Session, patient_id: Optional[str] = None,
                              limit: int = 20) -> List[Dict[str, Any]]:
    """Read the in-app queue back out of the database."""
    query = db.query(NotificationDB).filter(NotificationDB.channel == "IN_APP")
    if patient_id:
        query = query.filter(NotificationDB.patient_id == patient_id)
    rows = query.order_by(NotificationDB.id.desc()).limit(limit).all()
    return [
        {
            "id": r.notification_id,
            "appointment_id": r.appointment_id,
            "patient_id": r.patient_id,
            "doctor_id": r.doctor_id,
            "kind": r.kind,
            "title": r.title,
            "message": r.message,
            "status": r.status,
            "read": bool(r.read),
            "timestamp": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def channel_status() -> Dict[str, Any]:
    """
    What this deployment can actually send, stated plainly.

    Exposed over the API so "did the patient get told?" has an answer that does not
    require reading the source.
    """
    email_ready = email_channel_configured()
    sms_ready = sms_channel_configured()
    return {
        "email": {
            "configured": email_ready,
            "host": NOTIFICATION_SMTP_HOST or None,
            "note": None if email_ready else
            "No SMTP server configured. E-mail reminders are NOT sent; every e-mail "
            "attempt is recorded as NOT_CONFIGURED. Set S11_SMTP_HOST and S11_SMTP_FROM.",
        },
        "sms": {
            "configured": sms_ready,
            "webhook": NOTIFICATION_SMS_WEBHOOK_URL or None,
            "note": None if sms_ready else
            "No SMS webhook configured. SMS reminders are NOT sent; every SMS attempt "
            "is recorded as NOT_CONFIGURED. Set S11_SMS_WEBHOOK_URL.",
        },
        "in_app": {
            "configured": True,
            "note": "Persisted to the notifications table and readable at "
                    "/api/notifications/in-app.",
        },
        "advance_notice_days": NOTIFICATION_ADVANCE_NOTICE_DAYS,
    }
