"""
RAG corpus provenance test suite.

The corpus now holds three provenance classes, and the whole point of these tests is
that a citation drawn from one can never be mistaken for a citation from another:

  OFFICIAL_PDF                      hash-verified publication; `p. N` is a real page
  GOOGLE_DOCS_EXPORT_TRANSCRIPTION  operator-attested edition; N is a TRANSCRIPT page
  PLAIN_TEXT_TRANSCRIPTION          operator-attested edition; no page locator exists

A transcript page rendered as "p. 4" would invite a clinician to open page 4 of an
edition where the passage may sit somewhere else entirely. That is the failure these
tests exist to prevent.
"""
import io
import json
import os

import pytest

from backend.rag.store import (
    PAGE_NONE,
    PAGE_OFFICIAL,
    PAGE_TRANSCRIPT,
    GuidelineVectorStore,
    vector_store,
)

RAG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend", "guidelines", "data", "rag",
)

OFFICIAL = {
    "ICMR-STG-2019-ED2": "74e988ffe0603263ce131d043a187302d5845fbc4ff30aa74f9190ce99ff5016",
    "WHO-AWARE-BOOK-2022": "4960ecc4fa5bab8281feda656a0da3176dafa1fd21971d87e3b2092d7dac562f",
    "ICMR-STW-VOL3-2022": "38ae15831b78518cb2372785c363a7d061a8a6f5b42592ee2a0dd43cedae6c10",
    "ICMR-STW-PTB-EPTB-2022": "95f06c22b936875baf358853e598e4425dfc667d1857fae8d64c9d3884490ad2",
}

TRANSCRIBED = {
    "ICMR-STG-2022-23-CH05-IAI": PAGE_NONE,
    "ICMR-STG-2022-23-CH06-SSTI": PAGE_NONE,
    "ICMR-STG-2022-23-CH07-BJI": PAGE_NONE,
    "ICMR-STG-2022-23-CH08-CNS": PAGE_TRANSCRIPT,
    "ICMR-STG-2022-23-CH09-UTI": PAGE_TRANSCRIPT,
    "ICMR-STG-2022-23-CH10-HAI": PAGE_TRANSCRIPT,
    "ICMR-STG-2022-23-CH11-IMM": PAGE_TRANSCRIPT,
}


def _docs():
    out = {}
    for name in sorted(os.listdir(RAG_DIR)):
        if not name.endswith(".json"):
            continue
        with io.open(os.path.join(RAG_DIR, name), encoding="utf-8") as f:
            payload = json.load(f)
        out[payload["document"]["document_id"]] = payload
    return out


# ---------------------------------------------------------------------------
# Corpus composition
# ---------------------------------------------------------------------------

def test_corpus_holds_all_eleven_documents():
    docs = _docs()
    assert len(docs) == 11
    for doc_id in list(OFFICIAL) + list(TRANSCRIBED):
        assert doc_id in docs, f"{doc_id} missing from the corpus"


def test_official_documents_keep_their_verified_hashes():
    docs = _docs()
    for doc_id, digest in OFFICIAL.items():
        doc = docs[doc_id]["document"]
        assert doc["file_sha256"] == digest, f"{doc_id} hash changed"
        assert doc.get("source_type", "OFFICIAL_PDF") == "OFFICIAL_PDF"
        assert doc.get("page_reference_kind", PAGE_OFFICIAL) == PAGE_OFFICIAL
        assert doc.get("provenance_basis", "HASH_VERIFIED_PDF") == "HASH_VERIFIED_PDF"
        assert doc["page_count"] and doc["page_count"] > 0


def test_transcriptions_declare_themselves_as_such():
    docs = _docs()
    for doc_id, page_kind in TRANSCRIBED.items():
        doc = docs[doc_id]["document"]
        assert doc["source_type"] in (
            "GOOGLE_DOCS_EXPORT_TRANSCRIPTION", "PLAIN_TEXT_TRANSCRIPTION")
        assert doc["page_reference_kind"] == page_kind
        assert doc["provenance_basis"] == "OPERATOR_ATTESTATION"
        assert "OPERATOR-ATTESTED EDITION, NOT VERIFIED" in doc["notes"]
        # The hash identifies the transcription, and the note must not let that
        # be read as confirmation of the edition.
        assert len(doc["file_sha256"]) == 64
        assert "SHA-256 identifies the transcription, not the edition" in doc["notes"]


def test_plain_text_documents_carry_no_page_numbers_at_all():
    docs = _docs()
    for doc_id, page_kind in TRANSCRIBED.items():
        if page_kind != PAGE_NONE:
            continue
        payload = docs[doc_id]
        assert payload["document"]["page_count"] is None
        for chunk in payload["chunks"]:
            assert chunk["page"] is None, (
                f"{doc_id} synthesised a page number for an unpaginated text file"
            )


def test_no_transcription_claims_to_be_a_hash_verified_pdf():
    for doc_id, payload in _docs().items():
        doc = payload["document"]
        if doc.get("source_type", "OFFICIAL_PDF") == "OFFICIAL_PDF":
            continue
        assert doc["provenance_basis"] != "HASH_VERIFIED_PDF"
        assert doc["page_reference_kind"] != PAGE_OFFICIAL


def test_edition_claim_is_marked_unverified_on_every_2022_23_chapter():
    docs = _docs()
    for doc_id in TRANSCRIBED:
        doc = docs[doc_id]["document"]
        assert "2022-23" in doc["version"]
        assert "unverified" in doc["version"].lower()
        assert "No official 2022-23 PDF is held" in doc["notes"]


# ---------------------------------------------------------------------------
# Citation rendering
# ---------------------------------------------------------------------------

def _chunk_for(document_id):
    vector_store.load()
    for c in vector_store.chunks:
        if c["document_id"] == document_id:
            return c
    pytest.skip(f"no chunks loaded for {document_id}")


def _retrieved(document_id):
    from backend.rag.store import RetrievedChunk

    doc = vector_store.docs[document_id]
    c = _chunk_for(document_id)
    return RetrievedChunk(
        document_id=document_id,
        document_title=doc.get("title", ""),
        issuing_org=doc.get("issuing_org", ""),
        geographic_scope=doc.get("geographic_scope", ""),
        version=doc.get("version", ""),
        publication_date=doc.get("publication_date", ""),
        source_url=doc.get("source_url", ""),
        page=c.get("page"),
        section=c.get("section"),
        text=c["text"],
        score=0.9,
        notes=doc.get("notes", ""),
        source_type=doc.get("source_type", "OFFICIAL_PDF"),
        page_reference_kind=doc.get("page_reference_kind", PAGE_OFFICIAL),
        provenance_basis=doc.get("provenance_basis", "HASH_VERIFIED_PDF"),
    )


def test_official_pages_render_as_plain_page_citations():
    cit = _retrieved("ICMR-STW-VOL3-2022").to_citation()
    assert "p. " in cit["section_page"]
    assert "transcript" not in cit["section_page"]
    assert "NOT an official page" not in cit["section_page"]
    assert cit["page_reference_kind"] == PAGE_OFFICIAL


def test_transcript_pages_are_never_rendered_as_official_pages():
    cit = _retrieved("ICMR-STG-2022-23-CH10-HAI").to_citation()
    assert "transcript p." in cit["section_page"]
    assert "NOT an official page of this edition" in cit["section_page"]
    assert cit["page_reference_kind"] == PAGE_TRANSCRIPT
    assert cit["provenance_basis"] == "OPERATOR_ATTESTATION"
    assert "OPERATOR-ATTESTED EDITION, NOT VERIFIED" in cit["provenance_note"]


def test_unpaginated_text_renders_no_page_locator():
    cit = _retrieved("ICMR-STG-2022-23-CH07-BJI").to_citation()
    assert "no pagination" in cit["section_page"]
    assert "p. " not in cit["section_page"].replace("no pagination", "")
    assert cit["page_reference_kind"] == PAGE_NONE


def test_every_citation_carries_its_provenance_basis():
    vector_store.load()
    for doc_id in vector_store.docs:
        cit = _retrieved(doc_id).to_citation()
        assert cit["provenance_basis"] in ("HASH_VERIFIED_PDF", "OPERATOR_ATTESTATION")
        assert cit["page_reference_kind"] in (PAGE_OFFICIAL, PAGE_TRANSCRIPT, PAGE_NONE)
        assert cit["verbatim_passage"]


# ---------------------------------------------------------------------------
# Index integrity
# ---------------------------------------------------------------------------

def test_vector_index_is_aligned_with_the_expanded_corpus():
    store = GuidelineVectorStore()
    assert store.load() is True, (
        "the vector index is missing or misaligned with the corpus; rebuild it with "
        "GuidelineVectorStore().build() after any ingestion"
    )
    assert store.available
    assert len(store.chunks) == store.matrix.shape[0]
    assert len(store.docs) == 11


def test_new_chapters_are_actually_retrievable():
    vector_store.load()
    ids = [d for d in vector_store.docs if d.startswith("ICMR-STG-2022-23")]
    assert len(ids) == 7

    hits = vector_store.search("catheter associated urinary tract infection", k=3, document_ids=ids)
    assert hits, "the ingested 2022-23 chapters returned nothing"
    assert all(h.document_id in ids for h in hits)


def test_retrieval_still_refuses_off_domain_queries():
    """Expanding the corpus must not weaken the refusal path."""
    from backend.rag.retrieve import retrieve

    result = retrieve("how do I change a bicycle tyre", k=3).to_dict()
    assert result["refused"] is True
    assert not result["retrieved"]
