"""
Agent 3 - precedence-aware grounding.

The tests that matter are the ordering and the refusals: a confident web source
must never sort above a national guideline, and web evidence alone must never be
enough to ground an antimicrobial answer.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.agents.grounding import (
    INSUFFICIENT_EMPTY, INSUFFICIENT_NO_AUTHORITY, WEB_ONLY_NOTICE, ground,
)
from backend.agents.provenance import ORIGIN_HELD_CORPUS, ORIGIN_WEB, web_citation
from backend.config import WEB_EVIDENCE_PRECEDENCE_RANK

CHOLANGITIS_Q = "Empirical therapy for acute cholangitis"


class _Chunk:
    """Stands in for a RetrievedChunk; only to_citation() is used by the agent."""

    def __init__(self, citation: Dict[str, Any]):
        self._c = citation

    def to_citation(self) -> Dict[str, Any]:
        return dict(self._c)


@dataclass
class _Retrieval:
    chunks: List[_Chunk] = field(default_factory=list)
    refused: bool = False

    def caveats(self) -> List[str]:
        return []


def held(rank=2, score=0.7, authority=True, text="Ceftriaxone with metronidazole.",
         title="ICMR National Treatment Guidelines", issuer="ICMR, MoHFW"):
    return _Chunk({
        "document_title": title,
        "issuing_org": issuer,
        "section_page": "p. 44",
        "verbatim_passage": text,
        "retrieval_score": score,
        "precedence_rank": rank,
        "is_clinical_guideline": rank != 4,
        "carries_antimicrobial_authority": authority,
        "clinical_domain": "ANTIMICROBIAL_TREATMENT",
        "domain_caveat": None,
        "clinical_standing": None,
        "source_url": "https://icmr.gov.in/x",
    })


def web(score=0.99, text="Piperacillin-tazobactam is preferred.", url="https://who.int/a"):
    return web_citation(url=url, title="WHO page", passage=text,
                        filter_score=score, filter_reason="passed", filter_model="stub")


# --- ordering ----------------------------------------------------------------

def test_a_confident_web_source_never_outranks_a_national_guideline():
    out = ground(CHOLANGITIS_Q, _Retrieval([held(rank=2, score=0.51)]), [web(score=0.99)])
    assert [p["precedence_rank"] for p in out.passages] == [2, WEB_EVIDENCE_PRECEDENCE_RANK]
    assert out.passages[0]["origin"] == ORIGIN_HELD_CORPUS


def test_full_hierarchy_orders_by_rank_before_score():
    retrieval = _Retrieval([
        held(rank=4, score=0.95, authority=False),
        held(rank=2, score=0.55),
        held(rank=1, score=0.40),
        held(rank=3, score=0.90, authority=False),
    ])
    out = ground(CHOLANGITIS_Q, retrieval, [web(score=1.0)])
    assert [p["precedence_rank"] for p in out.passages] == [1, 2, 3, 4, 5]


def test_within_a_rank_the_better_score_leads():
    retrieval = _Retrieval([held(rank=2, score=0.60), held(rank=2, score=0.88)])
    out = ground(CHOLANGITIS_Q, retrieval)
    assert [p["retrieval_score"] for p in out.passages] == [0.88, 0.60]


def test_a_passage_with_no_rank_sorts_as_web_not_as_authority():
    stray = _Chunk({"verbatim_passage": "unranked", "retrieval_score": 0.99,
                    "carries_antimicrobial_authority": False})
    out = ground(CHOLANGITIS_Q, _Retrieval([stray, held(rank=2, score=0.3)]))
    assert out.passages[0]["precedence_rank"] == 2


def test_max_passages_is_respected():
    out = ground(CHOLANGITIS_Q, _Retrieval([held(score=0.9 - i / 100) for i in range(12)]),
                 max_passages=4)
    assert len(out.passages) == 4


# --- sufficiency -------------------------------------------------------------

def test_web_evidence_alone_cannot_ground_an_answer():
    out = ground(CHOLANGITIS_Q, None, [web(), web(url="https://cdc.gov/b")])
    assert out.sufficient_to_ground is False
    assert out.insufficiency_reason == INSUFFICIENT_NO_AUTHORITY
    assert WEB_ONLY_NOTICE in out.caveats


def test_reference_only_documents_cannot_ground_an_answer():
    out = ground(CHOLANGITIS_Q, _Retrieval([held(rank=4, authority=False)]))
    assert out.sufficient_to_ground is False
    assert out.insufficiency_reason == INSUFFICIENT_NO_AUTHORITY


def test_one_authoritative_passage_is_enough():
    out = ground(CHOLANGITIS_Q, _Retrieval([held(rank=2)]), [web()])
    assert out.sufficient_to_ground is True
    assert out.insufficiency_reason is None


def test_nothing_retrieved_is_reported_as_such():
    out = ground(CHOLANGITIS_Q, None, [])
    assert out.passages == []
    assert out.insufficiency_reason == INSUFFICIENT_EMPTY


def test_refused_retrieval_contributes_nothing():
    out = ground(CHOLANGITIS_Q, _Retrieval([held()], refused=True), [web()])
    assert out.held_count == 0
    assert out.web_count == 1
    assert out.sufficient_to_ground is False


# --- divergence is surfaced, never resolved ----------------------------------

def test_agent_named_only_by_web_is_reported_with_both_sides():
    out = ground(
        CHOLANGITIS_Q,
        _Retrieval([held(text="Ceftriaxone with metronidazole is recommended.")]),
        [web(text="Piperacillin-tazobactam should be used empirically.")],
    )
    assert out.divergences
    d = out.divergences[0]
    assert "Piperacillin-Tazobactam" in d["named_only_by_web"]
    assert "Ceftriaxone" in d["named_by_national_guidelines"]
    assert d["web_source"].startswith("Web - who.int")
    assert "NOT RESOLVED BY THIS SYSTEM" in d["resolution"]


def test_agreement_produces_no_divergence():
    out = ground(CHOLANGITIS_Q,
                 _Retrieval([held(text="Ceftriaxone with metronidazole.")]),
                 [web(text="Ceftriaxone remains a reasonable empirical choice.")])
    assert out.divergences == []


def test_no_divergence_claimed_without_an_authoritative_side():
    out = ground(CHOLANGITIS_Q,
                 _Retrieval([held(rank=4, authority=False, text="Ceftriaxone.")]),
                 [web(text="Meropenem is preferred.")])
    assert out.divergences == []


# --- the payload the composing agent receives --------------------------------

def test_prompt_block_prints_origin_and_rank_for_every_passage():
    out = ground(CHOLANGITIS_Q, _Retrieval([held()]), [web()])
    block = out.to_prompt_block()
    assert "SOURCE: ICMR" in block
    assert "SOURCE: Web - who.int" in block
    assert "WEB - NOT A GUIDELINE" in block
    assert block.count("PRECEDENCE RANK:") == 2


def test_web_caveat_travels_inside_the_block_not_beside_it():
    out = ground(CHOLANGITIS_Q, _Retrieval([held()]), [web()])
    assert "PROVENANCE UNVERIFIED" in out.to_prompt_block()


def test_fusion_declares_itself_modelless():
    out = ground(CHOLANGITIS_Q, _Retrieval([held()]))
    assert out.to_dict()["fusion_method"] == "DETERMINISTIC_PRECEDENCE_ORDER_NO_MODEL"


def test_origins_are_counted_separately():
    out = ground(CHOLANGITIS_Q, _Retrieval([held(), held(score=0.5)]), [web()])
    assert (out.held_count, out.web_count) == (2, 1)
    assert {p["origin"] for p in out.passages} == {ORIGIN_HELD_CORPUS, ORIGIN_WEB}
