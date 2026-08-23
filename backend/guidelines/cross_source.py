"""
Cross-source comparison across the ingested guideline corpus.

WHAT THIS DOES AND DOES NOT CLAIM
---------------------------------
It retrieves what EACH held document says about a topic and lays the passages
side by side, ordered by the documented precedence hierarchy.

It does NOT decide that sources disagree. Judging whether two pieces of clinical
guidance genuinely conflict is a clinical judgement, and asserting one from a
similarity score would be exactly the kind of unfounded claim the rest of this
system refuses to make. What it computes instead is objective and checkable:
which antimicrobials from the formulary each document names for the topic, and
where those sets differ. A difference in named agents is a fact about the text.
Whether it amounts to a clinical conflict is left to the reader.

Curated conflicts that HAVE been reviewed are surfaced separately, and labelled
as curated so they are never confused with the computed set differences.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from backend.config import GUIDELINE_PRECEDENCE_HIERARCHY

# Passages per document. Small on purpose: this is a reading aid, not a dump.
PASSAGES_PER_DOCUMENT = 3

# Relevance gating.
#
# Two thresholds, because one is not enough. Semantic search always returns its
# nearest neighbours, so on a UTI query the tuberculosis document still surfaces
# its closest passage. Reporting that as "this document's guidance on UTI" would
# be actively misleading -- it would make a TB guideline look as though it had
# opinions about nitrofurantoin.
#
# ABSOLUTE is set above backend.rag.retrieve.RELEVANCE_FLOOR (0.35). That floor
# governs "is anything in the corpus relevant"; this is the stronger per-document
# claim that THIS source addresses the topic, and deserves a higher bar.
#
# RELATIVE then keeps only documents close to the best match, which is what
# actually separates the two or three sources genuinely covering a syndrome from
# the tail that merely share vocabulary with it.
MIN_SCORE_ABSOLUTE = 0.45
MIN_SCORE_RELATIVE = 0.85


def _formulary_terms(knowledge_base) -> Dict[str, str]:
    """Map a lowercase drug token -> canonical display name, from the formulary."""
    terms: Dict[str, str] = {}
    for key, info in knowledge_base.drugs_db.items():
        name = info.get("name") or key
        terms[key.replace("_", " ").lower()] = name
        terms[str(name).lower()] = name
        # The corpus spells several agents differently from the formulary key.
        for variant in (
            str(name).replace("-", " ").lower(),
            str(name).replace("-", "+").lower(),
            key.split("_")[0].lower(),
        ):
            terms.setdefault(variant, name)
    return terms


def _named_drugs(text: str, terms: Dict[str, str]) -> List[str]:
    """Antimicrobials from the formulary that this passage actually names."""
    lowered = text.lower()
    found = set()
    for term, canonical in terms.items():
        if len(term) < 5:
            continue
        if re.search(r"\b" + re.escape(term) + r"\b", lowered):
            found.add(canonical)
    return sorted(found)


def compare_sources(
    topic: str,
    knowledge_base,
    vector_store,
    k_per_document: int = PASSAGES_PER_DOCUMENT,
) -> Dict[str, Any]:
    """
    Retrieve `topic` from every ingested document and report them side by side.
    """
    topic = (topic or "").strip()
    if not topic:
        return {
            "topic": "",
            "available": False,
            "message": "Enter a syndrome or therapy topic to compare across sources.",
            "documents": [],
        }

    if not getattr(vector_store, "available", False):
        return {
            "topic": topic,
            "available": False,
            "message": "The guideline corpus is not loaded, so no comparison can be made.",
            "documents": [],
        }

    terms = _formulary_terms(knowledge_base)

    # First pass: best match per document, so the relative threshold has a
    # corpus-wide reference point before anything is judged relevant.
    raw: Dict[str, List] = {}
    for doc_id in vector_store.docs:
        raw[doc_id] = vector_store.search(topic, k=k_per_document, document_ids=[doc_id])

    best_overall = max(
        (hits[0].score for hits in raw.values() if hits),
        default=0.0,
    )
    threshold = max(MIN_SCORE_ABSOLUTE, best_overall * MIN_SCORE_RELATIVE)

    documents: List[Dict[str, Any]] = []
    for doc_id, doc in vector_store.docs.items():
        hits = [h for h in raw.get(doc_id, []) if h.score >= threshold]
        base = {
            "document_id": doc_id,
            "title": doc.get("title"),
            "version": doc.get("version"),
            "precedence_rank": doc.get("precedence_rank"),
            "source_type": doc.get("source_type", "OFFICIAL_PDF"),
            "provenance_basis": doc.get("provenance_basis", "HASH_VERIFIED_PDF"),
        }

        if not hits:
            # Silence is informative, and reported as silence rather than as a
            # weak answer dressed up as guidance.
            nearest = raw.get(doc_id) or []
            documents.append({
                **base,
                "has_guidance": False,
                "reason": "No passage in this document cleared the relevance threshold for this topic.",
                "nearest_score": round(float(nearest[0].score), 4) if nearest else None,
                "passages": [],
                "named_drugs": [],
            })
            continue

        named: List[str] = []
        for h in hits:
            for drug in _named_drugs(h.text, terms):
                if drug not in named:
                    named.append(drug)

        documents.append({
            **base,
            "has_guidance": True,
            "top_score": round(float(hits[0].score), 4),
            "passages": [h.to_citation() for h in hits],
            "named_drugs": sorted(named),
        })

    # Order by precedence, then by how strongly the document matched.
    documents.sort(key=lambda d: (d.get("precedence_rank") or 99, -(d.get("top_score") or 0)))

    with_guidance = [d for d in documents if d["has_guidance"]]
    all_named = sorted({drug for d in with_guidance for drug in d["named_drugs"]})

    # Objective, checkable difference: which on-topic documents name each agent,
    # and which on-topic documents do not.
    #
    # Only computed when at least two documents actually cover the topic. With one
    # source there is nothing to compare, and reporting "named by 1, not named by
    # 10" across documents that were never about this syndrome would manufacture
    # disagreement out of scope differences.
    divergent: List[Dict[str, Any]] = []
    if len(with_guidance) >= 2:
        for drug in all_named:
            names_it = [d["document_id"] for d in with_guidance if drug in d["named_drugs"]]
            omits_it = [d["document_id"] for d in with_guidance if drug not in d["named_drugs"]]
            if names_it and omits_it:
                divergent.append({
                    "drug": drug,
                    "named_by": names_it,
                    "not_named_by": omits_it,
                })

    return {
        "topic": topic,
        "available": True,
        "documents_searched": len(documents),
        "documents_with_guidance": len(with_guidance),
        "precedence_hierarchy": GUIDELINE_PRECEDENCE_HIERARCHY,
        "agents_named_anywhere": all_named,
        "differing_agents": divergent,
        "curated_conflict": _curated_conflict(topic, knowledge_base),
        "interpretation_note": (
            "Passages are what each held document says about this topic, ordered by the "
            "documented precedence hierarchy. Differences in the agents named are computed "
            "by matching formulary drug names against the retrieved text: they are a fact "
            "about the wording, NOT a finding that the sources clinically conflict. A "
            "document may omit an agent because it is out of that document's scope. "
            "Clinical interpretation remains with the reader."
        ),
        "documents": documents,
    }


def _curated_conflict(topic: str, knowledge_base) -> Optional[Dict[str, Any]]:
    """
    Conflicts that have been reviewed and written down, as opposed to computed.

    Kept separate from the set differences above so a curated clinical finding is
    never presented as though the system derived it.
    """
    resolved = knowledge_base.resolve_guideline_precedence(topic)
    conflict = resolved.get("conflict_surfaced")
    if not conflict:
        return None
    return {"origin": "CURATED_AND_REVIEWED", **conflict}
