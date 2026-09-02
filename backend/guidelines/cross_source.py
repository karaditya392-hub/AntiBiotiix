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

from backend.config import (
    ANTIMICROBIAL_CONTENT_DOCUMENT_IDS,
    GUIDELINE_PRECEDENCE_HIERARCHY,
)
from backend.rag.store import (
    DOMAIN_ANTIMICROBIAL,
    DOMAIN_READING_CONTRACT,
    NOT_A_CLINICAL_GUIDELINE_RANK,
)

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
# ABSOLUTE is set above backend.rag.retrieve.RELEVANCE_FLOOR (0.45). That floor
# governs "is anything in the corpus relevant"; this is the stronger per-document
# claim that THIS source addresses the topic, and deserves a higher bar.
#
# RELATIVE then keeps only documents close to the best match, which is what
# actually separates the sources genuinely covering a syndrome from the tail that
# merely share vocabulary with it.
#
# BOTH RECALIBRATED for the 39-document corpus (were 0.45 / 0.85 at 11 documents).
# The relative gate was the binding constraint and it had started excluding
# national guidelines that plainly cover the topic: with more documents competing,
# the best score is often set by whichever source happens to phrase things closest,
# and NCDC-NTG-AMR-2016 -- a national antimicrobial guideline with a chapter on the
# syndrome being asked about -- fell 0.003 short on community acquired pneumonia
# and 0.0006 short on UTI. Measured over 11 syndrome topics:
#
#   relative   NCDC shown   avg sources shown   off-scope sources admitted
#   0.85        4 / 11            2.8                   0
#   0.82        7 / 11            3.6                   0
#   0.80        8 / 11            3.8                   0
#   0.78        8 / 11            4.3                   0
#
# 0.80 buys the coverage without admitting anything off-scope: no dry eye,
# osteoarthritis, hypertension, alcohol, Ayurvedic or public-information document
# appeared on any infection topic at any setting tested. The absolute bar moves to
# 0.50 to stay above the raised retrieval floor and keep that relationship intact.
#
# ---------------------------------------------------------------------------
# RE-MEASURED 02-09-2026 for nvidia/nemotron-3-embed-1b, which replaced
# all-MiniLM-L6-v2 as the retrieval model. Same method, 11 syndrome topics,
# scripts/calibrate_cross_source_gates.py:
#
#   absolute  relative   NCDC shown   avg sources shown
#     0.50      0.80        4 / 11           2.0          <- the old value
#     0.40      0.80        7 / 11           3.1
#     0.35      0.80        7 / 11           3.1
#     0.30      0.80        7 / 11           3.1
#
# THE ABSOLUTE BAR HAD TO MOVE FOR THE SAME REASON THE RETRIEVAL FLOOR DID: it is
# a measurement of one model's score distribution, not a constant. At 0.50 on this
# index, NCDC-NTG-AMR-2016 misses community acquired pneumonia by 0.002 -- the
# identical failure this gate was lowered to 0.80 relative to fix in the first
# place, reappearing through the other threshold.
#
# 0.40 is chosen as the HIGHEST absolute bar that buys the full coverage available:
# NCDC coverage saturates at 7/11 and does not improve at 0.35 or 0.30, so nothing
# is gained by going lower and the stronger per-document claim is preserved. The
# relative gate is now the binding constraint, which is why it is unchanged.
#
# ONE ADMISSION IS NOT OFF-SCOPE BUT IS WORTH NAMING: ICMR-T1DM-2022 surfaces on
# skin and soft tissue infection (0.5587) and, at 0.40, on urinary tract infection
# (0.4602). It is admitted at the OLD setting too, so this is not a consequence of
# the change. Diabetes guidance genuinely discusses foot infection and UTI, and the
# passage arrives carrying its CLINICAL_CONDITION_SPECIFIC domain caveat, which
# says in as many words that it does not govern antimicrobial choice.
# ---------------------------------------------------------------------------
MIN_SCORE_ABSOLUTE = 0.40
MIN_SCORE_RELATIVE = 0.80


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
        rank = doc.get("precedence_rank")
        domain = doc.get("clinical_domain", DOMAIN_ANTIMICROBIAL)
        is_guideline = rank != NOT_A_CLINICAL_GUIDELINE_RANK
        base = {
            "document_id": doc_id,
            "title": doc.get("title"),
            "version": doc.get("version"),
            "precedence_rank": rank,
            "source_type": doc.get("source_type", "OFFICIAL_PDF"),
            "provenance_basis": doc.get("provenance_basis", "HASH_VERIFIED_PDF"),
            # A reader comparing sources side by side has to be able to see, without
            # opening the provenance note, that one of these columns is a public
            # information sheet rather than a guideline.
            "is_clinical_guideline": is_guideline,
            "clinical_domain": domain,
            # Shown per column because the side-by-side layout is exactly where a
            # reader infers that everything on screen is comparable evidence.
            "carries_antimicrobial_authority": is_guideline and domain == DOMAIN_ANTIMICROBIAL,
            "carries_antimicrobial_content": doc_id in ANTIMICROBIAL_CONTENT_DOCUMENT_IDS,
            "domain_caveat": DOMAIN_READING_CONTRACT.get(domain),
            "clinical_standing": (
                None if is_guideline else
                "Held for reference only - not a clinical guideline and never a basis "
                "for a prescribing or antimicrobial decision."
            ),
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

    # Agent differences are computed across documents that CARRY ANTIBACTERIAL
    # RECOMMENDATIONS only. A public information sheet or a community programme
    # leaflet not naming ceftriaxone is not a guideline declining to recommend it,
    # and letting rank-4 documents into this set would report an absence of authority
    # as a difference of opinion.
    #
    # The same argument reaches further than rank 4, and the ICMR national corpus is
    # what made that visible. An ICMR cancer consensus document is a clinical
    # guideline at rank 2, so the old `is_clinical_guideline` filter admitted it --
    # and a gallbladder cancer document that does not mention piperacillin would have
    # been counted as a national guideline omitting it, on an intra-abdominal topic it
    # was never about. Twenty-two such documents joined the corpus at once, which
    # would have turned a genuine two-source comparison into a manufactured
    # twenty-three-source disagreement.
    #
    # The filter is the explicit set in config rather than the domain, because domain
    # alone is too coarse in the other direction: it would drop NCDC-LEPTOSPIROSIS-2015
    # from a leptospirosis comparison, which is the one source that actually covers it.
    # Everything else is still shown as a column above; it just does not vote here.
    comparable = [
        d for d in with_guidance
        if d["document_id"] in ANTIMICROBIAL_CONTENT_DOCUMENT_IDS
    ]
    all_named = sorted({drug for d in comparable for drug in d["named_drugs"]})

    # Objective, checkable difference: which on-topic documents name each agent,
    # and which on-topic documents do not.
    #
    # Only computed when at least two documents actually cover the topic. With one
    # source there is nothing to compare, and reporting "named by 1, not named by
    # 10" across documents that were never about this syndrome would manufacture
    # disagreement out of scope differences.
    divergent: List[Dict[str, Any]] = []
    if len(comparable) >= 2:
        for drug in all_named:
            names_it = [d["document_id"] for d in comparable if drug in d["named_drugs"]]
            omits_it = [d["document_id"] for d in comparable if drug not in d["named_drugs"]]
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
        "documents_compared_for_agent_differences": len(comparable),
        "documents_shown_but_not_compared": [
            d["document_id"] for d in with_guidance
            if not d.get("carries_antimicrobial_content", True)
        ],
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
            "Clinical interpretation remains with the reader. Only documents that carry "
            "antibacterial recommendations are compared for agent differences; any other "
            "document that matched this topic is shown as a column, carries its own domain "
            "caveat, and is listed under documents_shown_but_not_compared."
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
