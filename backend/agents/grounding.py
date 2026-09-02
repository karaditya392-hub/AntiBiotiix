"""
Agent 3 - precedence-aware grounding and fusion (Spec §8A, §9, §21, §23).

Takes what the held corpus retrieved and what the filtration agent admitted from
the web, and assembles ONE context for the composing agent.

ASSEMBLED, NOT BLENDED. "Tight coupling" in the architecture review means the two
evidence sets travel together in a single ordered payload. It does not mean they
are melted into one voice. Every passage arrives carrying its own precedence rank,
its own origin label and its own reading caveat, and it keeps all three the whole
way to the reader. The moment a reader cannot tell which sentence came from ICMR
and which came from a website, web text has silently acquired national-guideline
authority - which is the one failure in this layer that could actually change a
prescription.

THREE PROPERTIES, each deterministic and testable. No model runs in this agent:

  1. ORDER IS PRECEDENCE, THEN SCORE. Rank 1 local antibiogram, then national
     (2), then international (3), then reference-only (4), then web (5). A
     retrieval score never promotes a passage above a better-ranked one. A
     confident website does not outrank ICMR, and confidence is exactly how it
     would try.

  2. WEB ALONE CANNOT GROUND A RECOMMENDATION. If nothing in the payload carries
     antimicrobial authority, `sufficient_to_ground` is False and says which
     evidence is missing. The composing agent must refuse rather than answer from
     rank 5 - the same refusal Ask the Evidence already makes when nothing clears
     the relevance floor.

  3. DIVERGENCE IS SURFACED, NEVER RESOLVED. Where web sources name antimicrobials
     the national guidelines do not, or the reverse, the difference is reported
     with both sides named. This system does not adjudicate between ICMR and NCDC,
     two national authorities; it certainly does not let a website overrule either.
     What is computed is objective - which agents each side's text NAMES - exactly
     as backend.guidelines.cross_source computes it. Whether a naming difference
     amounts to a clinical conflict is a clinical judgement and stays with the
     reader.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.agents.provenance import ORIGIN_WEB, mark_held, source_label
from backend.config import WEB_EVIDENCE_PRECEDENCE_RANK
from backend.guidelines.cross_source import _formulary_terms, _named_drugs
from backend.guidelines.knowledge_base import knowledge_base

INSUFFICIENT_NO_AUTHORITY = (
    "No passage in this evidence set carries antimicrobial authority. Web sources and "
    "reference-only documents cannot ground an antimicrobial recommendation between "
    "them. Answer that the held guidelines do not cover this question rather than "
    "composing from what remains."
)

INSUFFICIENT_EMPTY = "No evidence was retrieved or admitted. There is nothing to ground an answer on."

WEB_ONLY_NOTICE = (
    "Every passage below rank 4 in this set is web-sourced. It may be reported as web "
    "context, attributed to its site, and must not be presented as guidance."
)


@dataclass
class GroundedContext:
    question: str
    passages: List[Dict[str, Any]] = field(default_factory=list)
    sufficient_to_ground: bool = False
    insufficiency_reason: Optional[str] = None
    divergences: List[Dict[str, Any]] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    @property
    def held_count(self) -> int:
        return sum(1 for p in self.passages if p.get("origin") != ORIGIN_WEB)

    @property
    def web_count(self) -> int:
        return sum(1 for p in self.passages if p.get("origin") == ORIGIN_WEB)

    def to_prompt_block(self) -> str:
        """
        The context as the composing agent receives it.

        Each passage is preceded by its origin and, where one exists, its reading
        caveat - inside the block, not alongside it. A caveat carried in a sibling
        field is a caveat a prompt assembler will eventually drop, and the passage
        would then be read as ordinary evidence.
        """
        lines: List[str] = []
        for i, p in enumerate(self.passages, 1):
            lines.append(f"[{i}] SOURCE: {source_label(p)}")
            lines.append(f"    PRECEDENCE RANK: {p.get('precedence_rank')}"
                         f"{'  (WEB - NOT A GUIDELINE)' if p.get('origin') == ORIGIN_WEB else ''}")
            if p.get("domain_caveat"):
                lines.append(f"    READ AS: {p['domain_caveat']}")
            lines.append(f"    PASSAGE: {p.get('verbatim_passage', '').strip()}")
            lines.append("")
        return "\n".join(lines).strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "passages": self.passages,
            "passage_count": len(self.passages),
            "held_corpus_passages": self.held_count,
            "web_passages": self.web_count,
            "sufficient_to_ground": self.sufficient_to_ground,
            "insufficiency_reason": self.insufficiency_reason,
            "divergences": self.divergences,
            "caveats": self.caveats,
            "fusion_method": "DETERMINISTIC_PRECEDENCE_ORDER_NO_MODEL",
        }


def _sort_key(passage: Dict[str, Any]):
    """
    Precedence first, retrieval score second.

    Rank ascending (1 is strongest), score descending within a rank. A missing rank
    sorts to the web rank rather than to the top: a passage that failed to record
    what it is must never be treated as if it were authoritative.
    """
    rank = passage.get("precedence_rank")
    if not isinstance(rank, int):
        rank = WEB_EVIDENCE_PRECEDENCE_RANK
    try:
        score = float(passage.get("retrieval_score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    return (rank, -score)


def _divergences(held: List[Dict[str, Any]], web: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Antimicrobials named on one side and not the other.

    A fact about the text, not a clinical finding, and the returned record says so
    in the words the reader sees.
    """
    if not held or not web:
        return []

    terms = _formulary_terms(knowledge_base)
    authoritative = [p for p in held if p.get("carries_antimicrobial_authority")]
    if not authoritative:
        return []

    held_named = set()
    for p in authoritative:
        held_named.update(_named_drugs(p.get("verbatim_passage", ""), terms))

    out: List[Dict[str, Any]] = []
    for p in web:
        web_named = set(_named_drugs(p.get("verbatim_passage", ""), terms))
        only_web = sorted(web_named - held_named)
        if not only_web:
            continue
        out.append({
            "web_source": source_label(p),
            "web_url": p.get("source_url"),
            "named_only_by_web": only_web,
            "named_by_national_guidelines": sorted(held_named),
            "finding": (
                f"{source_label(p)} names {', '.join(only_web)}, which the retrieved national "
                "guideline passages do not name for this question."
            ),
            "resolution": (
                "NOT RESOLVED BY THIS SYSTEM. A difference in named agents is a fact about "
                "the text, not a clinical conflict. The national guidelines and the local "
                "antibiogram govern antimicrobial choice; a web source never overrides them. "
                "Whether this difference matters clinically is the reader's judgement."
            ),
        })
    return out


def ground(
    question: str,
    retrieval_result: Any = None,
    web_citations: Optional[List[Dict[str, Any]]] = None,
    max_passages: int = 8,
) -> GroundedContext:
    """
    Fuse held-corpus retrieval with filtered web evidence.

    `retrieval_result` is a backend.rag.retrieve.RetrievalResult, or None when
    retrieval refused. `web_citations` are the citations Agent 2 ACCEPTED - this
    agent never sees a rejected result, and has no route to admit one.
    """
    held: List[Dict[str, Any]] = []
    caveats: List[str] = []

    if retrieval_result is not None and not getattr(retrieval_result, "refused", False):
        held = [mark_held(c.to_citation()) for c in getattr(retrieval_result, "chunks", [])]
        # Carried through rather than recomputed: the evidence and the warning about
        # the evidence must not be able to drift apart.
        caveats.extend(retrieval_result.caveats())

    web = list(web_citations or [])
    for p in web:
        # Defensive, not decorative. A citation that reached here without its rank
        # would sort as authoritative, so the rank is asserted rather than assumed.
        p.setdefault("precedence_rank", WEB_EVIDENCE_PRECEDENCE_RANK)

    merged = sorted(held + web, key=_sort_key)[:max_passages]

    context = GroundedContext(question=question, passages=merged, caveats=caveats)

    if not merged:
        context.insufficiency_reason = INSUFFICIENT_EMPTY
        return context

    has_authority = any(p.get("carries_antimicrobial_authority") for p in merged)
    if not has_authority:
        context.insufficiency_reason = INSUFFICIENT_NO_AUTHORITY
    else:
        context.sufficient_to_ground = True

    if context.web_count and not context.held_count:
        context.caveats.append(WEB_ONLY_NOTICE)

    context.divergences = _divergences(held, [p for p in merged if p.get("origin") == ORIGIN_WEB])
    return context
