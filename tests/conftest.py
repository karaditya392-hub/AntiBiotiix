"""
Shared test bootstrap.

Several suites assert against the seeded synthetic patients -- PATIENT-001's
penicillin allergy in particular. If the database has not been seeded, those
assertions fail as `assert 'Penicillin' in []`, which points nowhere near the
actual cause and reads like a broken allergy engine.

Worse, the failure used to be self-inflicting: running the tests against an empty
database created PATIENT-001 with no allergies, and the seeder then skipped it as
already present, so re-seeding could not repair it. The seeder now converges
seeded records instead of skipping them; this check is the other half, so the
problem is reported at the start of the run in plain language rather than as a
misleading assertion twenty tests later.
"""
import pytest

from backend.models.database import PatientDB, SessionLocal, init_db

# The fixtures the suites actually depend on, and why.
REQUIRED_FIXTURES = {
    "PATIENT-001": "penicillin allergy - drives the ALLERGY-001/002 tests",
    "PATIENT-002": "renal impairment - drives the RENAL tests",
    "PATIENT-004": "pregnancy - drives the VULN tests",
}

SEED_COMMAND = "python -m backend.seed_data"


@pytest.fixture(scope="session", autouse=True)
def verify_seeded_database():
    """Fail fast, and say exactly what to run, if the fixtures are missing."""
    init_db()

    db = SessionLocal()
    try:
        problems = []
        for patient_id, purpose in REQUIRED_FIXTURES.items():
            patient = db.query(PatientDB).filter(PatientDB.patient_id == patient_id).first()
            if patient is None:
                problems.append(f"  {patient_id} is missing ({purpose})")
            elif patient_id == "PATIENT-001" and "Penicillin" not in (patient.allergies_json or ""):
                problems.append(
                    f"  {patient_id} exists but has no documented allergies ({purpose}).\n"
                    f"    This happens when the API is exercised before seeding, which creates\n"
                    f"    the record empty. Re-running the seeder now repairs it."
                )
    finally:
        db.close()

    if problems:
        pytest.exit(
            "\n\nThe test database is not seeded, so these suites cannot run:\n"
            + "\n".join(problems)
            + f"\n\nRun this first, then re-run the tests:\n    {SEED_COMMAND}\n",
            returncode=1,
        )

    yield

    # Clean up any non-seed test patients created during test execution
    from backend.seed_data import seed_database
    seed_database(reset_patients=True)
