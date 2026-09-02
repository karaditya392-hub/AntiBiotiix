"""
Patient follow-up loop: patient answers by visit code, clinician sees the answers.

THE PROPERTY THAT MATTERS HERE IS ACCESS. The submit and lookup endpoints are
public, because a patient has no login in this system. That makes the code the
only thing standing between a stranger and someone's prescription, so most of
these tests are about what the code does NOT open.

The obvious design -- "type your name and we'll show your prescription" -- is the
one this deliberately does not implement.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app import app, _new_feedback_code
from backend.models.database import (
    FeedbackAcknowledgementDB, FeedbackResponseDB, NotificationDB,
    SessionLocal, VisitDB,
)

client = TestClient(app)


@pytest.fixture()
def coded_visit():
    db = SessionLocal()
    visit = db.query(VisitDB).filter(VisitDB.prescription_id.isnot(None)).first()
    assert visit, "expected a seeded visit with a prescription"
    if not visit.feedback_code:
        visit.feedback_code = _new_feedback_code(db)
        db.commit()
    data = {"code": visit.feedback_code, "visit_id": visit.visit_id,
            "patient_id": visit.patient_id}
    db.close()
    return data


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", [" ", "AB", "ZZZZZZZZ", "../../etc/passwd", "null"])
def test_a_code_that_opens_nothing_returns_the_same_refusal(code):
    """
    Distinguishing "no such code" from "wrong code" tells a guesser which is which,
    so both answer identically. A blank code must never match the visits recorded
    before this feature existed, whose feedback_code is NULL.
    """
    assert client.get(f"/api/feedback/{code}").status_code == 404


def test_an_empty_code_falls_through_to_the_authenticated_list_not_a_visit():
    """
    An empty path segment resolves to /api/feedback, which is the clinician-only
    listing rather than a lookup. It answers 401 instead of 404 -- a different
    refusal, but still a refusal, and it returns no visit.
    """
    for path in ("/api/feedback/", "/api/feedback"):
        res = client.get(path)
        assert res.status_code == 401
        assert "visit_id" not in res.text


def test_a_valid_code_opens_exactly_one_visit(coded_visit):
    body = client.get(f"/api/feedback/{coded_visit['code']}").json()
    assert body["visit_id"] == coded_visit["visit_id"]


def test_the_code_is_case_insensitive(coded_visit):
    """It is read off a printed slip or spoken aloud."""
    assert client.get(f"/api/feedback/{coded_visit['code'].lower()}").status_code == 200


def test_the_public_page_is_given_the_minimum_not_the_record(coded_visit):
    """
    A patient confirming how treatment is going needs their medications and their
    diagnosis. They do not need, and a public endpoint must not hand back, the rest
    of the clinical record.
    """
    body = client.get(f"/api/feedback/{coded_visit['code']}").json()
    assert body["medications"] is not None
    for leaked in ("allergies", "egfr_ml_min", "clinical_notes", "child_pugh_class",
                   "active_medications", "medical_history", "visits"):
        assert leaked not in body, f"public feedback context leaked {leaked}"


def test_reading_other_peoples_answers_requires_a_clinician(coded_visit):
    """Submitting is public. Reading the list is not."""
    assert client.get("/api/feedback").status_code == 401


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def test_an_answer_reaches_the_clinician_as_a_notification(coded_visit):
    db = SessionLocal()
    before = db.query(NotificationDB).filter(NotificationDB.kind == "PATIENT_FEEDBACK").count()
    db.close()

    res = client.post(f"/api/feedback/{coded_visit['code']}", json={
        "feeling": "WORSE", "medicines_helped": "NO",
        "discomfort": "Rash on both arms since yesterday",
    })
    assert res.status_code == 200
    assert res.json()["recorded"] is True

    db = SessionLocal()
    after = db.query(NotificationDB).filter(NotificationDB.kind == "PATIENT_FEEDBACK").count()
    latest = (db.query(NotificationDB)
              .filter(NotificationDB.kind == "PATIENT_FEEDBACK")
              .order_by(NotificationDB.id.desc()).first())
    stored = (db.query(FeedbackResponseDB)
              .order_by(FeedbackResponseDB.id.desc()).first())
    db.close()

    assert after == before + 1
    assert latest.recipient_type == "DOCTOR" and latest.channel == "IN_APP"
    assert "WORSE" in (latest.title or "").upper()
    # The patient's own words, stored unedited.
    assert stored.discomfort == "Rash on both arms since yesterday"


@pytest.mark.parametrize("payload", [
    {"feeling": "GREAT", "medicines_helped": "YES"},
    {"feeling": "BETTER", "medicines_helped": "MAYBE"},
    {"medicines_helped": "YES"},
    {"feeling": "BETTER"},
])
def test_an_unanswered_or_invalid_question_is_rejected(coded_visit, payload):
    assert client.post(f"/api/feedback/{coded_visit['code']}", json=payload).status_code == 400


def test_discomfort_is_optional(coded_visit):
    res = client.post(f"/api/feedback/{coded_visit['code']}", json={
        "feeling": "BETTER", "medicines_helped": "YES",
    })
    assert res.status_code == 200


def test_submitting_against_an_unknown_code_records_nothing(coded_visit):
    db = SessionLocal()
    before = db.query(FeedbackResponseDB).count()
    db.close()
    assert client.post("/api/feedback/ZZZZZZZZ", json={
        "feeling": "BETTER", "medicines_helped": "YES"}).status_code == 404
    db = SessionLocal()
    assert db.query(FeedbackResponseDB).count() == before
    db.close()


# ---------------------------------------------------------------------------
# Codes
# ---------------------------------------------------------------------------

def test_codes_avoid_glyphs_that_are_misread_aloud():
    """The code is spoken or handwritten, so O/0, I/1 and S/5 are excluded."""
    db = SessionLocal()
    codes = [_new_feedback_code(db) for _ in range(40)]
    db.close()
    for code in codes:
        assert len(code) == 8
        assert not (set(code) & set("O0I1S5")), code


def test_codes_are_unique():
    db = SessionLocal()
    codes = [_new_feedback_code(db) for _ in range(200)]
    db.close()
    assert len(set(codes)) == len(codes)


# ---------------------------------------------------------------------------
# Code stability
# ---------------------------------------------------------------------------

def test_seeded_codes_survive_a_reseed():
    """
    seed_database(reset_patients=True) deletes every visit and rebuilds it, and
    conftest calls it that way on every test run. With randomly generated codes,
    VIS-001's code changed each time the suite ran, so a code written on a patient's
    visit summary stopped working as soon as anyone ran the tests.

    An access code that rotates behind the holder's back is not an access code.
    """
    from backend.seed_data import _seed_feedback_code

    first = {vid: _seed_feedback_code(vid) for vid in ("VIS-001", "VIS-002", "VIS-020")}
    second = {vid: _seed_feedback_code(vid) for vid in first}
    assert first == second

    db = SessionLocal()
    live = db.query(VisitDB).filter(VisitDB.visit_id == "VIS-001").first()
    db.close()
    if live and live.feedback_code:
        assert live.feedback_code == first["VIS-001"], (
            "the stored code for VIS-001 does not match its derived code; a reseed "
            "would change it"
        )


def test_seeded_codes_are_distinct_across_visits():
    from backend.seed_data import _seed_feedback_code

    codes = {_seed_feedback_code(f"VIS-{i:03d}") for i in range(1, 61)}
    assert len(codes) == 60


def test_seeded_codes_use_the_unambiguous_alphabet():
    from backend.seed_data import _seed_feedback_code

    for i in range(1, 21):
        code = _seed_feedback_code(f"VIS-{i:03d}")
        assert len(code) == 8
        assert not (set(code) & set("O0I1S5")), code


# ---------------------------------------------------------------------------
# The alert queue the clinician sees after logging in
# ---------------------------------------------------------------------------

def _clinician_headers(username="CLINICIAN-DEMO", role="ATTENDING_PHYSICIAN"):
    res = client.post("/api/auth/login", json={"username": username, "role": role})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_unseen_is_matched_as_a_route_not_as_a_visit_code():
    """
    /api/feedback/unseen sits next to /api/feedback/{code}. FastAPI matches in
    declaration order, so with the parameterised route first "unseen" is read as a
    visit code and answers 404. 401 here proves the ordering is right: it reached
    the clinician-only handler.
    """
    assert client.get("/api/feedback/unseen").status_code == 401


def test_a_new_answer_appears_in_the_unseen_queue(coded_visit):
    headers = _clinician_headers()
    res = client.post(f"/api/feedback/{coded_visit['code']}", json={
        "feeling": "WORSE", "medicines_helped": "NO", "discomfort": "Dizzy since Tuesday"})
    response_id = res.json()["response_id"]

    body = client.get("/api/feedback/unseen", headers=headers).json()
    ids = [r["response_id"] for r in body["responses"]]
    assert response_id in ids

    # The alert is shown by NAME, which is the whole point of announcing it.
    entry = next(r for r in body["responses"] if r["response_id"] == response_id)
    assert entry["patient_name"] and not entry["patient_name"].startswith("PATIENT-")
    # And it carries the patient id the alert navigates to.
    assert entry["patient_id"] == coded_visit["patient_id"]


def test_acknowledging_an_answer_removes_it_from_the_queue(coded_visit):
    headers = _clinician_headers()
    res = client.post(f"/api/feedback/{coded_visit['code']}", json={
        "feeling": "BETTER", "medicines_helped": "YES"})
    response_id = res.json()["response_id"]

    assert client.post(f"/api/feedback/{response_id}/seen", headers=headers).status_code == 200
    remaining = [r["response_id"] for r in
                 client.get("/api/feedback/unseen", headers=headers).json()["responses"]]
    assert response_id not in remaining


def test_an_acknowledged_answer_is_still_in_the_record(coded_visit):
    """
    Marking an alert seen stops it announcing itself. It must not remove the answer:
    the patient still said it, and the clinician still needs it on the record.
    """
    headers = _clinician_headers()
    res = client.post(f"/api/feedback/{coded_visit['code']}", json={
        "feeling": "SAME", "medicines_helped": "UNSURE", "discomfort": "Mild nausea"})
    response_id = res.json()["response_id"]
    client.post(f"/api/feedback/{response_id}/seen", headers=headers)

    listed = client.get(f"/api/feedback?patient_id={coded_visit['patient_id']}",
                        headers=headers).json()["responses"]
    match = [r for r in listed if r["response_id"] == response_id]
    assert match and match[0]["discomfort"] == "Mild nausea"


def test_acknowledging_something_that_does_not_exist_is_refused():
    assert client.post("/api/feedback/FB-NOPE/seen",
                       headers=_clinician_headers()).status_code == 404


def test_the_unseen_queue_is_clinician_only():
    """A patient must not be able to read the queue of everyone else's answers."""
    assert client.get("/api/feedback/unseen").status_code == 401
    assert client.post("/api/feedback/FB-ANY/seen").status_code == 401


# ---------------------------------------------------------------------------
# Acknowledgement is per clinician
#
# This system has five clinician accounts. Acknowledgement was originally a single
# boolean on the answer, which meant whichever clinician logged in first could
# clear an alert for all of them -- a pharmacist dismissing a popup would hide it
# from the attending physician who owned the patient. That is precisely the failure
# a follow-up alert exists to prevent.
# ---------------------------------------------------------------------------

def _unseen_ids(headers):
    return [r["response_id"] for r in
            client.get("/api/feedback/unseen", headers=headers).json()["responses"]]


def test_one_clinician_dismissing_does_not_hide_it_from_another(coded_visit):
    attending = _clinician_headers("DOC-ATTENDING-01", "ATTENDING_PHYSICIAN")
    pharmacist = _clinician_headers("DOC-PHARM-01", "CLINICAL_PHARMACIST")

    response_id = client.post(f"/api/feedback/{coded_visit['code']}", json={
        "feeling": "WORSE", "medicines_helped": "NO"}).json()["response_id"]

    assert response_id in _unseen_ids(attending)
    assert response_id in _unseen_ids(pharmacist)

    client.post(f"/api/feedback/{response_id}/seen", headers=pharmacist)

    assert response_id not in _unseen_ids(pharmacist), "the dismisser should stop seeing it"
    assert response_id in _unseen_ids(attending), (
        "the attending physician must still be told: another clinician clearing "
        "their own alert says nothing about whether this one has read it"
    )


def test_each_clinician_clears_their_own_alert(coded_visit):
    attending = _clinician_headers("DOC-ATTENDING-01", "ATTENDING_PHYSICIAN")
    pharmacist = _clinician_headers("DOC-PHARM-01", "CLINICAL_PHARMACIST")
    response_id = client.post(f"/api/feedback/{coded_visit['code']}", json={
        "feeling": "SAME", "medicines_helped": "UNSURE"}).json()["response_id"]

    for headers in (pharmacist, attending):
        client.post(f"/api/feedback/{response_id}/seen", headers=headers)
    assert response_id not in _unseen_ids(attending)
    assert response_id not in _unseen_ids(pharmacist)


def test_dismissing_twice_records_one_acknowledgement(coded_visit):
    """A double click or a retried request must not write duplicate rows."""
    headers = _clinician_headers("DOC-ID-LEAD-01", "INFECTIOUS_DISEASE_SPECIALIST")
    response_id = client.post(f"/api/feedback/{coded_visit['code']}", json={
        "feeling": "BETTER", "medicines_helped": "YES"}).json()["response_id"]

    for _ in range(3):
        assert client.post(f"/api/feedback/{response_id}/seen", headers=headers).status_code == 200

    db = SessionLocal()
    count = db.query(FeedbackAcknowledgementDB).filter(
        FeedbackAcknowledgementDB.response_id == response_id).count()
    db.close()
    assert count == 1


def test_acknowledgement_does_not_alter_the_answer(coded_visit):
    headers = _clinician_headers()
    response_id = client.post(f"/api/feedback/{coded_visit['code']}", json={
        "feeling": "WORSE", "medicines_helped": "NO",
        "discomfort": "Swelling around the ankles"}).json()["response_id"]
    client.post(f"/api/feedback/{response_id}/seen", headers=headers)

    db = SessionLocal()
    row = db.query(FeedbackResponseDB).filter(
        FeedbackResponseDB.response_id == response_id).first()
    db.close()
    assert row.feeling == "WORSE"
    assert row.discomfort == "Swelling around the ankles"


# ---------------------------------------------------------------------------
# The 24-hour notification hold, and the fourth question
# ---------------------------------------------------------------------------

import uuid as _uuid
from datetime import datetime, timedelta, timezone

from backend.app import FEEDBACK_NOTIFICATION_DELAY_HOURS
from backend.models.database import SessionLocal, VisitDB


def _visit_aged(hours: float, code: str) -> str:
    """A completed visit that happened `hours` ago, with a known follow-up code."""
    visit_id = f"VIS-T-{_uuid.uuid4().hex[:8].upper()}"
    db = SessionLocal()
    db.add(VisitDB(visit_id=visit_id, patient_id="PATIENT-001", doctor_id="DOC-DEMO-01",
                   visit_date=datetime.now(timezone.utc) - timedelta(hours=hours),
                   diagnosis="Hold test", status="COMPLETED", feedback_code=code))
    db.commit()
    db.close()
    return visit_id


def _age_visit(visit_id: str, hours: float) -> None:
    db = SessionLocal()
    visit = db.query(VisitDB).filter(VisitDB.visit_id == visit_id).first()
    visit.visit_date = datetime.now(timezone.utc) - timedelta(hours=hours)
    db.commit()
    db.close()


def _attending_headers():
    res = client.post("/api/auth/login",
                      json={"doctor_id": "DOC-DEMO-01", "password": "doctorpassword123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _notified(response_id: str, headers) -> bool:
    rows = client.get("/api/feedback/unseen", headers=headers).json()["responses"]
    return any(r["response_id"] == response_id for r in rows)


def test_an_answer_from_a_fresh_visit_is_stored_but_not_notified():
    """
    A patient who answers on the way out of the clinic is reporting the
    consultation, not the treatment. Paging a clinician minutes after they
    prescribed teaches them to dismiss the alert.
    """
    code = f"HOLD{_uuid.uuid4().hex[:4].upper()}"
    visit_id = _visit_aged(0.1, code)          # six minutes ago
    headers = _attending_headers()

    submitted = client.post(f"/api/feedback/{code}",
                            json={"feeling": "WORSE", "medicines_helped": "NO"})
    assert submitted.status_code == 200
    response_id = submitted.json()["response_id"]

    # stored immediately...
    listed = client.get(f"/api/patients/PATIENT-001/history")
    assert listed.status_code == 200
    # ...but not surfaced as an interruption
    assert _notified(response_id, headers) is False


def test_the_same_answer_is_notified_once_the_visit_matures():
    code = f"HOLD{_uuid.uuid4().hex[:4].upper()}"
    visit_id = _visit_aged(0.1, code)
    headers = _attending_headers()
    response_id = client.post(f"/api/feedback/{code}",
                              json={"feeling": "WORSE", "medicines_helped": "NO"}).json()["response_id"]

    assert _notified(response_id, headers) is False
    _age_visit(visit_id, FEEDBACK_NOTIFICATION_DELAY_HOURS + 1)
    assert _notified(response_id, headers) is True


def test_the_hold_is_reported_so_a_client_can_explain_the_quiet():
    body = client.get("/api/feedback/unseen", headers=_attending_headers()).json()
    assert body["notification_delay_hours"] == FEEDBACK_NOTIFICATION_DELAY_HOURS == 24


def test_adherence_is_recorded_when_answered():
    code = f"ADH{_uuid.uuid4().hex[:5].upper()}"
    _visit_aged(30, code)
    res = client.post(f"/api/feedback/{code}", json={
        "feeling": "WORSE", "medicines_helped": "NO", "doses_taken": "STOPPED",
        "discomfort": "Rash since Tuesday"})
    assert res.status_code == 200

    db = SessionLocal()
    from backend.models.database import FeedbackResponseDB
    row = db.query(FeedbackResponseDB).filter(
        FeedbackResponseDB.response_id == res.json()["response_id"]).first()
    assert row.doses_taken == "STOPPED"
    assert row.discomfort == "Rash since Tuesday"
    db.close()


def test_adherence_is_optional_and_a_bad_value_is_dropped_not_stored():
    """
    A patient unwilling to say they stopped must still be able to report that
    they feel worse, so the answer is never required - and an unrecognised value
    is discarded rather than written to the record as if it were an answer.
    """
    code = f"ADH{_uuid.uuid4().hex[:5].upper()}"
    _visit_aged(30, code)
    res = client.post(f"/api/feedback/{code}", json={
        "feeling": "BETTER", "medicines_helped": "YES", "doses_taken": "whatever"})
    assert res.status_code == 200

    from backend.models.database import FeedbackResponseDB
    db = SessionLocal()
    row = db.query(FeedbackResponseDB).filter(
        FeedbackResponseDB.response_id == res.json()["response_id"]).first()
    assert row.doses_taken is None
    db.close()
