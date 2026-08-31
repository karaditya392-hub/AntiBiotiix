"""
The features that CONSUME the guideline corpus, tested against what it now holds.

Growing the corpus from 11 to 39 documents changed what these features must say.
Three kinds of failure are covered here, and each one had actually occurred:

  1. A feature that states a corpus fact from memory. The precedence endpoint
     reported "ICMR Edition 3", an edition this repository has never held.
  2. A gate calibrated on a smaller corpus that now excludes a document which
     plainly covers the topic. NCDC-NTG-AMR-2016 fell 0.003 short on pneumonia.
  3. A passage from a document that is not a clinical guideline being returned
     with nothing to say so.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import (
    GUIDELINE_PRECEDENCE_HIERARCHY,
    NATIONAL_ANTIMICROBIAL_AUTHORITY_DOCUMENT_IDS,
)
from backend.guidelines.cross_source import compare_sources
from backend.guidelines.knowledge_base import knowledge_base
from backend.rag.ask import ask
from backend.rag.retrieve import LEXICAL_RELEVANCE_FLOOR, RELEVANCE_FLOOR, retrieve
from backend.rag.store import NOT_A_CLINICAL_GUIDELINE_RANK, vector_store

client = TestClient(app)

# A query that lands squarely in a rank-4 document held for reference only.
REFERENCE_ONLY_QUERY = "what is chikungunya fever"


# ---------------------------------------------------------------------------
# Corpus facts are read, never remembered
# ---------------------------------------------------------------------------

def test_health_reports_the_corpus_it_actually_holds():
    body = client.get("/api/system/health").json()
    corpus = body["guideline_corpus"]
    assert corpus["documents"] == len(vector_store.docs)
    assert corpus["chunks"] == len(vector_store.chunks)
    assert corpus["documents_by_precedence_rank"]
    # The two facts that change how a passage must be read.
    assert corpus["national_antimicrobial_authorities"]
    assert corpus["held_for_reference_not_clinical_guidelines"]


def test_precedence_names_the_editions_held_not_an_edition_from_memory():
    body = client.get("/api/guidelines/precedence").json()
    authorities = body["national_antimicrobial_authorities"]
    assert [a["document_id"] for a in authorities] == [
        d for d in NATIONAL_ANTIMICROBIAL_AUTHORITY_DOCUMENT_IDS if d in vector_store.docs
    ]
    scope = body["selected_scope"]
    for authority in authorities:
        assert authority["version"] in scope
    # The specific false claim this replaced. ICMR Edition 3 has never been held:
    # the corpus has the 2nd edition (2019) plus operator-attested 2022-23 chapters.
    assert "Edition 3" not in scope


def test_two_national_authorities_are_disclosed_without_adjudication():
    body = client.get("/api/guidelines/precedence").json()
    assert len(body["national_antimicrobial_authorities"]) == 2
    note = body["multiple_national_authorities_note"]
    assert "Neither supersedes the other" in note
    assert "no adjudication" in note


def test_precedence_hierarchy_defines_every_rank_a_document_uses():
    """A rank rendered in the UI with no entry describing it is an unexplained number."""
    defined = {entry["rank"] for entry in GUIDELINE_PRECEDENCE_HIERARCHY}
    used = {d.get("precedence_rank") for d in vector_store.docs.values()}
    assert used <= defined, f"ranks in use with no hierarchy entry: {used - defined}"
    assert NOT_A_CLINICAL_GUIDELINE_RANK in defined


# ---------------------------------------------------------------------------
# Retrieval carries the standing of what it returned
# ---------------------------------------------------------------------------

def test_citations_carry_precedence_rank_and_clinical_standing():
    result = retrieve("empirical therapy for enteric fever", k=3)
    assert not result.refused
    for citation in [c.to_citation() for c in result.chunks]:
        assert citation["precedence_rank"] is not None
        assert citation["is_clinical_guideline"] is True
        # A guideline must not carry a caveat that belongs to reference material.
        assert citation["clinical_standing"] is None


def test_a_reference_only_passage_says_so_on_the_passage_and_on_the_response():
    result = retrieve(REFERENCE_ONLY_QUERY, k=3)
    assert not result.refused
    assert result.non_clinical_sources

    citation = result.chunks[0].to_citation()
    assert citation["is_clinical_guideline"] is False
    assert citation["precedence_rank"] == NOT_A_CLINICAL_GUIDELINE_RANK
    assert "NOT A CLINICAL GUIDELINE" in citation["clinical_standing"]

    caveat = " ".join(result.caveats())
    assert "held for reference only" in caveat
    assert "never a basis for a prescribing" in caveat


def test_ask_the_evidence_passes_the_caveat_through_to_its_answer():
    result = ask(REFERENCE_ONLY_QUERY, k=3).to_dict()
    assert result["answered"] is True
    assert any("held for reference only" in c for c in result["caveats"])
    assert any(p["is_clinical_guideline"] is False for p in result["passages"])


def test_ask_carries_no_reference_caveat_for_a_guideline_answer():
    result = ask("empirical therapy for enteric fever", k=3).to_dict()
    assert result["answered"] is True
    assert not any("held for reference only" in c for c in result["caveats"])


# ---------------------------------------------------------------------------
# Relevance floors, re-measured on this corpus
# ---------------------------------------------------------------------------

def test_the_semantic_floor_still_clears_the_measured_off_domain_ceiling():
    """
    The floor was raised from 0.35 to 0.45 because the expanded corpus pushed
    off-domain scores up to 0.341 -- a food composition table in the burns document
    and rehabilitation language in the leprosy guideline both match ordinary English.
    """
    assert RELEVANCE_FLOOR >= 0.45
    for query in ("how to train a puppy", "best pizza recipe in Naples",
                  "how to fix a leaking kitchen tap", "how do I change a bicycle tyre"):
        assert retrieve(query, k=3).refused is True, query


def test_legitimate_questions_still_clear_the_raised_floor():
    for query in ("nitrofurantoin renal impairment", "doxycycline for leptospirosis",
                  "rabies post exposure prophylaxis schedule",
                  "syndromic management of vaginal discharge",
                  "multibacillary leprosy MDT duration"):
        assert retrieve(query, k=3).refused is False, query


def test_the_lexical_floor_documents_the_overlap_it_cannot_resolve():
    """
    On this corpus the lexical fallback can no longer separate off-domain English
    from clinical questions by score, so the failure must be disclosed rather than
    hidden behind a threshold that looks authoritative.
    """
    from backend.rag import retrieve as retrieve_mod

    assert LEXICAL_RELEVANCE_FLOOR >= 0.17
    caveat = retrieve_mod.LEXICAL_OVERLAP_CAVEAT
    assert "LEXICAL, not semantic" in caveat
    assert "overlap" in caveat


# ---------------------------------------------------------------------------
# Cross-source comparison
# ---------------------------------------------------------------------------

def test_a_national_antimicrobial_guideline_is_not_gated_out_of_its_own_syndromes():
    """
    Regression guard for the relative threshold. At 0.85 the NCDC guideline was
    dropped from topics its own syndromic therapy chapter covers, missing the bar
    by 0.003 on pneumonia and 0.0006 on UTI.
    """
    shown = 0
    topics = ["community acquired pneumonia", "urinary tract infection",
              "enteric fever", "infective endocarditis"]
    for topic in topics:
        result = compare_sources(topic, knowledge_base, vector_store)
        on_topic = {d["document_id"] for d in result["documents"] if d["has_guidance"]}
        shown += "NCDC-NTG-AMR-2016" in on_topic
    assert shown >= 3, f"NCDC surfaced on only {shown} of {len(topics)} syndrome topics"


def test_cross_source_labels_reference_only_documents():
    result = compare_sources(REFERENCE_ONLY_QUERY, knowledge_base, vector_store)
    reference_only = [d for d in result["documents"]
                      if d["precedence_rank"] == NOT_A_CLINICAL_GUIDELINE_RANK]
    assert reference_only
    for doc in reference_only:
        assert doc["is_clinical_guideline"] is False
        assert "not a clinical guideline" in doc["clinical_standing"]
    for doc in result["documents"]:
        if doc["precedence_rank"] != NOT_A_CLINICAL_GUIDELINE_RANK:
            assert doc["is_clinical_guideline"] is True
            assert doc["clinical_standing"] is None


def test_agent_differences_are_computed_across_guidelines_only():
    """
    A leaflet not naming ceftriaxone is not a guideline declining to recommend it.
    Letting rank-4 documents vote would report an absence of authority as a
    difference of clinical opinion.
    """
    result = compare_sources("mass drug administration for lymphatic filariasis",
                             knowledge_base, vector_store)
    on_topic = [d for d in result["documents"] if d["has_guidance"]]
    reference_only = {d["document_id"] for d in on_topic if not d["is_clinical_guideline"]}
    assert reference_only, "expected this topic to surface a reference-only document"

    assert result["documents_compared_for_agent_differences"] == len(on_topic) - len(reference_only)
    for difference in result["differing_agents"]:
        named = set(difference["named_by"]) | set(difference["not_named_by"])
        assert not (named & reference_only), difference


def test_cross_source_orders_reference_only_documents_last():
    result = compare_sources(REFERENCE_ONLY_QUERY, knowledge_base, vector_store)
    ranks = [d["precedence_rank"] or 99 for d in result["documents"]]
    assert ranks == sorted(ranks)


@pytest.mark.parametrize("topic", ["urinary tract infection", "enteric fever"])
def test_cross_source_admits_nothing_off_scope_on_an_infection_topic(topic):
    """The relaxed relative gate must not have opened the door to unrelated sources."""
    off_scope = {
        "MOHFW-STG-OA-KNEE-2017", "MOHFW-STG-DRY-EYE-2016",
        "MOHFW-STG-ALCOHOL-DEPENDENCE-2016", "MOHFW-STG-HYPERTENSION-2016",
        "AYURVEDA-STG-UNATTRIBUTED-UNDATED", "NPCDCS-MO-MANUAL-UNDATED",
    }
    result = compare_sources(topic, knowledge_base, vector_store)
    on_topic = {d["document_id"] for d in result["documents"] if d["has_guidance"]}
    assert not (on_topic & off_scope), on_topic & off_scope
