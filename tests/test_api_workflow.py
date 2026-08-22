"""
End-to-End API Integration & Clinical Workflow Test Suite (Sections 27, 28)
Verifies the full lifecycle: Prescription -> Extraction -> Analysis -> Evidence -> Override -> Audit.
"""
import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.models.database import init_db

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    init_db()


def test_system_health_and_version():
    res = client.get("/api/system/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert data["clinical_role"] == "CLINICAL_DECISION_SUPPORT_ONLY"

    res_ver = client.get("/api/system/model-version")
    assert res_ver.status_code == 200
    ver_data = res_ver.json()
    # Sources are derived from the ingested corpus, not hardcoded. Assert the
    # real document identity and the edition actually held (Spec 22).
    sources = str(ver_data["guideline_sources"])
    assert "Indian Council of Medical Research" in sources
    assert "2nd edition, 2019" in sources, "must advertise the edition actually ingested"
    assert "2022-2023" not in sources, "must not claim an edition this system does not hold"
    assert "Deterministic" in ver_data["stewardship_priority_method"]


def test_patient_list_and_details():
    res = client.get("/api/patients")
    assert res.status_code == 200
    patients = res.json()
    assert len(patients) >= 10
    
    # Test specific patient (PATIENT-001)
    p1 = client.get("/api/patients/PATIENT-001")
    assert p1.status_code == 200
    assert "Penicillin" in p1.json()["allergies"]


def test_end_to_end_prescription_workflow():
    # 1. Extraction from free text
    extract_payload = {"raw_text": "Amoxicillin 500mg PO TID x 7 days for CAP"}
    ext_res = client.post("/api/prescriptions/extract", json=extract_payload)
    assert ext_res.status_code == 200
    ext_data = ext_res.json()
    assert len(ext_data["items"]) == 1
    assert ext_data["items"][0]["medication_name"] == "Amoxicillin"

    # 2. Create Prescription for PATIENT-001 (has Penicillin allergy)
    presc_payload = {
        "patient_id": "PATIENT-001",
        "diagnosis": "Community-Acquired Pneumonia",
        "raw_text": "Amoxicillin 500mg PO TID x 7 days",
        "items": ext_data["items"],
        "clinician_id": "DOC-ADITYA-01",
        "clinician_role": "ATTENDING_PHYSICIAN"
    }
    create_res = client.post("/api/prescriptions", json=presc_payload)
    assert create_res.status_code == 200
    presc_id = create_res.json()["prescription_id"]

    # 3. Analyze Prescription
    analyze_res = client.post(f"/api/prescriptions/{presc_id}/analyze")
    assert analyze_res.status_code == 200
    analysis = analyze_res.json()
    assert analysis["total_warnings"] >= 1
    rule_ids = [w["rule_id"] for w in analysis["warnings"]]
    assert "ALLERGY-001" in rule_ids or "ALLERGY-002" in rule_ids

    warning_id = analysis["warnings"][0]["warning_id"]

    # 4. View Evidence
    ev_res = client.get(f"/api/warnings/{warning_id}/evidence")
    assert ev_res.status_code == 200
    ev_data = ev_res.json()
    assert "ICMR" in ev_data["document_title"]
    assert "precedence_hierarchy" in ev_data

    # 5. Clinician Override with Authenticated Bearer Token
    override_payload = {
        "warning_id": warning_id,
        "override_reason": "Patient underwent formal desensitization protocol in 2024; skin prick test negative."
    }
    headers = {"Authorization": "Bearer mock_attending_token"}
    ovr_res = client.post(f"/api/warnings/{warning_id}/override", json=override_payload, headers=headers)
    assert ovr_res.status_code == 200
    assert ovr_res.json()["status"] == "CONFIRMED"

    # 6. Verify Immutable Audit Trail
    audit_res = client.get(f"/api/audit/logs?prescription_id={presc_id}")
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert len(logs) >= 2  # SUBMITTED/ANALYZED + OVERRIDE
    event_types = [l["event_type"] for l in logs]
    assert "PRESCRIPTION_ANALYZED" in event_types
    assert "CLINICIAN_OVERRIDE" in event_types

    # 7. Cryptographically Verify Audit Chain
    verify_res = client.get("/api/audit/verify")
    assert verify_res.status_code == 200
    assert verify_res.json()["valid"] is True
