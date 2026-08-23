"""
Patient registration, medication reconciliation and allergy self-reporting.
Spec §3 (data model), §3B, §18A (authorization), §24/§25 (privacy).

The central safety property under test: a patient-reported allergy still fires
the allergy rules, and the resulting warning states that it is unverified.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.models import allergies as allergy_store

client = TestClient(app)


@pytest.fixture
def doctor():
    tok = client.post("/api/auth/login",
                      json={"username": "dr_test", "role": "ATTENDING_PHYSICIAN"}).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


@pytest.fixture
def new_patient(doctor):
    r = client.post("/api/patients", headers=doctor,
                    json={"age": 55, "age_category": "ADULT", "sex": "FEMALE"}).json()
    return r


# --- registration -----------------------------------------------------------

def test_doctor_can_register_patient(doctor):
    r = client.post("/api/patients", headers=doctor, json={"age": 44, "sex": "MALE"})
    assert r.status_code == 201
    body = r.json()
    assert body["patient_id"].startswith("PATIENT-")
    assert body["status"] == "CREATED"


def test_registration_defaults_to_unknown_not_normal(doctor):
    """
    A new record with nothing filled in must not read as a healthy patient.
    Allergy, renal and hepatic status all start unknown.
    """
    body = client.post("/api/patients", headers=doctor, json={"age": 30}).json()
    assert set(body["unknowns"]) == {"allergy history", "renal function", "hepatic function"}

    pid = body["patient_id"]
    rx = client.post("/api/prescriptions", json={
        "patient_id": pid, "diagnosis": "cellulitis",
        "items": [{"medication_name": "Ciprofloxacin", "dose": 500, "unit": "mg",
                   "route": "PO", "frequency": "BID", "duration_days": 7}]}).json()["prescription_id"]
    rules = [w["rule_id"] for w in client.post(f"/api/prescriptions/{rx}/analyze", json={}).json()["warnings"]]
    assert "ALLERGY-004" in rules, "missing allergy history must be flagged"
    assert "RENAL-003" in rules, "missing renal information must be flagged"


def test_registration_accepts_no_direct_identifiers(doctor):
    """Spec 24/25: the API must have nowhere to put a real identifier."""
    r = client.post("/api/patients", headers=doctor,
                    json={"age": 40, "name": "Real Person", "phone": "9876543210",
                          "address": "12 Main St", "aadhaar": "1234"})
    assert r.status_code == 201
    stored = client.get(f"/api/patients/{r.json()['patient_id']}").json()
    for leaked in ("name", "phone", "address", "aadhaar"):
        assert leaked not in stored


def test_server_issues_patient_id(doctor):
    """A client cannot choose the identifier."""
    r = client.post("/api/patients", headers=doctor,
                    json={"age": 40, "patient_id": "CHOSEN-BY-CLIENT"})
    assert r.json()["patient_id"] != "CHOSEN-BY-CLIENT"


# --- medication reconciliation ---------------------------------------------

def test_doctor_updates_medications(doctor, new_patient):
    pid = new_patient["patient_id"]
    r = client.put(f"/api/patients/{pid}/medications", headers=doctor,
                   json={"active_medications": ["Warfarin 5mg PO QD", "Metoprolol 50mg PO BID"],
                         "reason": "admission reconciliation"})
    assert r.status_code == 200
    assert r.json()["current_count"] == 2
    assert client.get(f"/api/patients/{pid}").json()["active_medications"] == \
        ["Warfarin 5mg PO QD", "Metoprolol 50mg PO BID"]


def test_updated_medications_reach_interaction_checks(doctor, new_patient):
    """A medication added after registration must be seen by the DDI rules."""
    pid = new_patient["patient_id"]
    client.put(f"/api/patients/{pid}/medications", headers=doctor,
               json={"active_medications": ["Warfarin 5mg PO QD"]})
    rx = client.post("/api/prescriptions", json={
        "patient_id": pid, "diagnosis": "cellulitis",
        "items": [{"medication_name": "Ciprofloxacin", "dose": 500, "unit": "mg",
                   "route": "PO", "frequency": "BID", "duration_days": 7}]}).json()["prescription_id"]
    rules = [w["rule_id"] for w in client.post(f"/api/prescriptions/{rx}/analyze", json={}).json()["warnings"]]
    assert "DDI-001" in rules, "warfarin interaction must fire from the updated list"


# --- patient self-reported allergies ---------------------------------------

def test_patient_reports_own_allergy(new_patient):
    pid = new_patient["patient_id"]
    h = {"Authorization": f"Bearer {new_patient['patient_access_token']}"}
    r = client.post(f"/api/patients/{pid}/allergies", headers=h,
                    json={"substance": "Penicillin", "reaction": "rash"})
    assert r.status_code == 201
    assert r.json()["source"] == allergy_store.SELF_REPORTED


def test_self_reported_allergy_still_fires_the_rule(new_patient):
    """
    The safety-critical property. An unverified report must NOT be silently
    ignored -- it fires the rule, and the warning says it is unverified.
    """
    pid = new_patient["patient_id"]
    h = {"Authorization": f"Bearer {new_patient['patient_access_token']}"}
    client.post(f"/api/patients/{pid}/allergies", headers=h, json={"substance": "Penicillin"})

    rx = client.post("/api/prescriptions", json={
        "patient_id": pid, "diagnosis": "Community-Acquired Pneumonia",
        "items": [{"medication_name": "Amoxicillin", "dose": 500, "unit": "mg",
                   "route": "PO", "frequency": "TID", "duration_days": 7}]}).json()["prescription_id"]
    warns = client.post(f"/api/prescriptions/{rx}/analyze", json={}).json()["warnings"]
    allergy = [w for w in warns if w["category"] == "ALLERGY"]
    assert allergy, "a self-reported allergy must still trigger the allergy rules"
    w = allergy[0]
    assert "unverified" in w["interacting_factor"].lower()
    assert "PATIENT-REPORTED" in w["evidence"]["verbatim_passage"]


def test_clinician_entered_allergy_carries_no_unverified_caveat(doctor, new_patient):
    pid = new_patient["patient_id"]
    client.post(f"/api/patients/{pid}/allergies", headers=doctor, json={"substance": "Penicillin"})
    rx = client.post("/api/prescriptions", json={
        "patient_id": pid, "diagnosis": "CAP",
        "items": [{"medication_name": "Amoxicillin", "dose": 500, "unit": "mg",
                   "route": "PO", "frequency": "TID", "duration_days": 7}]}).json()["prescription_id"]
    warns = client.post(f"/api/prescriptions/{rx}/analyze", json={}).json()["warnings"]
    allergy = [w for w in warns if w["category"] == "ALLERGY"]
    assert allergy
    assert "unverified" not in allergy[0]["interacting_factor"].lower()


def test_clinician_can_verify_a_self_report(doctor, new_patient):
    pid = new_patient["patient_id"]
    h = {"Authorization": f"Bearer {new_patient['patient_access_token']}"}
    client.post(f"/api/patients/{pid}/allergies", headers=h, json={"substance": "Sulfa"})
    r = client.post(f"/api/patients/{pid}/allergies/verify", headers=doctor,
                    json={"substance": "Sulfa"})
    assert r.status_code == 200
    rec = [x for x in r.json()["allergy_records"] if x["substance"].lower() == "sulfa"][0]
    assert rec["source"] == allergy_store.CLINICIAN_VERIFIED
    assert rec["verified_by"]


def test_reporting_an_allergy_clears_the_missing_history_guard(new_patient):
    pid = new_patient["patient_id"]
    h = {"Authorization": f"Bearer {new_patient['patient_access_token']}"}
    client.post(f"/api/patients/{pid}/allergies", headers=h, json={"substance": "Penicillin"})
    assert client.get(f"/api/patients/{pid}").json()["allergy_status_known"] is True


# --- authorization boundaries (Spec 18A) ------------------------------------

def test_patient_cannot_touch_another_patients_record(doctor, new_patient):
    other = client.post("/api/patients", headers=doctor, json={"age": 61}).json()
    h = {"Authorization": f"Bearer {new_patient['patient_access_token']}"}
    r = client.post(f"/api/patients/{other['patient_id']}/allergies", headers=h,
                    json={"substance": "Sulfa"})
    assert r.status_code == 403


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/patients", {"age": 30}),
    ("put", "/api/patients/{pid}/medications", {"active_medications": ["X"]}),
    ("post", "/api/patients/{pid}/allergies/verify", {"substance": "Penicillin"}),
])
def test_patient_cannot_perform_clinician_actions(new_patient, method, path, body):
    pid = new_patient["patient_id"]
    h = {"Authorization": f"Bearer {new_patient['patient_access_token']}"}
    r = getattr(client, method)(path.format(pid=pid), headers=h, json=body)
    assert r.status_code == 403


@pytest.mark.parametrize("method,path", [
    ("post", "/api/patients"),
    ("put", "/api/patients/PATIENT-001/medications"),
    ("post", "/api/patients/PATIENT-001/allergies"),
])
def test_unauthenticated_requests_rejected(method, path):
    r = getattr(client, method)(path, json={"age": 30, "active_medications": [], "substance": "X"})
    assert r.status_code == 401


# --- legacy compatibility ---------------------------------------------------

def test_seeded_patients_read_as_clinician_verified():
    """
    Existing records store plain strings. They were entered by staff, so they
    must not be downgraded to 'patient-reported' by the new model.
    """
    p = client.get("/api/patients/PATIENT-001").json()
    assert p["allergies"], "PATIENT-001 has documented allergies"
    assert all(r["source"] == allergy_store.CLINICIAN_VERIFIED for r in p["allergy_records"])
    assert p["unverified_allergy_count"] == 0
