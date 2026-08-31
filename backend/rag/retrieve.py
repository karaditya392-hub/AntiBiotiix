"""
Guideline retrieval with a hard relevance floor (Spec §9, §16, §23).

THE MOST IMPORTANT BEHAVIOUR IN THIS MODULE: when nothing clears the relevance
threshold, retrieval returns the refusal string. It never returns the best of a
bad set. A weak citation presented to a clinician as guideline evidence is worse
than an explicit "no evidence retrieved".

Retrieval AUGMENTS evidence. It must never gate whether a clinical rule fires:
the rule engine does not import this module, and every warning that fires today
still fires with the vector store empty, misaligned, or offline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.rag.store import RetrievalBackendMismatch, RetrievedChunk, vector_store

NO_EVIDENCE = "No sufficiently relevant evidence was retrieved."

# Cosine similarity floor. Below this, a chunk is not offered as evidence.
#
# RECALIBRATED for the 39-document corpus (was 0.35, calibrated when 11 documents
# were held). Measured over 24 legitimate and 15 off-domain queries:
#
#   lowest legitimate  0.522  ("nitrofurantoin renal impairment")
#   highest off-domain 0.341  ("how to train a puppy" -> NLEP-DPMR-2012)
#
# The old 0.35 sat 0.009 above the highest off-domain score. That margin was
# 0.219 on the smaller corpus and the expansion consumed it: a food composition
# table in the burns document, rehabilitation training language in the leprosy
# guideline and cost discussion in the hypertension guideline all raise the score
# of ordinary English that has nothing to do with any of them. 0.45 sits in the
# middle of the measured gap, rejecting every off-domain query with room to spare
# while keeping every legitimate one.
#
# Invented drug names still score high (0.62 for "flurbamycin dosing in adults"):
# a nonsense name in a well-formed dosing question matches on sentence FORM, not
# content, and no threshold separates those. They are caught before scoring by
# unknown_entities() below. Neither check alone is sufficient.
RELEVANCE_FLOOR = 0.45

# Floor for the LEXICAL fallback, used when this machine could not load the
# semantic model and the corpus was re-embedded with TF-IDF.
#
# It needs its own number because the two backends score on different scales:
# applying the semantic floor to TF-IDF rejected every genuine question, which is
# how a working corpus came to answer "no sufficiently relevant evidence" on a
# machine without the model cached.
#
# THE TWO CLASSES NOW OVERLAP HERE, and the floor can no longer separate them.
# Measured over the 39-document corpus, counting only queries that survive
# unknown_entities() and therefore actually reach the floor:
#
#   lowest legitimate   0.156  ("vancomycin monitoring")
#   highest off-domain  0.209  ("how to invest in mutual funds"
#                               -> MOHFW-STG-HYPERTENSION-2016, on its cost text)
#
# The off-domain maximum is now ABOVE the legitimate minimum, so no threshold
# admits every real question while rejecting every off-domain one. A term-overlap
# guard was measured too and does not separate them either ("how do I change a
# bicycle tyre" matches 2 of 3 terms; "fever in neutropenic patient" matches 1 of 3).
#
# 0.17 is therefore chosen as the best available compromise rather than a clean
# separator: it rejects three of the five off-domain queries that reach it, keeps
# 16 of 18 legitimate ones, and leaves the residual failure visible instead of
# hidden -- see LEXICAL_OVERLAP_CAVEAT, which every degraded-mode response carries.
LEXICAL_RELEVANCE_FLOOR = 0.17

# Attached to every result produced by the lexical fallback, because on this corpus
# a passage clearing the lexical floor is evidence of shared WORDING, not evidence
# that the corpus addresses the question.
LEXICAL_OVERLAP_CAVEAT = (
    "Retrieval on this machine is LEXICAL, not semantic. On the current corpus the "
    "lexical scores of genuine clinical questions and of off-domain questions overlap, "
    "so a returned passage means the corpus contains similar WORDING, not that it "
    "addresses this question. Read every passage below against the question before "
    "relying on it, and install the semantic model to restore reliable retrieval."
)


def active_floor() -> float:
    """
    The floor appropriate to the backend actually answering queries here.

    Passed explicitly rather than read inside retrieve() so a caller can still
    override it, and so the chosen value appears in the response.
    """
    return RELEVANCE_FLOOR if vector_store.is_semantic else LEXICAL_RELEVANCE_FLOOR

# Query tokens at least this long are treated as specific entity names
# (drug names, organisms, syndromes) rather than ordinary English.
_ENTITY_MIN_LEN = 6

_COMMON = {
    "about", "against", "antibiotic", "antibiotics", "antimicrobial", "adult",
    "adults", "before", "between", "children", "clinical", "different",
    "dosing", "during", "guideline", "guidelines", "indication",
    "indications", "infection", "infections", "patient", "patients",
    "recommend", "recommended", "should", "therapy", "treatment", "treating",
    "which", "within", "without",
}


def unknown_entities(query: str) -> List[str]:
    """
    Return query tokens that look like specific entity names but appear nowhere
    in the ingested corpus.

    A query naming a drug the corpus has never seen cannot be answered from that
    corpus, however similar its sentence shape is to a real dosing question.
    This is the check that rejects "zzzzmycin 500mg indications" while accepting
    "nitrofurantoin renal impairment".
    """
    import re

    vocab = vector_store.vocabulary
    if not vocab:
        return []
    prefixes = getattr(vector_store, "vocab_prefixes", set())
    out = []
    for tok in re.findall(r"[A-Za-z]{%d,}" % _ENTITY_MIN_LEN, query.lower()):
        if tok in _COMMON or tok in vocab:
            continue
        # Grounded if the token is an inflection of a corpus word, or a corpus
        # word is an inflection of it. Matching bidirectionally on a 5-character
        # stem keeps "renally"/"renal" and "contraindication"/"contraindications"
        # grounded while leaving invented names such as "zzzzmycin" unmatched.
        if tok in prefixes:
            continue
        if any(tok[:n] in vocab for n in range(5, len(tok))):
            continue
        out.append(tok)
    return out


@dataclass
class RetrievalResult:
    query: str
    chunks: List[RetrievedChunk]
    refused: bool
    reason: Optional[str]
    floor: float
    best_score: Optional[float]

    @property
    def non_clinical_sources(self) -> List[str]:
        """Retrieved documents that are held for reference but are not guidelines."""
        seen = []
        for c in self.chunks:
            if not c.is_clinical_guideline and c.document_id not in seen:
                seen.append(c.document_id)
        return seen

    def caveats(self) -> List[str]:
        """
        Everything a reader must know before using these passages.

        Collected here rather than left implicit in the store description, because a
        caveat the caller has to reconstruct from three separate fields is a caveat
        that will not reach the clinician.
        """
        out: List[str] = []
        if not vector_store.is_semantic:
            out.append(LEXICAL_OVERLAP_CAVEAT)
        if self.non_clinical_sources:
            out.append(
                "One or more passages come from documents held for reference only and "
                "not as clinical guidelines: "
                + ", ".join(self.non_clinical_sources)
                + ". They carry no clinical authority and are never a basis for a "
                "prescribing or antimicrobial decision."
            )
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "retrieved": [c.to_citation() for c in self.chunks],
            "count": len(self.chunks),
            "refused": self.refused,
            "message": self.reason,
            "relevance_floor": self.floor,
            "best_score": round(self.best_score, 4) if self.best_score is not None else None,
            "store": vector_store.backend_description(),
            "non_clinical_sources": self.non_clinical_sources,
            "caveats": self.caveats(),
        }


def retrieve(
    query: str,
    k: int = 5,
    document_ids: Optional[List[str]] = None,
    floor: Optional[float] = None,
) -> RetrievalResult:
    # None means "whichever floor suits the backend actually in use", so a machine
    # running the lexical fallback is not judged against a semantic threshold.
    if floor is None:
        floor = active_floor()
    q = (query or "").strip()
    if not q:
        return RetrievalResult(q, [], True, NO_EVIDENCE, floor, None)

    if not vector_store.available:
        return RetrievalResult(
            q, [], True,
            f"{NO_EVIDENCE} (guideline index unavailable)",
            floor, None,
        )

    # Lexical grounding: a query naming entities absent from the corpus cannot
    # be answered from it, regardless of embedding similarity.
    unknown = unknown_entities(q)
    if unknown:
        return RetrievalResult(
            q, [], True,
            f"{NO_EVIDENCE} The following term(s) do not appear anywhere in the "
            f"ingested guideline corpus: {', '.join(sorted(set(unknown)))}.",
            floor, None,
        )

    try:
        hits = vector_store.search(q, k=k, document_ids=document_ids)
    except RetrievalBackendMismatch as exc:
        # A tool failure, not a finding about the corpus. Saying NO_EVIDENCE here
        # would tell a clinician the guidelines are silent on their question when
        # in fact the system could not read its own index.
        return RetrievalResult(
            q, [], True,
            f"Retrieval is unavailable on this machine, so the guideline corpus could not "
            f"be searched. This is a system fault, not a statement about the guidelines. {exc}",
            floor, None,
        )

    if not hits:
        return RetrievalResult(q, [], True, NO_EVIDENCE, floor, None)

    best = hits[0].score
    kept = [h for h in hits if h.score >= floor]
    if not kept:
        # Deliberate: do NOT fall back to the top hit.
        return RetrievalResult(q, [], True, NO_EVIDENCE, floor, best)

    return RetrievalResult(q, kept, False, None, floor, best)
