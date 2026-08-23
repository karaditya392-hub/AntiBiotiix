"""
Clinical rule governance.

Every rule in the catalog ships as PENDING_CLINICAL_REVIEW, authored by
SYSTEM_GENERATED. Nothing had ever recorded a human reviewing one, which the
project's own audit report flags. This module closes that loop.

Design decision: the catalog JSON is NOT mutated.

The catalog is a source artefact with a version and a reconciliation note. Review
decisions are events about it, not edits to it, so they are appended to
rule_authorship_logs and the effective status is derived at read time. That keeps
the shipped catalog reproducible, makes the review history replayable, and means
an approval can never silently rewrite the rule text it approved.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.models.database import RuleAuthorshipLogDB

# Decisions a reviewer may record. RETIRED is included because withdrawing a rule
# is a governance act too, and must be as traceable as approving one.
REVIEW_ACTIONS = ("APPROVED", "REJECTED", "CHANGES_REQUESTED", "RETIRED")

# Only APPROVED changes a rule's effective status; the others record that review
# happened and what was decided, without claiming clinical sign-off.
_STATUS_FOR_ACTION = {
    "APPROVED": "APPROVED_FOR_CLINICAL_USE",
    "REJECTED": "REJECTED_IN_REVIEW",
    "CHANGES_REQUESTED": "CHANGES_REQUESTED",
    "RETIRED": "RETIRED",
}


def latest_reviews(db: Session, rule_ids: Optional[List[str]] = None) -> Dict[str, RuleAuthorshipLogDB]:
    """Most recent review event per rule id."""
    query = db.query(RuleAuthorshipLogDB).filter(
        RuleAuthorshipLogDB.action.in_(REVIEW_ACTIONS)
    )
    if rule_ids:
        query = query.filter(RuleAuthorshipLogDB.rule_id.in_(rule_ids))

    newest: Dict[str, RuleAuthorshipLogDB] = {}
    for row in query.order_by(RuleAuthorshipLogDB.id.asc()).all():
        newest[row.rule_id] = row  # ascending, so the last write wins
    return newest


def review_history(db: Session, rule_id: str) -> List[Dict[str, Any]]:
    rows = (
        db.query(RuleAuthorshipLogDB)
        .filter(RuleAuthorshipLogDB.rule_id == rule_id)
        .order_by(RuleAuthorshipLogDB.id.desc())
        .all()
    )
    return [
        {
            "action": r.action,
            "author_id": r.author_id,
            "author_role": r.author_role,
            "approved_by": r.approved_by,
            "change_summary": r.change_summary,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ]


def governance_report(db: Session, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Catalog rules with their effective review state layered on top.

    `catalog_status` is what the shipped file says; `effective_status` is what the
    review log has since decided. Both are returned, because a reviewer needs to
    see that a rule was approved in spite of shipping as pending.
    """
    reviews = latest_reviews(db, [r.get("rule_id") for r in rules if r.get("rule_id")])

    out: List[Dict[str, Any]] = []
    for rule in rules:
        rule_id = rule.get("rule_id")
        review = reviews.get(rule_id)
        catalog_status = rule.get("approval_status", "PENDING_CLINICAL_REVIEW")

        out.append({
            "rule_id": rule_id,
            "category": rule.get("category"),
            "severity": rule.get("severity"),
            "description": rule.get("description"),
            "catalog_author": rule.get("author"),
            "catalog_status": catalog_status,
            "effective_status": (
                _STATUS_FOR_ACTION.get(review.action, catalog_status) if review else catalog_status
            ),
            "reviewed": bool(review),
            "last_action": review.action if review else None,
            "reviewed_by": review.author_id if review else None,
            "reviewer_role": review.author_role if review else None,
            "review_rationale": review.change_summary if review else None,
            "reviewed_at": review.timestamp.isoformat() if review and review.timestamp else None,
        })

    reviewed = [r for r in out if r["reviewed"]]
    approved = [r for r in out if r["effective_status"] == "APPROVED_FOR_CLINICAL_USE"]

    return {
        "total_rules": len(out),
        "reviewed_count": len(reviewed),
        "approved_count": len(approved),
        "pending_count": len(out) - len(reviewed),
        "governance_note": (
            "Rules ship as PENDING_CLINICAL_REVIEW. Review decisions are recorded as "
            "append-only events against the catalog rather than edits to it, so the shipped "
            "catalog stays reproducible and an approval can never rewrite the rule text it "
            "approved. Approval records that a clinician accepted the rule; it does not "
            "change how the rule evaluates, and every rule fires identically either way."
        ),
        "rules": out,
    }


def record_review(
    db: Session,
    rule_id: str,
    action: str,
    rationale: str,
    reviewer_id: str,
    reviewer_role: str,
) -> RuleAuthorshipLogDB:
    """Append a review event. Callers must have already authorized the reviewer."""
    entry = RuleAuthorshipLogDB(
        rule_id=rule_id,
        action=action,
        author_id=reviewer_id,
        author_role=reviewer_role,
        approved_by=reviewer_id if action == "APPROVED" else None,
        change_summary=rationale,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
