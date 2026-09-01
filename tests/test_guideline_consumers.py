"""
The features that CONSUME the guideline corpus, tested against what it now holds.

Growing the corpus from 11 to 39 and then to 94 documents changed what these
features must say. Four kinds of failure are covered here, and each one had
actually occurred or would have:

  1. A feature that states a corpus fact from memory. The precedence endpoint
     reported "ICMR Edition 3", an edition this repository has never held.
  2. A gate calibrated on a smaller corpus that now excludes a document which
     plainly covers the topic. NCDC-NTG-AMR-2016 fell 0.003 short on pneumonia.
  3. A passage from a document that is not a clinical guideline being returned
     with nothing to say so.
  4. A document with no antimicrobial standing being counted as a source in an
     antimicrobial agent comparison. The ICMR batch added 22 cancer consensus
     documents at rank 2, all of which the old rank-based filter would have let
     vote on any infection topic they happened to match.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import (
    ANTIMICROBIAL_CONTENT_DOCUMENT_IDS,
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


def test_agent_differences_are_computed_across_antimicrobial_sources_only():
    """
    A leaflet not naming ceftriaxone is not a guideline declining to recommend it.
    Letting rank-4 documents vote would report an absence of authority as a
    difference of clinical opinion.

    The rule is now stronger than rank, because the ICMR national corpus showed rank
    was not enough: an oncology consensus document is a clinical guideline at rank 2
    and still has no opinion about antimicrobial choice. Only documents that carry
    antibacterial recommendations vote.
    """
    result = compare_sources("mass drug administration for lymphatic filariasis",
                             knowledge_base, vector_store)
    on_topic = [d for d in result["documents"] if d["has_guidance"]]
    reference_only = {d["document_id"] for d in on_topic if not d["is_clinical_guideline"]}
    assert reference_only, "expected this topic to surface a reference-only document"

    voting = {
        d["document_id"] for d in on_topic
        if d["document_id"] in ANTIMICROBIAL_CONTENT_DOCUMENT_IDS
    }
    assert result["documents_compared_for_agent_differences"] == len(voting)
    assert not (voting & reference_only)
    for difference in result["differing_agents"]:
        named = set(difference["named_by"]) | set(difference["not_named_by"])
        assert named <= voting, difference


def test_no_document_without_antimicrobial_content_votes_on_any_infection_topic():
    """
    The regression the ICMR batch would have caused. Twenty-two cancer consensus
    documents joined the corpus at rank 2; under the old rank-based filter each one
    that cleared the relevance gate would have been counted as a national guideline
    omitting whichever agent it does not mention.
    """
    for topic in ("intra abdominal infection", "febrile neutropenia", "sepsis"):
        result = compare_sources(topic, knowledge_base, vector_store)
        for difference in result["differing_agents"]:
            voters = set(difference["named_by"]) | set(difference["not_named_by"])
            stowaways = voters - set(ANTIMICROBIAL_CONTENT_DOCUMENT_IDS)
            assert not stowaways, f"{topic}: {stowaways} voted on {difference['drug']}"


def test_a_non_antimicrobial_document_shown_on_a_topic_declares_its_domain():
    """
    Documents outside the antimicrobial set are still shown as columns. Each must
    carry the reading contract for its own domain, so a reader scanning the
    side-by-side layout cannot take an oncology or ethics column for evidence about
    antimicrobial choice.
    """
    result = compare_sources("intra abdominal infection", knowledge_base, vector_store)
    shown = [d for d in result["documents"] if d["has_guidance"]]
    for doc in shown:
        if doc["document_id"] in ANTIMICROBIAL_CONTENT_DOCUMENT_IDS:
            continue
        assert doc["document_id"] in result["documents_shown_but_not_compared"]
        if doc["clinical_domain"] != "ANTIMICROBIAL_TREATMENT":
            assert doc["domain_caveat"], doc["document_id"]


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


# ---------------------------------------------------------------------------
# Document listing
#
# The corpus summary reported how many documents sat in each clinical domain and
# never reported which. A count nobody can open is not auditable, and the domain
# strip in the UI reads as a set of tabs, so a reader reasonably expects to be able
# to look behind each number.
# ---------------------------------------------------------------------------

def test_documents_endpoint_lists_the_whole_corpus():
    body = client.get("/api/guidelines/documents").json()
    assert body["total_documents"] == len(vector_store.docs)
    assert body["returned"] == body["total_documents"]


def test_every_domain_count_can_be_opened_and_matches():
    """
    The badge count and the list behind it come from the same corpus and must agree.
    A strip claiming 14 research-ethics documents that opens onto 9 would be worse
    than not opening at all.
    """
    corpus = client.get("/api/system/health").json()["guideline_corpus"]
    for domain, count in corpus["documents_by_clinical_domain"].items():
        body = client.get(f"/api/guidelines/documents?domain={domain}").json()
        assert body["returned"] == count, f"{domain}: strip says {count}, list returns {body['returned']}"
        assert all(d["clinical_domain"] == domain for d in body["documents"])


def test_listed_documents_carry_their_provenance():
    """A listing that drops provenance turns a transcription into a citation."""
    for doc in client.get("/api/guidelines/documents").json()["documents"]:
        assert doc["provenance_basis"], doc["document_id"]
        assert doc["page_reference_kind"], doc["document_id"]
        assert doc["precedence_rank"] is not None, doc["document_id"]


def test_non_antimicrobial_documents_carry_their_reading_contract():
    body = client.get("/api/guidelines/documents").json()
    for doc in body["documents"]:
        if doc["clinical_domain"] == "ANTIMICROBIAL_TREATMENT":
            continue
        assert doc["domain_caveat"], doc["document_id"]
        assert doc["carries_antimicrobial_authority"] is False, doc["document_id"]


def test_documents_are_ordered_by_precedence():
    ranks = [d["precedence_rank"] or 99
             for d in client.get("/api/guidelines/documents").json()["documents"]]
    assert ranks == sorted(ranks)


def test_an_unknown_domain_returns_nothing_rather_than_everything():
    body = client.get("/api/guidelines/documents?domain=NOT_A_REAL_DOMAIN").json()
    assert body["returned"] == 0
    assert body["documents"] == []


def test_documents_report_what_they_say_not_only_how_to_cite_them():
    """
    The provenance note says how a citation must be treated and deliberately says
    almost nothing about subject matter. For the 22 oncology consensus documents it
    is generated from one template, so a panel showing only that note rendered the
    gallbladder and retinoblastoma documents as near-identical text. A heading is
    not enough either: it names a topic without saying what the document says on it.
    """
    docs = client.get("/api/guidelines/documents").json()["documents"]
    with_topics = [d for d in docs if d["topics"]]
    assert len(with_topics) > len(docs) // 2
    for doc in with_topics:
        for topic in doc["topics"]:
            # The heading may legitimately be empty: documents whose headings the
            # ingest matcher never detected fall back to their opening passages, and
            # those are left unlabelled rather than given an invented heading. The
            # TEXT is what must always be there.
            assert topic["excerpt"], doc["document_id"]
            # An excerpt shorter than a sentence is a label, not a statement.
            assert len(topic["excerpt"]) >= 150, (doc["document_id"], topic["heading"])


def test_excerpts_are_clean_and_bounded():
    """
    Excerpts come from PDF extraction and carry its residue: soft hyphens, unmapped
    glyphs, running headers and chapter furniture. A legitimate en dash is NOT
    residue and must survive.
    """
    seen_en_dash = False
    for doc in client.get("/api/guidelines/documents").json()["documents"]:
        assert len(doc["topics"]) <= 8, doc["document_id"]
        for topic in doc["topics"]:
            text = topic["excerpt"]
            assert "­" not in text, (doc["document_id"], "soft hyphen")
            assert "�" not in text, (doc["document_id"], "unmapped glyph")
            assert not text.upper().startswith(("SECTION", "CHAPTER")), doc["document_id"]
            assert len(text) <= 470, doc["document_id"]
            if "–" in text:
                seen_en_dash = True
    assert seen_en_dash, "en dashes are document punctuation and must not be stripped"


def test_excerpts_are_verbatim_from_the_stored_corpus():
    """
    No summary is generated. Every excerpt must be findable in the document's own
    chunks, because a paraphrase of a clinical document is a new claim about it.
    """
    import re as _re

    def normalise(text: str) -> str:
        """
        Both sides are compared after the same repair the endpoint applies for
        display -- soft hyphens and unmapped glyphs removed, whitespace collapsed.
        Without this the test fails wherever the repair fired, which is not evidence
        that the excerpt was invented; it is evidence the repair happened.
        """
        text = text.replace("­", "").replace("�", "")
        return " ".join(text.split())

    docs = client.get("/api/guidelines/documents").json()["documents"]
    checked = 0
    for doc in docs[:12]:
        if not doc["topics"]:
            continue
        corpus = " ".join(
            normalise(c["text"])
            for c in vector_store.chunks if c["document_id"] == doc["document_id"]
        )
        for topic in doc["topics"]:
            # Take a distinctive run from the middle, clear of the trimmed opening
            # and the trailing ellipsis.
            body = normalise(topic["excerpt"]).rstrip(".").strip()
            probe = " ".join(body.split()[6:14])
            if len(probe) < 25 or "•" in probe:
                continue
            assert probe in corpus, (doc["document_id"], topic["heading"], probe[:60])
            checked += 1
    assert checked > 5, "expected to verify several excerpts against the corpus"


def test_two_documents_from_the_same_template_are_distinguishable():
    """The failure that prompted this: 22 oncology documents, one provenance template."""
    docs = {d["document_id"]: d for d in client.get("/api/guidelines/documents").json()["documents"]}
    gallbladder = docs["ICMR-CONSENSUS-GALLBLADDER-2014"]
    colorectal = docs["ICMR-CONSENSUS-COLORECTAL-2014"]
    # Their provenance notes come from the same template and are near-identical.
    assert gallbladder["provenance_note"][:120] == colorectal["provenance_note"][:120]
    # What the panel now leads with must still tell them apart.
    assert gallbladder["topics"] != colorectal["topics"]


def test_excerpts_are_prose_not_contents_pages_or_forms():
    """
    Three classes of page extract as text and say nothing: contents listings,
    reporting forms and staging flowcharts. The ethics guidelines leaked a contents
    page ("Special situations 55 5.11 Consent for studies using deception 55") past
    a dot-leader check, because that contents page has no dot leaders -- its numbers
    interleave with the headings instead.
    """
    import re as _re

    bare_number = _re.compile(r"(?<![\w.])\d{1,3}(?![\w.%])")
    for doc in client.get("/api/guidelines/documents").json()["documents"]:
        for topic in doc["topics"]:
            text = topic["excerpt"]
            letters = sum(ch.isalpha() or ch.isspace() for ch in text)
            assert letters / len(text) >= 0.82, (doc["document_id"], topic["heading"])
            assert len(bare_number.findall(text)) <= 10, (doc["document_id"], topic["heading"])
            assert "...." not in text, (doc["document_id"], topic["heading"])


def test_every_document_shows_something_of_its_own_text():
    """
    Excerpts were anchored to detected section headings, and eight condition-specific
    documents have none the ingest matcher recognises -- the type 1 diabetes guideline
    has 604 chunks and zero, neonatal jaundice 71 and zero. Those documents rendered
    blank, and because the list sorts by title the blank ones sorted to the top.

    A document with no headings still has an opening, and quoting it is no weaker a
    claim than quoting a passage that happens to sit under one.
    """
    docs = client.get("/api/guidelines/documents").json()["documents"]
    blank = [d["document_id"] for d in docs if not d["topics"]]
    assert not blank, f"documents showing no text of their own: {blank}"


def test_a_passage_without_a_heading_is_left_unlabelled_not_invented():
    docs = client.get("/api/guidelines/documents").json()["documents"]
    headless = [t for d in docs for t in d["topics"] if not t["heading"]]
    assert headless, "expected some documents to fall back to opening passages"
    for topic in headless:
        assert topic["excerpt"], "an unlabelled passage must still carry its text"
