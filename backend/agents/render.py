"""
The render contract: one stable JSON shape for everything the search pipeline
produces.

WHY THIS IS A SEPARATE, DETERMINISTIC STEP RATHER THAN MORE PROMPT.

The composing agent already asks a model for JSON, and that JSON is already
validated. But what a model returns is `{"summary", "points", ...}` -- an answer,
not a view. A client rendering it still has to reach into the grounded context for
precedence ranks, into the filtration result for rejections, and into the
retrieval result for caveats, and decide for itself how to display a rank-5 web
passage differently from a rank-2 national guideline.

Every client that does that gets it slightly wrong, and the way it gets it wrong
is always the same: the origin label is the first thing dropped when a layout is
tight. A web passage rendered without its origin has silently acquired national-
guideline authority, which is the one failure in this layer that could change a
prescription.

So the shape is assembled HERE, once, deterministically, from data that already
exists. No model runs in this module. Each section arrives with its own display
tier already decided, each citation with its origin already printed, and a client
renders what it is given rather than deriving what to show.

`SCHEMA_VERSION` is on every payload so a client can tell what it is reading.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.agents.compose import ComposedAnswer, MODE_COMPOSED, MODE_EXTRACTIVE, MODE_REFUSED
from backend.agents.grounding import GroundedContext
from backend.agents.provenance import ORIGIN_WEB, source_label
from backend.config import WEB_EVIDENCE_PRECEDENCE_RANK

SCHEMA_VERSION = "antibiotix.search.render/1"

# How a passage of each precedence rank is to be displayed. The tier is decided
# here rather than by a stylesheet, because "which of these two paragraphs is a
# national guideline" is a clinical distinction, not a visual preference.
TIER_BY_RANK = {
    1: {"tier": "LOCAL_AUTHORITY", "label": "Local institutional data",
        "weight": "Outranks national guidance for this institution."},
    2: {"tier": "NATIONAL_AUTHORITY", "label": "National guideline",
        "weight": "National antimicrobial or clinical authority."},
    3: {"tier": "INTERNATIONAL_AUTHORITY", "label": "International guideline",
        "weight": "International guidance; national guidance governs where they differ."},
    4: {"tier": "REFERENCE_ONLY", "label": "Reference only — not a clinical guideline",
        "weight": "Carries no clinical authority. Never a basis for a prescribing decision."},
    WEB_EVIDENCE_PRECEDENCE_RANK: {
        "tier": "WEB_UNVERIFIED", "label": "Web source — unverified provenance",
        "weight": "Retrieved live and filtered. Never sufficient alone and never outranks a guideline."},
}

MODE_DESCRIPTION = {
    MODE_COMPOSED: "Composed by a model from the passages below, then checked against them.",
    MODE_EXTRACTIVE: "The retrieved passages themselves, verbatim. No model wrote this text.",
    MODE_REFUSED: "Refused: the evidence retrieved cannot ground an answer to this question.",
}


def _tier(rank: Any) -> Dict[str, str]:
    if not isinstance(rank, int):
        rank = WEB_EVIDENCE_PRECEDENCE_RANK
    return TIER_BY_RANK.get(rank, TIER_BY_RANK[WEB_EVIDENCE_PRECEDENCE_RANK])


def _citation(index: int, passage: Dict[str, Any]) -> Dict[str, Any]:
    """
    One citation, carrying everything needed to display it and nothing that has to
    be looked up elsewhere.
    """
    is_web = passage.get("origin") == ORIGIN_WEB
    tier = _tier(passage.get("precedence_rank"))
    return {
        "index": index,
        "source_label": source_label(passage),
        "document_title": passage.get("document_title"),
        "issuing_org": passage.get("issuing_org"),
        "version": passage.get("guideline_version"),
        "location": passage.get("section_page"),
        "source_url": passage.get("source_url") or None,
        "passage": passage.get("verbatim_passage", ""),
        "origin": passage.get("origin"),
        "is_web_source": is_web,
        "precedence_rank": passage.get("precedence_rank"),
        "tier": tier["tier"],
        "tier_label": tier["label"],
        "authority_note": tier["weight"],
        "carries_antimicrobial_authority": bool(passage.get("carries_antimicrobial_authority")),
        "retrieval_score": passage.get("retrieval_score"),
        "reading_caveat": passage.get("domain_caveat") or passage.get("clinical_standing"),
        # Web-only, and null rather than absent on held citations so a client reads
        # one shape and never branches on key presence.
        "filter_score": passage.get("filter_score"),
        "filter_reason": passage.get("filter_reason"),
        "filter_model": passage.get("filter_model"),
        "retrieved_at": passage.get("retrieved_at"),
    }


def _evidence_groups(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Citations grouped by display tier, strongest first.

    Grouped rather than left flat because a flat list renders as a list of equals,
    and these are not equals. The group header is where a reader learns that the
    next three passages carry no clinical authority.
    """
    order: List[str] = []
    buckets: Dict[str, Dict[str, Any]] = {}
    for citation in citations:
        key = citation["tier"]
        if key not in buckets:
            order.append(key)
            buckets[key] = {
                "tier": key,
                "label": citation["tier_label"],
                "authority_note": citation["authority_note"],
                "precedence_rank": citation["precedence_rank"],
                "citation_indexes": [],
            }
        buckets[key]["citation_indexes"].append(citation["index"])
    return [buckets[k] for k in order]


def _filtration_block(filtration: Any) -> Optional[Dict[str, Any]]:
    """
    What the web filter accepted AND what it rejected.

    The rejections are rendered, not logged. A filter whose refusals are invisible
    cannot be reviewed, and one nobody reviews is indistinguishable from no filter
    at all -- so they arrive in the render payload as first-class content.
    """
    if filtration is None:
        return None
    raw = filtration.to_dict()
    return {
        "ran": True,
        "accepted_count": raw["accepted_count"],
        "rejected_count": raw["rejected_count"],
        "acceptance_threshold": raw["acceptance_threshold"],
        "model": raw["filter_model"],
        "degraded_no_model": raw["degraded_no_model"],
        "verdicts": [
            {
                "url": v["url"],
                "site": v["site"],
                "accepted": v["accepted"],
                "score": v["score"],
                "reason": v["reason"],
                "recognised_authority": v["recognised_authority"],
                "assessed_by_model": v["assessed_by_model"],
            }
            for v in raw["verdicts"]
        ],
    }


def build(
    *,
    question: str,
    answer: ComposedAnswer,
    context: GroundedContext,
    filtration: Any = None,
    retrieval: Any = None,
    web_path_active: bool = False,
    web_skipped_reason: Optional[str] = None,
    trace: Any = None,
) -> Dict[str, Any]:
    """
    Assemble the render payload. Deterministic; no model runs here.
    """
    citations = [_citation(i + 1, p) for i, p in enumerate(answer.citations)]
    held = [c for c in citations if not c["is_web_source"]]
    web = [c for c in citations if c["is_web_source"]]

    sections: List[Dict[str, Any]] = []
    if answer.summary:
        sections.append({"kind": "SUMMARY", "title": "Summary", "text": answer.summary,
                         "citation_indexes": sorted({
                             i for i in range(1, len(citations) + 1)
                             if f"[{i}]" in answer.summary
                         })})
    if answer.points:
        sections.append({
            "kind": "FINDINGS",
            "title": "What the evidence says" if answer.mode == MODE_COMPOSED
                     else "Retrieved passages, verbatim",
            "items": [
                {
                    "text": str(p.get("text", "")),
                    "citation_indexes": [
                        int(i) for i in (p.get("citation_indexes") or [])
                        if str(i).isdigit() and 1 <= int(i) <= len(citations)
                    ],
                    "source": p.get("source"),
                }
                for p in answer.points
            ],
        })
    if answer.divergences:
        sections.append({
            "kind": "DIVERGENCE",
            "title": "Where the sources differ",
            "note": "Reported, never resolved. A difference in named agents is a fact about "
                    "the text, not a clinical conflict.",
            "items": answer.divergences,
        })
    if answer.caveats:
        sections.append({"kind": "CAVEATS", "title": "Read this before using the above",
                         "items": answer.caveats})

    return {
        "schema": SCHEMA_VERSION,
        "question": question,
        "answered": answer.answered,
        "answer_mode": answer.mode,
        "answer_mode_description": MODE_DESCRIPTION.get(answer.mode, ""),
        "model": answer.model,
        "composition_rejected_because": answer.rejection,
        "sections": sections,
        "citations": citations,
        "evidence_groups": _evidence_groups(citations),
        "evidence": {
            "total": len(citations),
            "from_vector_db": len(held),
            "from_web": len(web),
            "sufficient_to_ground": context.sufficient_to_ground,
            "insufficiency_reason": context.insufficiency_reason,
            "carries_antimicrobial_authority": any(
                c["carries_antimicrobial_authority"] for c in citations
            ),
        },
        "sources": {
            "vector_db": {
                "ran": retrieval is not None,
                "refused": bool(getattr(retrieval, "refused", False)) if retrieval else None,
                "reason": getattr(retrieval, "reason", None) if retrieval else None,
                "passages": len(held),
                "relevance_floor": getattr(retrieval, "floor", None) if retrieval else None,
                "best_score": getattr(retrieval, "best_score", None) if retrieval else None,
            },
            "web": {
                "ran": web_path_active,
                "skipped_reason": web_skipped_reason,
                "passages": len(web),
                "filtration": _filtration_block(filtration),
            },
        },
        "disclaimer": answer.to_dict()["disclaimer"],
        "trace": trace.to_dict() if trace is not None else None,
    }
