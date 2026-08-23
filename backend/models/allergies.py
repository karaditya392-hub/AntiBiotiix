"""
Allergy record normalisation.

Allergies were originally stored as a plain list of strings:

    ["Penicillin", "Amoxicillin"]

Patient self-reporting requires provenance, so records are now stored as:

    [{"substance": "Penicillin", "source": "SELF_REPORTED", "reaction": "rash",
      "reported_by": "PATIENT-011", "reported_at": "..."}]

Both shapes must keep working: seeded demo patients use the legacy form, and a
migration that rewrote them would change clinical data to suit a storage
convention. Legacy entries are therefore read as CLINICIAN_VERIFIED, which is
what they were - records entered by staff, not self-reported.
"""
from __future__ import annotations

import datetime
import json
from typing import Any, Dict, Iterable, List

SELF_REPORTED = "SELF_REPORTED"
CLINICIAN_VERIFIED = "CLINICIAN_VERIFIED"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def normalise(raw: Any) -> List[Dict[str, Any]]:
    """Return a list of allergy records regardless of which shape was stored."""
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, list):
        return []

    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            if not item.strip():
                continue
            # Pre-existing entries were staff-entered, not patient-reported.
            out.append({
                "substance": item.strip(),
                "source": CLINICIAN_VERIFIED,
                "reaction": None,
                "reported_by": None,
                "reported_at": None,
                "verified_by": None,
                "verified_at": None,
            })
        elif isinstance(item, dict) and item.get("substance"):
            out.append({
                "substance": str(item["substance"]).strip(),
                "source": item.get("source") or SELF_REPORTED,
                "reaction": item.get("reaction"),
                "reported_by": item.get("reported_by"),
                "reported_at": item.get("reported_at"),
                "verified_by": item.get("verified_by"),
                "verified_at": item.get("verified_at"),
            })
    return out


def substances(raw: Any) -> List[str]:
    """
    Substance names only - the shape the rule engine consumes.

    Every recorded allergy is returned, including unverified self-reports.
    Withholding a self-reported allergy from the safety check to avoid a
    'soft' warning would be the wrong trade: the rule fires, and the warning
    says the report is unverified.
    """
    return [r["substance"] for r in normalise(raw) if r.get("substance")]


def find(raw: Any, substance: str) -> Dict[str, Any] | None:
    """Locate the record for a substance, matched case-insensitively."""
    target = (substance or "").strip().lower()
    for r in normalise(raw):
        if r["substance"].strip().lower() == target:
            return r
    return None


def add_report(raw: Any, substance: str, *, source: str, reported_by: str,
               reaction: str | None = None) -> tuple[List[Dict[str, Any]], bool]:
    """
    Add an allergy record. Returns (records, added).

    A duplicate substance is not appended twice; if a clinician records one the
    patient already self-reported, the existing record is upgraded to verified
    rather than duplicated.
    """
    records = normalise(raw)
    target = substance.strip().lower()
    for r in records:
        if r["substance"].strip().lower() == target:
            if source == CLINICIAN_VERIFIED and r["source"] != CLINICIAN_VERIFIED:
                r["source"] = CLINICIAN_VERIFIED
                r["verified_by"] = reported_by
                r["verified_at"] = _now()
                return records, True
            return records, False

    entry = {
        "substance": substance.strip(),
        "source": source,
        "reaction": reaction,
        "reported_by": reported_by,
        "reported_at": _now(),
        "verified_by": reported_by if source == CLINICIAN_VERIFIED else None,
        "verified_at": _now() if source == CLINICIAN_VERIFIED else None,
    }
    records.append(entry)
    return records, True


def verify(raw: Any, substance: str, clinician_id: str) -> tuple[List[Dict[str, Any]], bool]:
    """Mark a self-reported allergy as clinician-verified."""
    records = normalise(raw)
    target = (substance or "").strip().lower()
    for r in records:
        if r["substance"].strip().lower() == target:
            if r["source"] == CLINICIAN_VERIFIED:
                return records, False
            r["source"] = CLINICIAN_VERIFIED
            r["verified_by"] = clinician_id
            r["verified_at"] = _now()
            return records, True
    return records, False


def dumps(records: Iterable[Dict[str, Any]]) -> str:
    return json.dumps(list(records))


def unverified_count(raw: Any) -> int:
    return sum(1 for r in normalise(raw) if r.get("source") != CLINICIAN_VERIFIED)
