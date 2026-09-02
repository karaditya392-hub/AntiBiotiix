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

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.rag.store import (
    DOMAIN_READING_CONTRACT,
    RetrievalBackendMismatch,
    RetrievedChunk,
    vector_store,
)

NO_EVIDENCE = "No sufficiently relevant evidence was retrieved."

# Cosine similarity floor. Below this, a chunk is not offered as evidence.
#
# 0.45 was set for the 39-document corpus (up from 0.35 at 11 documents). It was
# RE-MEASURED, and kept, for the 94-document corpus. Over 30 legitimate and 15
# off-domain queries, counting only those that survive unknown_entities() and
# therefore actually reach the floor:
#
#   lowest legitimate  0.4677  ("WHO AWaRe access watch reserve classification")
#   highest off-domain 0.4270  ("best pizza recipe" -> ICMR-T1DM-2022)
#
# 0.45 still separates them cleanly: it rejects no legitimate query and admits no
# off-domain one.
#
# THE MARGIN IS NEARLY GONE, AND THAT IS THE FINDING THAT MATTERS HERE. It was
# 0.219 at 11 documents, 0.181 at 39, and is 0.041 now -- the floor sits 0.018
# above the highest off-domain score. Each expansion has eaten roughly the same
# fraction of it, and for the same reason: more documents mean more ordinary
# English competing for the nearest neighbour, so an off-domain query's best match
# keeps rising. "best pizza recipe" now scores 0.427 against the type 1 diabetes
# guideline, on its dietary content -- the same mechanism as the food composition
# table in the burns document that forced the last recalibration.
#
# So the next batch of documents should NOT be answered by raising this number
# again. Raising it far enough to restore the old margin would start rejecting
# legitimate queries, which the 0.4677 above shows are already close. What the
# next expansion needs is a second signal -- a domain or document-set restriction
# on the query, in the way unknown_entities() is a second signal for invented
# names -- not a higher threshold.
#
# Invented drug names still score high (0.62 for "flurbamycin dosing in adults"):
# a nonsense name in a well-formed dosing question matches on sentence FORM, not
# content, and no threshold separates those. They are caught before scoring by
# unknown_entities() below. Neither check alone is sufficient.
#
# ---------------------------------------------------------------------------
# RE-MEASURED 02-09-2026 for nvidia/nemotron-3-embed-1b (2048 dim), which
# replaced all-MiniLM-L6-v2 as the retrieval model. Same method, same corpus,
# scripts/calibrate_relevance_floor.py:
#
#   lowest legitimate  0.3906  ("nitrofurantoin renal impairment")
#   highest off-domain 0.2608  ("how to train a puppy")
#   MARGIN             0.1298
#
# THE MARGIN PROBLEM ABOVE IS THE ONE THIS ADDRESSES, and a stronger retrieval
# model is what the note above said was needed instead of a higher threshold.
# 0.041 -> 0.1298 is a 3.2x recovery, back between the 0.181 measured at 39
# documents and the 0.219 at 11, on a corpus more than twice the size of either.
#
# THE FLOOR HAD TO MOVE, and leaving it would have been the failure. A cosine
# floor is a property of the model's score distribution, not a constant: 0.45 on
# THIS index refuses "nitrofurantoin renal impairment" at 0.3906, a question the
# corpus plainly answers. 0.326 is the midpoint of the measured gap, chosen the
# same way 0.45 was for MiniLM -- it rejects no legitimate query in the set and
# admits no off-domain one.
#
# Three off-domain queries never reach the floor at all now ("best pizza recipe
# in Naples" among them) because unknown_entities() rejects them first. That is
# the second signal doing its job, not the threshold.
#
# ANY FUTURE EMBEDDING CHANGE MUST RE-RUN THE CALIBRATION. A floor carried across
# a model swap is a number that no longer means what this comment says.
# ---------------------------------------------------------------------------
RELEVANCE_FLOOR = 0.326

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


# A FLOOR PER EMBEDDING MODEL, because a cosine threshold is a measurement of one
# model's score distribution and nothing else.
#
# THE BUG THIS FIXES, found by cloning the repository and running it as a new user
# would: RELEVANCE_FLOOR was re-measured for nvidia/nemotron-3-embed-1b and moved
# to 0.326. A fresh clone defaults to EMBEDDING_BACKEND=local and rebuilds the
# index with all-MiniLM-L6-v2, whose scores sit higher -- its own calibration put
# the floor at 0.45. Judging MiniLM scores against the NVIDIA floor let off-domain
# questions through: "how to train a puppy" scored 0.3414, cleared 0.326, and was
# answered instead of refused. That is precisely the failure the floor exists to
# prevent, introduced by carrying one model's number onto another model's index.
#
# Each entry is the midpoint of that model's own measured legitimate/off-domain
# gap. An unknown model falls back to the STRICTER of the known floors rather than
# the looser one: refusing a legitimate question is recoverable by rephrasing;
# answering an off-domain one with a clinical passage is not.
MODEL_RELEVANCE_FLOORS = {
    "nvidia:nvidia/nemotron-3-embed-1b": 0.326,
    "sentence-transformers/all-MiniLM-L6-v2": 0.45,
}


def active_floor() -> float:
    """
    The floor appropriate to the model that actually built the index in use here.

    Passed explicitly rather than read inside retrieve() so a caller can still
    override it, and so the chosen value appears in the response.
    """
    if not vector_store.is_semantic:
        return LEXICAL_RELEVANCE_FLOOR
    model = vector_store.embedding_model
    if model in MODEL_RELEVANCE_FLOORS:
        return MODEL_RELEVANCE_FLOORS[model]
    # Unrecognised model: no calibration exists for it, so take the strictest
    # known floor and let scripts/calibrate_relevance_floor.py establish the
    # right one before it is loosened.
    return max(MODEL_RELEVANCE_FLOORS.values())

# Query tokens at least this long are treated as specific entity names
# (drug names, organisms, syndromes) rather than ordinary English.
_ENTITY_MIN_LEN = 6

# Longest suffix a corpus word may drop and still count as the stem of a query
# token. See the stem check in unknown_entities().
_MAX_INFLECTION_SUFFIX = 4

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
        # A corpus word is a STEM of this token only if what it drops is short
        # enough to be an inflection. Without the length bound, any token whose
        # first five-or-more characters happen to spell a corpus word counts as
        # grounded, and on a 44,000-word vocabulary that is a large surface.
        #
        # This bound was added after the corpus grew to 94 documents and the guard
        # stopped catching "fictionalcillin": the expanded vocabulary contains
        # "fiction", so an eight-character suffix -- "alcillin" -- was being treated
        # as an inflection of it. The invented drug name then reached the relevance
        # floor, which is the check that cannot separate it, because a nonsense name
        # in a well-formed dosing question matches on sentence form.
        #
        # Four characters covers the inflections this is for (-s, -es, -ed, -ly,
        # -ing, -ally) and keeps "renally" grounded against "renal". It does not
        # cover "-alcillin".
        if any(
            tok[:n] in vocab
            for n in range(max(5, len(tok) - _MAX_INFLECTION_SUFFIX), len(tok))
        ):
            continue
        out.append(tok)
    return out


# A reference to a NAMED document: an optional capitalised name, a guideline-ish
# noun, and an optional year. "the Fictional Guideline 2099", "ICMR Guidelines 2019".
# The name must be genuinely Capitalised, so case-insensitivity is scoped to the
# noun alone. Applying re.IGNORECASE to the whole pattern makes [A-Z] match
# lowercase, which swallowed the question's opening words -- "what do the
# guidelines recommend for sepsis" was read as a reference to a document named
# "what do the", and refused.
_NAMED_DOCUMENT = re.compile(
    r"\b((?:[A-Z][A-Za-z-]*\s+){0,4})"
    r"(?i:(Guidelines?|Protocols?|Manuals?|Handbooks?|Formular(?:y|ies)|"
    r"Consensus\s+Documents?|Standard\s+Treatment\s+\w+))"
    r"(?:\s*,?\s*(\d{4}))?"
)


def unknown_document_reference(query: str) -> Optional[str]:
    """
    A named guideline the corpus does not hold, or None.

    Separate from unknown_entities(), which asks whether a WORD appears in the
    corpus text. This asks whether a DOCUMENT the question names is actually held,
    and the two come apart: "Fictional Guideline 2099" is built from ordinary
    English that appears throughout a 94-document corpus, so the vocabulary check
    finds nothing wrong with it.

    Answering it anyway is the §23 failure. The retrieved passages would be real,
    correctly attributed WHO and ICMR text about sepsis, and the reader asked what
    a specific named guideline recommends -- so a list of passages under that
    question invites them to believe the named guideline exists and says this. The
    corpus can only report what it holds, and it holds no such document.
    """
    from backend.rag.store import vector_store

    if not vector_store.docs:
        return None

    held_years = set()
    held_text = []
    for doc in vector_store.docs.values():
        blob = " ".join(
            str(doc.get(f) or "") for f in ("title", "issuing_org", "version", "publication_date")
        ).lower()
        held_text.append(blob)
        held_years.update(re.findall(r"\b(1[89]\d{2}|20\d{2})\b", blob))
    corpus_blob = " ".join(held_text)

    for match in _NAMED_DOCUMENT.finditer(query or ""):
        name, noun, year = match.group(1) or "", match.group(2), match.group(3)
        reference = f"{name}{noun} {year or ''}".strip()

        # A year no held document carries is decisive on its own: the question asks
        # about an edition this corpus does not have, whatever it is called.
        if year and year not in held_years:
            return reference

        # Otherwise judge the name. Distinctive words only -- the guideline noun and
        # ordinary qualifiers say nothing about which document is meant.
        tokens = [
            t.lower() for t in re.findall(r"[A-Za-z-]{4,}", name)
            if t.lower() not in {"the", "national", "indian", "clinical", "treatment",
                                 "standard", "current", "latest", "official", "new"}
        ]
        if tokens and not any(t in corpus_blob for t in tokens):
            return reference
    return None


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

    @property
    def non_antimicrobial_sources(self) -> List[str]:
        """
        Retrieved documents that may not be cited for antimicrobial choice.

        Wider than non_clinical_sources, and the distinction matters: an ICMR cancer
        consensus document IS a clinical guideline and still has no standing on
        antimicrobial selection. Reporting only the non-clinical set would let an
        oncology passage stand as antimicrobial evidence.
        """
        seen = []
        for c in self.chunks:
            if not c.carries_antimicrobial_authority and c.document_id not in seen:
                seen.append(c.document_id)
        return seen

    @property
    def domains_retrieved(self) -> List[str]:
        seen = []
        for c in self.chunks:
            if c.clinical_domain not in seen:
                seen.append(c.clinical_domain)
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

        # The per-domain reading contract, emitted once per domain actually present.
        # Repeating it per passage would bury it; omitting it would leave a research
        # ethics passage looking like any other retrieved evidence.
        for domain in self.domains_retrieved:
            contract = DOMAIN_READING_CONTRACT.get(domain)
            if not contract:
                continue
            ids = sorted({c.document_id for c in self.chunks if c.clinical_domain == domain})
            out.append(f"{contract} Affected passage(s): {', '.join(ids)}.")

        # Said plainly and last, because it is the caveat most likely to matter and
        # the one a reader skimming a list of citations is most likely to assume away.
        #
        # Gated on antimicrobial CONTENT, not on the antimicrobial DOMAIN. Gating on
        # the domain would fire this caveat on a leptospirosis query answered by
        # NCDC-LEPTOSPIROSIS-2015 -- a condition-specific document that does carry
        # doxycycline recommendations -- and tell the reader the corpus had not
        # answered a question it had just answered. Saying the corpus is silent when
        # it is not is the same class of false statement as a fabricated citation.
        from backend.config import ANTIMICROBIAL_CONTENT_DOCUMENT_IDS

        if self.chunks and not any(
            c.document_id in ANTIMICROBIAL_CONTENT_DOCUMENT_IDS for c in self.chunks
        ):
            out.append(
                "NO PASSAGE RETRIEVED HERE CARRIES ANTIMICROBIAL RECOMMENDATIONS. If this "
                "question was about antimicrobial choice, the corpus has not answered it: "
                "consult the national antimicrobial treatment guidelines and the local "
                "hospital antibiogram."
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
            "non_antimicrobial_sources": self.non_antimicrobial_sources,
            "domains_retrieved": self.domains_retrieved,
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

    # A question about a document the corpus does not hold cannot be answered from
    # the corpus, however well its other words match. Checked before the vocabulary
    # floor because the words in such a question are usually perfectly ordinary.
    missing_doc = unknown_document_reference(q)
    if missing_doc:
        return RetrievalResult(
            q, [], True,
            f"{NO_EVIDENCE} This corpus holds no document matching {missing_doc!r}. "
            f"Passages from the documents it does hold are not an answer to a question "
            f"about that one.",
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
