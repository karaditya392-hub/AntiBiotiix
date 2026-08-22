"""
Guideline ingestion + retrieval (Spec §9, §13, §14, §16, §21, §22, §23).

The two behaviours that matter most here:
  1. Retrieval refuses rather than returning best-of-a-bad-set.
  2. Retrieval NEVER gates whether a clinical rule fires.
"""
import json
from pathlib import Path

import pytest

from backend.models.schemas import PatientCreate, PrescriptionCreate, PrescriptionItem
from backend.rag import retrieve as retrieve_mod
from backend.rag.retrieve import NO_EVIDENCE, retrieve, unknown_entities
from backend.rag.store import vector_store
from backend.rules.engine import rule_engine

RAG_DIR = Path("backend/guidelines/data/rag")


# --- ingestion / provenance (§13, §14, §21, §22) ---------------------------

def test_corpus_ingested_from_real_documents():
    assert vector_store.available, "vector index not built"
    assert len(vector_store.docs) >= 2
    assert len(vector_store.chunks) > 500


@pytest.mark.parametrize("doc_id", ["WHO-AWARE-BOOK-2022", "ICMR-STG-2019-ED2"])
def test_document_provenance_complete(doc_id):
    payload = json.loads((RAG_DIR / f"{doc_id}.json").read_text(encoding="utf-8"))
    doc = payload["document"]
    for field in ("title", "issuing_org", "geographic_scope", "version",
                  "publication_date", "source_url", "file_sha256",
                  "page_count", "ingested_at"):
        assert doc.get(field), f"{doc_id} missing provenance field {field}"
    assert len(doc["file_sha256"]) == 64


def test_chunks_carry_page_anchors():
    """§21: the evidence chain must reach a page in the source document."""
    for c in vector_store.chunks[:200]:
        assert isinstance(c["page"], int) and c["page"] >= 1
        assert c["document_id"] and c["version"]
        assert c["char_end"] > c["char_start"]


def test_icmr_edition_mismatch_is_recorded():
    """
    The ingested ICMR PDF is Edition 2 (2019); the rule catalog cites Edition 3
    (2022-2023). §22 forbids silently mixing versions, so the discrepancy must be
    recorded on the document itself.
    """
    doc = json.loads((RAG_DIR / "ICMR-STG-2019-ED2.json").read_text(encoding="utf-8"))["document"]
    assert "2019" in doc["version"]
    assert "MISMATCH" in doc["notes"].upper()


# --- the hard refusal floor (§9, §23) --------------------------------------

@pytest.mark.parametrize("query", [
    "how do I fix a leaking kitchen tap",
    "best pizza recipe in Naples",
    "what is the capital of France",
])
def test_off_domain_queries_are_refused(query):
    r = retrieve(query, k=3)
    assert r.refused
    assert NO_EVIDENCE in r.reason
    assert r.chunks == []


@pytest.mark.parametrize("query,term", [
    ("zzzzmycin 500mg indications", "zzzzmycin"),
    ("blorbotrexate contraindications", "blorbotrexate"),
    ("xyzzy fictionalcillin dosing", "fictionalcillin"),
])
def test_nonexistent_drug_is_refused_and_named(query, term):
    """
    Cosine similarity alone cannot catch these: a nonsense drug in a well-formed
    dosing question matches dosing sections on sentence form. The lexical
    grounding check is what rejects them.
    """
    r = retrieve(query, k=3)
    assert r.refused
    assert term in r.reason
    assert r.chunks == []


@pytest.mark.parametrize("query", [
    "first line treatment for uncomplicated cystitis",
    "nitrofurantoin renal impairment",
    "WHO Reserve group antibiotics",
    "duration of therapy community acquired pneumonia",
    "treatment of typhoid fever",
    "septic shock empiric therapy",
])
def test_legitimate_queries_return_cited_evidence(query):
    r = retrieve(query, k=3)
    assert not r.refused, f"legitimate query wrongly refused: {query}"
    assert r.chunks
    top = r.chunks[0].to_citation()
    assert top["verbatim_passage"].strip()
    assert top["section_page"].startswith(("p. ", "1", "2", "3", "4", "5", "6", "7", "8", "9")) or "p." in top["section_page"]
    assert top["issuing_org"]
    assert top["guideline_version"]


def test_empty_query_refused():
    assert retrieve("", k=3).refused


def test_unknown_entities_ignores_ordinary_english():
    assert unknown_entities("recommended treatment duration for patients") == []


# --- rule independence (§16) -----------------------------------------------

def _warnings():
    patient = PatientCreate(
        patient_id="TEST-RAG", age=70, allergies=["Penicillin"],
        allergy_status_known=True, egfr_ml_min=18.0, renal_status_known=True,
    )
    presc = PrescriptionCreate(
        patient_id="TEST-RAG", diagnosis="uncomplicated cystitis",
        items=[
            PrescriptionItem(medication_name="Nitrofurantoin", dose=100, unit="mg",
                             route="PO", frequency="BID", duration_days=5),
            PrescriptionItem(medication_name="Amoxicillin", dose=500, unit="mg",
                             route="PO", frequency="TID", duration_days=7),
        ],
    )
    return rule_engine.evaluate_prescription(patient, presc, prescription_id="RX-RAG")


def test_rules_unchanged_when_vector_store_offline(monkeypatch):
    """A rule that fires today must still fire with the index gone."""
    before = [(w.rule_id, w.severity.value) for w in _warnings()]
    assert before, "fixture should produce warnings"

    monkeypatch.setattr(vector_store, "matrix", None)
    assert not vector_store.available
    after = [(w.rule_id, w.severity.value) for w in _warnings()]
    assert after == before


def test_retrieval_refuses_gracefully_when_store_offline(monkeypatch):
    monkeypatch.setattr(vector_store, "matrix", None)
    r = retrieve("uncomplicated cystitis", k=3)
    assert r.refused
    assert "unavailable" in r.reason.lower()


def test_rule_engine_does_not_import_retrieval():
    """Structural guarantee that retrieval cannot gate rule firing."""
    import backend.rules.engine as eng
    src = Path(eng.__file__).read_text(encoding="utf-8")
    assert "backend.rag" not in src


# --- store integrity -------------------------------------------------------

def test_store_reports_pgvector_status_honestly():
    d = vector_store.backend_description()
    assert d["pgvector_status"] == "PENDING_POSTGRES_MIGRATION"
    assert d["embedding_model"]


def test_query_with_mismatched_embedding_model_returns_nothing():
    """A store built with one model must not be queried with another."""
    class Fake:
        name = "some-other-model"
        dim = 8
        is_semantic = True

        def encode(self, texts):
            import numpy as np
            return np.zeros((len(texts), 8), dtype="float32")

    assert vector_store.search("cystitis", k=3, backend=Fake()) == []
