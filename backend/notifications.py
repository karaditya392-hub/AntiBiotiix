"""
Automated Multi-Channel Check-Up Notification Engine (IST Timezone: UTC+5:30)
Handles scheduling events, same-day scan triggers, multi-channel delivery (Email, SMS, In-App),
and immutable audit logging.
"""

import json
from datetime import datetime, time, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.models.database import (
    AppointmentDB, PatientDB, DoctorDB, VisitDB, IST, now_ist
)
from backend.audit.logger import audit_logger

# Real-time in-app notification memory queue
IN_APP_NOTIFICATIONS_STORE: List[Dict[str, Any]] = []


def get_ist_bounds_for_date(target_date: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Calculate 00:00:00 and 23:59:59 bounds in IST for a given date."""
    ref_dt = target_date if target_date else now_ist()
    # Normalize to IST if naive
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=IST)
    else:
        ref_dt = ref_dt.astimezone(IST)

    d = ref_dt.date()
    start_bound = datetime.combine(d, time.min, tzinfo=IST)
    end_bound = datetime.combine(d, time.max, tzinfo=IST)
    return start_bound, end_bound


def format_ist_datetime(dt: Optional[datetime]) -> Dict[str, str]:
    """Format a datetime into IST day, date, time, and full label."""
    if not dt:
        return {"date": "N/A", "time": "N/A", "day_of_week": "N/A", "formatted": "N/A"}
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        dt = dt.astimezone(IST)

    day_of_week = dt.strftime("%A")
    date_str = dt.strftime("%d %B %Y")
    time_str = dt.strftime("%I:%M %p")
    formatted = f"{day_of_week}, {date_str} at {time_str} IST"

    return {
        "date": date_str,
        "time": time_str,
        "day_of_week": day_of_week,
        "formatted": formatted,
        "iso": dt.isoformat()
    }


def dispatch_email_notification(
    recipient_email: str,
    recipient_type: str, # "DOCTOR" or "PATIENT"
    patient_id: str,
    doctor_id: str,
    appointment_id: str,
    reason: str,
    formatted_time: str
) -> Dict[str, Any]:
    """Simulate structured HTML email dispatch."""
    subject = f"[AntiBioTix Alert] Scheduled Clinical Check-up Today ({formatted_time})"
    if recipient_type == "DOCTOR":
        body = (
            f"Dear Clinician ({doctor_id}),\n\n"
            f"Reminder: You have a scheduled clinical check-up today with Patient {patient_id} at {formatted_time}.\n"
            f"Reason for Visit: {reason}\n"
            f"Appointment Reference: {appointment_id}\n\n"
            "Please review the patient's active medications and rule history on the AntiBioTix Console before the visit."
        )
    else:
        body = (
            f"AntiBioTix Patient Reminder:\n\n"
            f"You have a scheduled clinical check-up appointment today at {formatted_time} with Dr. {doctor_id}.\n"
            f"Reason: {reason}\n"
            f"Reference Code: {appointment_id}\n\n"
            "Please remember to bring all your current medications."
        )

    return {
        "channel": "EMAIL",
        "recipient": recipient_email,
        "status": "DELIVERED",
        "subject": subject,
        "body_snippet": body[:120] + "..."
    }


def dispatch_sms_notification(
    recipient_phone: str,
    patient_id: str,
    doctor_id: str,
    formatted_time: str
) -> Dict[str, Any]:
    """Simulate SMS/WhatsApp message dispatch."""
    message = (
        f"AntiBioTix Reminder: Patient {patient_id} has a scheduled check-up today at {formatted_time} "
        f"with Dr. {doctor_id}. Ref: AntiBioTix CDSS."
    )
    return {
        "channel": "SMS",
        "recipient": recipient_phone or "+91-9876543210",
        "status": "DELIVERED",
        "message": message
    }


def dispatch_in_app_notification(
    patient_id: str,
    doctor_id: str,
    appointment_id: str,
    reason: str,
    formatted_time: str
) -> Dict[str, Any]:
    """Add notification to in-app notification queue."""
    notif = {
        "id": f"NOTIF-{appointment_id}",
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "title": "Scheduled Check-up Today",
        "message": f"Check-up for Patient {patient_id} is scheduled today at {formatted_time}.",
        "reason": reason,
        "formatted_time": formatted_time,
        "timestamp": now_ist().isoformat(),
        "read": False
    }
    IN_APP_NOTIFICATIONS_STORE.insert(0, notif)
    return {
        "channel": "IN_APP",
        "status": "DELIVERED",
        "notification_id": notif["id"]
    }


def scan_and_trigger_same_day_notifications(db: Session, force_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Scans the appointment schedule for check-ups occurring on the current date (IST),
    triggers multi-channel alerts (Email, SMS, In-App), updates delivery status,
    and writes an append-only audit event.
    """
    start_bound, end_bound = get_ist_bounds_for_date(force_date)
    
    # Query matching appointments for today in IST
    appointments = (
        db.query(AppointmentDB)
        .filter(
            AppointmentDB.appointment_date >= start_bound,
            AppointmentDB.appointment_date <= end_bound,
            AppointmentDB.status == "SCHEDULED"
        )
        .all()
    )

    scanned_count = len(appointments)
    dispatched_records = []

    for appt in appointments:
        # Check if same-day alert was already sent today
        if appt.same_day_alert_sent and not force_date:
            continue

        patient = db.query(PatientDB).filter(PatientDB.patient_id == appt.patient_id).first()
        p_name = patient.display_name if patient else appt.patient_id
        time_info = format_ist_datetime(appt.appointment_date)

        # 1. Email Dispatch
        doc_email_res = dispatch_email_notification(
            recipient_email=appt.doctor_email or "doctor@hospital.org",
            recipient_type="DOCTOR",
            patient_id=p_name,
            doctor_id=appt.doctor_id,
            appointment_id=appt.appointment_id,
            reason=appt.reason,
            formatted_time=time_info["formatted"]
        )

        pat_email_res = dispatch_email_notification(
            recipient_email=appt.patient_email or "patient@de-identified.org",
            recipient_type="PATIENT",
            patient_id=p_name,
            doctor_id=appt.doctor_id,
            appointment_id=appt.appointment_id,
            reason=appt.reason,
            formatted_time=time_info["formatted"]
        )

        # 2. SMS Dispatch
        sms_res = dispatch_sms_notification(
            recipient_phone=appt.patient_phone or "+91-9876543210",
            patient_id=appt.patient_id,
            doctor_id=appt.doctor_id,
            formatted_time=time_info["formatted"]
        )

        # 3. In-App Dispatch
        in_app_res = dispatch_in_app_notification(
            patient_id=appt.patient_id,
            doctor_id=appt.doctor_id,
            appointment_id=appt.appointment_id,
            reason=appt.reason,
            formatted_time=time_info["formatted"]
        )

        delivery_summary = {
            "doctor_email": doc_email_res["status"],
            "patient_email": pat_email_res["status"],
            "patient_sms": sms_res["status"],
            "in_app": in_app_res["status"],
            "dispatched_at_ist": now_ist().isoformat()
        }

        # Update appointment record flags
        appt.same_day_alert_sent = True
        appt.same_day_alert_timestamp = now_ist()
        appt.delivery_status_json = json.dumps(delivery_summary)
        db.commit()

        # Log immutable SHA-256 audit entry
        audit_logger.log_event(
            db=db,
            event_type="SAME_DAY_NOTIFICATION_SENT",
            prescription_id="-",
            patient_id=appt.patient_id,
            clinician_id=appt.doctor_id,
            clinician_role="ATTENDING_PHYSICIAN",
            action_summary=f"Same-day check-up notification triggered for appointment {appt.appointment_id} ({time_info['formatted']}).",
            payload={
                "appointment_id": appt.appointment_id,
                "appointment_date_ist": time_info["iso"],
                "reason": appt.reason,
                "delivery_summary": delivery_summary
            }
        )

        dispatched_records.append({
            "appointment_id": appt.appointment_id,
            "patient_id": appt.patient_id,
            "doctor_id": appt.doctor_id,
            "reason": appt.reason,
            "formatted_time": time_info["formatted"],
            "delivery_status": delivery_summary
        })

    return {
        "status": "SUCCESS",
        "scan_date_ist": start_bound.strftime("%d %B %Y"),
        "scanned_appointments_count": scanned_count,
        "newly_dispatched_count": len(dispatched_records),
        "dispatched_records": dispatched_records
    }
