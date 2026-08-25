"""
Immutable Audit Logger & Alert-Fatigue Monitoring System (Sections 16A, 19)
Implements SHA-256 hash-chained immutable logging and per-rule override rate analytics.
"""
import uuid
import json
import hashlib
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.models.database import AuditLogDB, AlertMetricsDB, ClinicianOverrideDB, SafetyWarningDB, IST, now_ist
from backend.config import (
    SYSTEM_VERSION, PROMPT_TEMPLATE_ID,
    ALERT_FATIGUE_OVERRIDE_RATE_THRESHOLD, ALERT_FATIGUE_MIN_TRIGGERS
)

_audit_chain_lock = threading.Lock()


class ClinicalAuditLogger:
    def log_event(
        self,
        db: Session,
        event_type: str,
        prescription_id: str,
        patient_id: str,
        clinician_id: str,
        clinician_role: str,
        action_summary: str,
        payload: Dict[str, Any],
        model_version: str = SYSTEM_VERSION,
        prompt_template_id: str = PROMPT_TEMPLATE_ID
    ) -> AuditLogDB:
        """
        Record a cryptographically verifiable, append-only audit entry.
        Guarantees unbranched hash chain under concurrency via transaction-level / thread locking.
        """
        with _audit_chain_lock:
            try:
                db.rollback()
            except Exception:
                pass
            log_id = f"LOG-{uuid.uuid4().hex[:12].upper()}"
            timestamp = now_ist()
            ts_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")
            payload_str = json.dumps(payload, sort_keys=True, default=str)
            
            # Read the latest record inside the locked transaction
            query = db.query(AuditLogDB).order_by(AuditLogDB.id.desc())
            if db.bind and db.bind.dialect.name == "postgresql":
                try:
                    last_entry = query.with_for_update().first()
                except Exception:
                    last_entry = query.first()
            else:
                last_entry = query.first()

            prev_hash = last_entry.integrity_hash if last_entry else "GENESIS_BLOCK_0000000000000000"

            # Compute deterministic SHA-256 hash chain
            hash_input = f"{prev_hash}|{log_id}|{ts_str}|{event_type}|{prescription_id}|{clinician_id}|{payload_str}"
            current_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

            entry = AuditLogDB(
                log_id=log_id,
                timestamp=timestamp,
                event_type=event_type,
                prescription_id=prescription_id,
                patient_id=patient_id,
                clinician_id=clinician_id,
                clinician_role=clinician_role,
                action_summary=action_summary,
                payload_json=payload_str,
                prev_hash=prev_hash,
                integrity_hash=current_hash,
                model_version=model_version,
                prompt_template_id=prompt_template_id
            )
            
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry

    def record_warning_triggered(self, db: Session, rule_id: str):
        """Track warning generation in alert metrics."""
        metric = db.query(AlertMetricsDB).filter(AlertMetricsDB.rule_id == rule_id).first()
        if not metric:
            metric = AlertMetricsDB(
                rule_id=rule_id,
                total_triggered=1,
                total_overridden=0,
                total_accepted=0,
                last_triggered_at=now_ist()
            )
            db.add(metric)
        else:
            metric.total_triggered += 1
            metric.last_triggered_at = datetime.now(timezone.utc)
        db.commit()

    def record_override(
        self,
        db: Session,
        warning_id: str,
        prescription_id: str,
        clinician_id: str,
        clinician_role: str,
        override_reason: str
    ) -> ClinicianOverrideDB:
        """
        Record a clinician override in database, update warning status, and increment alert metrics.
        """
        override_id = f"OVR-{uuid.uuid4().hex[:8].upper()}"
        timestamp = now_ist()

        # 1. Update warning status
        warning = db.query(SafetyWarningDB).filter(SafetyWarningDB.warning_id == warning_id).first()
        if warning:
            warning.status = "OVERRIDDEN"

        # 2. Record override entry
        override = ClinicianOverrideDB(
            override_id=override_id,
            warning_id=warning_id,
            prescription_id=prescription_id,
            clinician_id=clinician_id,
            clinician_role=clinician_role,
            override_reason=override_reason,
            timestamp=timestamp
        )
        db.add(override)

        # 3. Update alert metrics
        if warning:
            metric = db.query(AlertMetricsDB).filter(AlertMetricsDB.rule_id == warning.rule_id).first()
            if metric:
                metric.total_overridden += 1
            else:
                metric = AlertMetricsDB(
                    rule_id=warning.rule_id,
                    total_triggered=1,
                    total_overridden=1,
                    total_accepted=0,
                    last_triggered_at=timestamp
                )
                db.add(metric)

        db.commit()
        db.refresh(override)

        # 4. Record in immutable audit log
        self.log_event(
            db=db,
            event_type="CLINICIAN_OVERRIDE",
            prescription_id=prescription_id,
            patient_id="PATIENT-UNKNOWN",
            clinician_id=clinician_id,
            clinician_role=clinician_role,
            action_summary=f"Clinician overridden warning {warning_id} (Rule: {warning.rule_id if warning else 'UNKNOWN'}) with justification: {override_reason[:100]}...",
            payload={
                "override_id": override_id,
                "warning_id": warning_id,
                "rule_id": warning.rule_id if warning else None,
                "override_reason": override_reason,
                "timestamp": timestamp.isoformat()
            }
        )

        return override

    def get_alert_fatigue_report(self, db: Session) -> List[Dict[str, Any]]:
        """
        Calculate per-rule override rates and flag rules exceeding the 60% alert fatigue threshold (Section 16A).
        """
        metrics = db.query(AlertMetricsDB).all()
        report = []
        for m in metrics:
            override_rate = (m.total_overridden / m.total_triggered) if m.total_triggered > 0 else 0.0
            recalibration_flag = (
                override_rate >= ALERT_FATIGUE_OVERRIDE_RATE_THRESHOLD 
                and m.total_triggered >= ALERT_FATIGUE_MIN_TRIGGERS
            )
            report.append({
                "rule_id": m.rule_id,
                "total_triggered": m.total_triggered,
                "total_overridden": m.total_overridden,
                "total_accepted": m.total_accepted,
                "override_rate_pct": round(override_rate * 100, 2),
                "alert_fatigue_threshold_pct": round(ALERT_FATIGUE_OVERRIDE_RATE_THRESHOLD * 100, 1),
                "requires_clinical_recalibration": recalibration_flag,
                "recommendation": "Review rule specificity and clinical relevance with stewardship committee" if recalibration_flag else "Rule performance within clinical calibration target (<60% override rate)",
                "last_triggered_at": m.last_triggered_at.isoformat() if m.last_triggered_at else None
            })
        return report

    def verify_chain_integrity(self, db: Session) -> Dict[str, Any]:
        """
        Walk and cryptographically verify the SHA-256 append-only hash chain from genesis to head.
        """
        entries = db.query(AuditLogDB).order_by(AuditLogDB.id.asc()).all()
        if not entries:
            return {
                "valid": True,
                "total_records": 0,
                "head_hash": "EMPTY_CHAIN",
                "message": "Audit log is empty."
            }

        expected_prev_hash = "GENESIS_BLOCK_0000000000000000"
        broken_records = []

        for idx, entry in enumerate(entries):
            # Check previous hash link
            if entry.prev_hash != expected_prev_hash:
                broken_records.append({
                    "log_id": entry.log_id,
                    "index": idx,
                    "reason": f"Mismatched prev_hash: expected {expected_prev_hash}, got {entry.prev_hash}"
                })

            # Recompute current hash
            ts_str = entry.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f") if isinstance(entry.timestamp, datetime) else str(entry.timestamp)
            hash_input = f"{entry.prev_hash}|{entry.log_id}|{ts_str}|{entry.event_type}|{entry.prescription_id}|{entry.clinician_id}|{entry.payload_json}"
            recomputed = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

            if entry.integrity_hash != recomputed:
                broken_records.append({
                    "log_id": entry.log_id,
                    "index": idx,
                    "reason": f"Corrupted integrity_hash: recomputed {recomputed}, recorded {entry.integrity_hash}"
                })

            expected_prev_hash = entry.integrity_hash

        is_valid = len(broken_records) == 0
        return {
            "valid": is_valid,
            "total_records": len(entries),
            "head_hash": entries[-1].integrity_hash,
            "broken_records": broken_records,
            "verification_status": "CRYPTOGRAPHICALLY_VERIFIED" if is_valid else "CORRUPTION_DETECTED"
        }


# Singleton audit logger
audit_logger = ClinicalAuditLogger()
