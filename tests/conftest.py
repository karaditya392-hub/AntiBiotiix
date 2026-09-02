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
import os

import pytest

# The appointment notification scheduler is a real background thread in the app's
# lifespan. Tests drive the scans directly, so leave the timer off rather than
# starting one thread per TestClient. Read at thread start, so setting it here is
# enough regardless of import order.
os.environ.setdefault("S11_NOTIFICATION_SCHEDULER", "0")

# The AGENT layer must be off for the whole suite, whatever is in .env, because a
# test that reaches a hosted model is not deterministic: the agent tests stub
# llm_client explicitly, and anything that does not stub it must take the no-model
# path, which is the behaviour those tests assert.
#
# THE RETRIEVAL LAYER IS A DIFFERENT MATTER, and conflating the two cost an hour.
# Since the index moved to a hosted embedding model, the suite can no longer be
# run with no network at all -- query embedding is an API call. That is a real
# consequence of EMBEDDING_BACKEND=nvidia and it is stated here rather than
# discovered on a machine with no connectivity. Set EMBEDDING_BACKEND=local and
# migrate back if an offline suite matters more than retrieval quality.
#
# The web path stays off for every test: a suite whose results depend on what a
# search engine returned this morning is not a suite.
os.environ["WEB_SEARCH_ENABLED"] = "false"
os.environ["WEB_SEARCH_API_KEY"] = ""

# NVIDIA_API_KEY is deliberately NOT blanked, and that is a change from the first
# version of this file. Blanking it stopped the agent tests reaching a hosted
# model, which was the intent -- but it also stopped the EMBEDDING backend from
# starting, and the guideline index is now built with nvidia/nemotron-3-embed-1b.
# The store then found a backend mismatch and re-embedded all 15,894 chunks in
# memory on every run: the suite went from four minutes to over ten, and it was
# silently testing MiniLM retrieval against an index the application does not use.
#
# So the agent LLM is disabled directly instead, by the fixture below. Embeddings
# keep their key; the agents get none.

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


@pytest.fixture(autouse=True)
def _no_hosted_agent_llm(monkeypatch):
    """
    No test reaches a hosted model unless it says so.

    Autouse, so a test that forgets cannot accidentally depend on a vendor being
    up, on a key being present, or on what a 120B model felt like answering. Tests
    that exercise the model path stub llm_client themselves; a test-level
    monkeypatch is applied after this one and therefore wins.
    """
    from backend.agents import llm_client

    monkeypatch.setattr(llm_client, "available", lambda: False)
