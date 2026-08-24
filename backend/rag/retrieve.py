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
# Calibrated against 12 legitimate and 7 nonsense queries over the ingested
# corpus. Those two classes OVERLAP on cosine similarity alone: the lowest
# legitimate score was 0.522 ("nitrofurantoin renal impairment") while the
# highest nonsense score was 0.595 ("zzzzmycin 500mg indications"). A nonsense
# drug name embedded in a well-formed dosing question matches dosing sections on
# sentence FORM, not content, so no single threshold can separate them.
#
# The floor is therefore set to catch clearly off-domain queries only, and is
# paired with the lexical grounding check below, which catches queries naming
# entities the corpus has never heard of. Neither check alone is sufficient.
RELEVANCE_FLOOR = 0.35

# Floor for the LEXICAL fallback, used when this machine could not load the
# semantic model and the corpus was re-embedded with TF-IDF.
#
# It needs its own number because the two backends score on different scales:
# applying 0.35 to TF-IDF rejected every genuine question, which is how a working
# corpus came to answer "no sufficiently relevant evidence" on a machine without
# the model cached.
#
# Calibrated the same way as the semantic floor, on this corpus:
#   lowest legitimate query  0.167  ("empirical treatment for typhoid fever")
#   highest nonsense query   0.162  ("zzzzmycin 500mg indications")
# Those two barely separate, exactly as they fail to separate for the semantic
# backend. The floor is therefore NOT asked to carry the load alone: invented
# drug names such as zzzzmycin are already rejected by unknown_entities() before
# scoring, leaving genuinely off-domain English as what the floor must catch, and
# that tops out at 0.131 ("how do I change a bicycle tyre"). 0.15 sits between
# that and the lowest real question.
LEXICAL_RELEVANCE_FLOOR = 0.15


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
