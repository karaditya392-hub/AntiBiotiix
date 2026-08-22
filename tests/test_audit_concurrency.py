"""
Audit Log Concurrency & Hash-Chain Integrity Test Suite
Verifies that concurrent event logging preserves an unbranched, cryptographically valid SHA-256 hash chain.
"""
import concurrent.futures
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.models.database import SessionLocal, init_db, AuditLogDB
from backend.audit.logger import ClinicalAuditLogger

client = TestClient(app)


def test_concurrent_audit_logging_preserves_valid_hash_chain():
    """
    Simulate multiple concurrent threads writing audit logs simultaneously.
    Assert that the entire hash chain validates without fork or broken links.
    """
    init_db()
    logger = ClinicalAuditLogger()
    num_threads = 20

    def log_task(index: int):
        db = SessionLocal()
        try:
            entry = logger.log_event(
                db=db,
                event_type="CONCURRENT_TEST_EVENT",
                prescription_id=f"RX-CONC-{index:03d}",
                patient_id=f"PATIENT-{(index % 5) + 1:03d}",
                clinician_id="CLIN-TEST-CONC",
                clinician_role="ATTENDING_PHYSICIAN",
                action_summary=f"Concurrent audit test event #{index}",
                payload={"thread_index": index, "status": "CONCURRENT_LOGGED"}
            )
            return entry.log_id, entry.integrity_hash
        finally:
            db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(log_task, i) for i in range(num_threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == num_threads, f"Expected {num_threads} entries, got {len(results)}"

    # Validate the full hash chain via verification endpoint
    res = client.get("/api/audit/verify")
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True, f"Hash chain verification failed: {data}"
    assert data["verification_status"] == "CRYPTOGRAPHICALLY_VERIFIED"
    assert data["broken_records"] == []
    assert data["total_records"] >= num_threads
