"""
The dual-path pipeline end to end (Spec §20, §23).

    question
       |
       +-- refusal guards (injection, personal advice)   <- before anything runs
       |
       +-- held corpus retrieval ------------------+
       |                                           |
       +-- web search -> Agent 2 filtration -------+--> Agent 3 grounding --> Agent 4 compose

The guards come FIRST and are the same ones Ask the Evidence already applies. A
question that would be refused by the extractive endpoint must not become
answerable by routing it through four agents instead: adding capability must
never remove a refusal.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend import config
from backend.agents import web_search
from backend.agents.compose import compose
from backend.agents.filtration import filter_web_results
from backend.agents.grounding import ground
from backend.agents.llm_client import available as llm_available
from backend.rag.ask import ADVICE_REFUSAL, INJECTION_REFUSAL, is_personal_advice
from backend.rag.retrieve import retrieve


def status() -> Dict[str, Any]:
    """What is actually wired up right now, for the UI to state rather than assume."""
    from backend.rag.store import vector_store

    return {
        "agent_llm_configured": llm_available(),
        "agent_llm_model": config.AGENT_LLM_MODEL if llm_available() else None,
        "web_search_enabled": web_search.available(),
        "web_search_provider": config.WEB_SEARCH_PROVIDER if web_search.available() else None,
        "web_filter_threshold": config.WEB_FILTER_ACCEPT_THRESHOLD,
        "embedding_backend": vector_store.embedding_model,
        "retrieval_is_semantic": vector_store.is_semantic,
        "corpus_documents": len(vector_store.docs),
        "corpus_chunks": len(vector_store.chunks),
        # Stated on every status read because it is the property the whole design
        # rests on, and a reader should not have to take it on trust.
        "rule_engine_independent_of_this_layer": True,
    }


def run(question: str, k: int = 4, include_web: bool = True) -> Dict[str, Any]:
    """
    Answer a question through the four-agent path.

    Returns the composed answer plus the working: what the filter accepted and
    rejected, and how the evidence was ordered. The working is not debug output --
    it is the evidence that the pipeline did what it claims.
    """
    from backend.llm.explainer import clinical_explainer

    question = (question or "").strip()
    if not question:
        return _refusal("", "EMPTY_QUERY", "No question was asked.")

    cleaned, injected = clinical_explainer.sanitize_input(question)
    if injected:
        return _refusal(question, "PROMPT_INJECTION", INJECTION_REFUSAL)
    if is_personal_advice(cleaned):
        return _refusal(question, "PERSONAL_MEDICAL_ADVICE", ADVICE_REFUSAL)

    retrieval = retrieve(cleaned, k=max(1, min(k, 10)))

    filtration = None
    web_citations = []
    if include_web and web_search.available():
        raw = web_search.search(cleaned)
        filtration = filter_web_results(raw, cleaned)
        web_citations = filtration.accepted

    context = ground(cleaned, retrieval if not retrieval.refused else None, web_citations)
    answer = compose(context)

    payload = answer.to_dict()
    payload["pipeline"] = {
        "question_asked": question,
        "held_retrieval_refused": bool(retrieval.refused),
        "held_retrieval_reason": retrieval.reason if retrieval.refused else None,
        "held_passages": context.held_count,
        "web_passages": context.web_count,
        "sufficient_to_ground": context.sufficient_to_ground,
        "insufficiency_reason": context.insufficiency_reason,
        "filtration": filtration.to_dict() if filtration else None,
        "web_path_active": bool(include_web and web_search.available()),
        "agents_run": [
            "AGENT_2_FILTRATION" if filtration else None,
            "AGENT_3_GROUNDING",
            "AGENT_4_COMPOSE",
        ],
    }
    payload["pipeline"]["agents_run"] = [a for a in payload["pipeline"]["agents_run"] if a]
    return payload


def _refusal(question: str, reason: str, message: str) -> Dict[str, Any]:
    return {
        "question": question,
        "answered": False,
        "answer_mode": "REFUSED_" + reason,
        "summary": message,
        "points": [],
        "citations": [],
        "divergences": [],
        "caveats": [],
        "refusal_reason": reason,
        "pipeline": {"agents_run": [], "web_path_active": False,
                     "note": "Refused before any agent ran."},
    }
