"""
Ask the Evidence (Spec §20, §10, §10A, §23).

Answers questions ABOUT the ingested guideline corpus. It is not a medical
chatbot and gives no clinical advice.

Design: strictly EXTRACTIVE. The response is assembled from retrieved passages
and their citations; no language model is involved, so the service is
structurally incapable of asserting a claim that is not present verbatim in a
held document. Spec §21 traceability therefore holds by construction rather than
by prompt instruction.

Four refusal paths, in order:
  1. Prompt injection detected in the question -> neutralised and refused.
  2. Request for personal medical advice -> refused, directed to a clinician.
  3. Query names an entity absent from the corpus, or is off-domain -> refused
     by the retrieval floor (see backend/rag/retrieve.py).
  4. Nothing clears the relevance floor -> refused.

Refusal always returns the same message shape. It never degrades to a
best-effort answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.rag.retrieve import NO_EVIDENCE, retrieve

INSUFFICIENT = "I don't have sufficient evidence in the ingested guideline corpus to answer that."

ADVICE_REFUSAL = (
    "This service answers questions about the ingested clinical guidelines. It does "
    "not give personal medical advice and cannot recommend treatment for an "
    "individual. Please consult a qualified clinician."
)

INJECTION_REFUSAL = (
    "The question contained instruction-like text targeting the system rather than "
    "a clinical query. It was neutralised and not acted upon."
)

# First/second-person treatment requests. This service must not become a
# consumer symptom-checker, however well the corpus happens to match.
_PERSONAL_ADVICE = re.compile(
    r"\b(?:should\s+i|can\s+i|do\s+i\s+need|what\s+should\s+i|is\s+it\s+safe\s+for\s+me|"
    r"my\s+(?:child|son|daughter|wife|husband|mother|father|infection|fever|cold|symptoms)|"
    r"i\s+(?:have|feel|took|am\s+taking)|prescribe\s+me|give\s+me\s+(?:a|an|some)\s+\w*)\b",
    re.IGNORECASE,
)


@dataclass
class AskResult:
    question: str
    answered: bool
    message: Optional[str]
    passages: List[Dict[str, Any]] = field(default_factory=list)
    injection_detected: bool = False
    sanitized_question: str = ""
    refusal_reason: Optional[str] = None
    # Everything the reader must know before using the passages: degraded lexical
    # retrieval, and passages drawn from documents that are not clinical guidelines.
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "answered": self.answered,
            "message": self.message,
            "passages": self.passages,
            "passage_count": len(self.passages),
            "injection_detected": self.injection_detected,
            "refusal_reason": self.refusal_reason,
            "caveats": self.caveats,
            "answer_mode": "EXTRACTIVE_NO_LLM",
            "disclaimer": (
                "Retrieved verbatim from the ingested guideline corpus. No language "
                "model generated this content. Clinical decision support only - not "
                "medical advice, and not a substitute for clinician judgement."
            ),
        }


def is_personal_advice(question: str) -> bool:
    return bool(_PERSONAL_ADVICE.search(question or ""))


def ask(question: str, k: int = 4) -> AskResult:
    q = (question or "").strip()
    if not q:
        return AskResult(q, False, INSUFFICIENT, refusal_reason="EMPTY_QUERY")

    # 1. Injection defence, reusing the explainer's sanitiser (Spec §10A).
    from backend.llm.explainer import clinical_explainer

    cleaned, injected = clinical_explainer.sanitize_input(q)
    if injected:
        return AskResult(
            q, False, INJECTION_REFUSAL,
            injection_detected=True, sanitized_question=cleaned,
            refusal_reason="PROMPT_INJECTION",
        )

    # 2. Personal medical advice is out of scope regardless of corpus coverage.
    if is_personal_advice(cleaned):
        return AskResult(
            q, False, ADVICE_REFUSAL,
            sanitized_question=cleaned, refusal_reason="PERSONAL_MEDICAL_ADVICE",
        )

    # 3/4. Retrieval, including the unknown-entity and relevance floors.
    result = retrieve(cleaned, k=k)
    if result.refused:
        detail = result.reason or NO_EVIDENCE
        return AskResult(
            q, False, f"{INSUFFICIENT} {detail}",
            sanitized_question=cleaned, refusal_reason="NO_RELEVANT_EVIDENCE",
        )

    passages = [c.to_citation() for c in result.chunks]
    return AskResult(
        q, True, None, passages=passages, sanitized_question=cleaned,
        # Carried through from retrieval rather than recomputed: the answer and the
        # warning about the answer must not be able to drift apart.
        caveats=result.caveats(),
    )
