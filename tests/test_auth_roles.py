"""
Server-Side Role Resolution & Authorization Test Suite (Spec §18, §18A)
Verifies that overrides and rule authoring enforce server-side token authorization
and ignore any client-asserted roles in request bodies.
"""
import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.models.database import init_db

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()


def test_missing_auth_token_rejected_with_401():
    # Attempt override without Authorization header
    override_payload = {
        "warning_id": "WARN-TEST-001",
        "override_reason": "Clinical override rationale without auth header."
    }
    res = client.post("/api/warnings/WARN-TEST-001/override", json=override_payload)
    assert res.status_code == 401, "Must return 401 when Authorization header is missing."


def test_invalid_auth_token_rejected_with_401():
    override_payload = {
        "warning_id": "WARN-TEST-001",
        "override_reason": "Clinical override rationale with forged token."
    }
    headers = {"Authorization": "Bearer forged_invalid_token_999"}
    res = client.post("/api/warnings/WARN-TEST-001/override", json=override_payload, headers=headers)
    assert res.status_code == 401, "Must return 401 for invalid/unknown session token."


def test_spoofed_body_role_rejected_with_403():
    # Login as STAFF_NURSE to get valid nurse token
    login_res = client.post("/api/auth/login", json={"username": "NURSE-01", "role": "STAFF_NURSE"})
    assert login_res.status_code == 200
    nurse_token = login_res.json()["access_token"]

    # First create a prescription and analyze it to generate a real warning
    create_res = client.post("/api/prescriptions", json={
        "patient_id": "PATIENT-001",
        "diagnosis": "CAP",
        "raw_text": "Amoxicillin 500mg PO TID",
        "items": [{"medication_name": "Amoxicillin", "dose": 500, "unit": "mg", "route": "PO", "frequency": "TID"}]
    })
    presc_id = create_res.json()["prescription_id"]
    analyze_res = client.post(f"/api/prescriptions/{presc_id}/analyze")
    warn_id = analyze_res.json()["warnings"][0]["warning_id"]

    # Attempt override passing clinician_role="ATTENDING_PHYSICIAN" in body but with nurse_token
    headers = {"Authorization": f"Bearer {nurse_token}"}
    override_payload = {
        "warning_id": warn_id,
        "clinician_role": "ATTENDING_PHYSICIAN",  # Spoofed body claim
        "override_reason": "I am claiming to be an attending physician in the request body."
    }
    ovr_res = client.post(f"/api/warnings/{warn_id}/override", json=override_payload, headers=headers)
    assert ovr_res.status_code == 403, "Must reject override with 403 based on server-side token role."
    assert "not authorized to override" in ovr_res.json()["detail"]


def test_authorized_override_succeeds_with_200():
    # Login as Attending Physician
    login_res = client.post("/api/auth/login", json={"username": "DOC-VERMA", "role": "ATTENDING_PHYSICIAN"})
    assert login_res.status_code == 200
    attending_token = login_res.json()["access_token"]

    # Create & analyze prescription
    create_res = client.post("/api/prescriptions", json={
        "patient_id": "PATIENT-001",
        "diagnosis": "CAP",
        "raw_text": "Amoxicillin 500mg PO TID",
        "items": [{"medication_name": "Amoxicillin", "dose": 500, "unit": "mg", "route": "PO", "frequency": "TID"}]
    })
    presc_id = create_res.json()["prescription_id"]
    analyze_res = client.post(f"/api/prescriptions/{presc_id}/analyze")
    warn_id = analyze_res.json()["warnings"][0]["warning_id"]

    # Override with valid attending token
    headers = {"Authorization": f"Bearer {attending_token}"}
    override_payload = {
        "warning_id": warn_id,
        "override_reason": "Documented negative skin prick testing in verified clinic allergy challenge."
    }
    ovr_res = client.post(f"/api/warnings/{warn_id}/override", json=override_payload, headers=headers)
    assert ovr_res.status_code == 200
    assert ovr_res.json()["status"] == "CONFIRMED"


def test_rule_authoring_endpoint_authorization():
    # Login as STAFF_NURSE -> forbidden to author rules
    nurse_res = client.post("/api/auth/login", json={"username": "NURSE-01", "role": "STAFF_NURSE"})
    nurse_token = nurse_res.json()["access_token"]
    
    rule_payload = {
        "rule_id": "ALLERGY-001",
        "action": "UPDATED",
        "change_summary": "Updated guideline citation wording."
    }
    res_nurse = client.post("/api/rules", json=rule_payload, headers={"Authorization": f"Bearer {nurse_token}"})
    assert res_nurse.status_code == 403

    # Login as ID Specialist -> authorized
    id_res = client.post("/api/auth/login", json={"username": "DOC-ID-01", "role": "INFECTIOUS_DISEASE_SPECIALIST"})
    id_token = id_res.json()["access_token"]
    res_id = client.post("/api/rules", json=rule_payload, headers={"Authorization": f"Bearer {id_token}"})
    assert res_id.status_code == 200
    assert res_id.json()["status"] == "RULE_AUTHORSHIP_RECORDED"
