"""
The dual-path search pipeline end to end (Spec §20, §23).

    question
       |
       +-- refusal guards (injection, personal advice)   <- before anything runs
       |
       +-- PARALLEL FAN-OUT
       |     |
       |     +-- vector DB search (held corpus) ------------------+
       |     |                                                    |
       |     +-- web search --> Agent 2 authenticity filter ------+
       |                                                          |
       +---------------------------> couple & ground (Agent 3) ---+
                                              |
                                     structured output (Agent 4)
                                              |
                                     render contract (JSON)

WHY THE FAN-OUT IS PARALLEL. Both branches are I/O-bound and INDEPENDENT: the
vector search reads a local index, the web search calls a vendor, and neither
needs the other's answer. Run in sequence, the total latency was the sum -- and
the web branch, which is the slow and unreliable one, was making a clinician wait
for evidence the local corpus already had. Run together, the wall clock is the
slower branch, and a web vendor that hangs no longer delays local evidence at
all: the fan-out has a timeout, and a branch that misses it is reported as
degraded rather than waited for.

WHAT PARALLELISM MUST NOT CHANGE. Every safety property here is about ORDER of
authority, not order of execution. Web results still pass the filtration agent
before anything can quote them, still enter at precedence rank 5, and still
cannot ground an antimicrobial recommendation alone. Concurrency changes when
work happens; it changes nothing about what may be said.

THE GUARDS COME FIRST and are the same ones Ask the Evidence already applies. A
question that would be refused by the extractive endpoint must not become
answerable by routing it through four agents instead: adding capability must
never remove a refusal.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Dict, List, Optional, Tuple

from backend import config
from backend.agents import render, web_search
from backend.agents.compose import compose
from backend.agents.filtration import filter_web_results
from backend.agents.grounding import ground
from backend.agents.llm_client import available as llm_available
from backend.agents.trace import (
    PipelineTrace, SEARCH_PIPELINE_ID, STATUS_DEGRADED, STATUS_OK, STATUS_REFUSED,
)
from backend.rag.ask import ADVICE_REFUSAL, INJECTION_REFUSAL, is_personal_advice
from backend.rag.retrieve import retrieve


def status() -> Dict[str, Any]:
    """What is actually wired up right now, for the UI to state rather than assume."""
    from backend.rag.store import vector_store

    return {
        "agent_llm_configured": llm_available(),
        "agent_llm_model": config.AGENT_LLM_MODEL if llm_available() else None,
        "agent_llm_base_url": config.NVIDIA_BASE_URL,
        "web_search_enabled": web_search.available(),
        "web_search_provider": config.WEB_SEARCH_PROVIDER if web_search.available() else None,
        "web_filter_threshold": config.WEB_FILTER_ACCEPT_THRESHOLD,
        "embedding_backend": vector_store.embedding_model,
        "retrieval_is_semantic": vector_store.is_semantic,
        "corpus_documents": len(vector_store.docs),
        "corpus_chunks": len(vector_store.chunks),
        "parallel_fan_out": True,
        "parallel_timeout_s": config.SEARCH_PARALLEL_TIMEOUT_S,
        "render_schema": render.SCHEMA_VERSION,
        "ingestion_validation_requires_model": config.INGEST_VALIDATION_REQUIRE_MODEL,
        "markdown_conversion": True,
        # Stated on every status read because it is the property the whole design
        # rests on, and a reader should not have to take it on trust.
        "rule_engine_independent_of_this_layer": True,
    }


def _fan_out(question: str, k: int, include_web: bool, trace: PipelineTrace) -> Tuple[Any, List[Dict[str, Any]], Optional[str]]:
    """
    Dispatch the vector search and the web search together.

    Returns (retrieval_result, raw_web_results, web_skipped_reason). A branch that
    fails or times out yields its empty value and a recorded reason -- never an
    exception that takes the other branch down with it. Losing the web evidence
    degrades an answer; losing the corpus evidence would be a broken system.
    """
    web_off_reason: Optional[str] = None
    if not include_web:
        web_off_reason = "The caller asked for held-corpus evidence only."
    elif not web_search.available():
        web_off_reason = (
            f"The web path is not configured (provider {config.WEB_SEARCH_PROVIDER!r}, "
            f"enabled={config.WEB_SEARCH_ENABLED}). Held corpus only."
        )

    run_web = web_off_reason is None
    trace.mark(
        "SEARCH_FANOUT", STATUS_OK,
        "Vector search and web search dispatched concurrently."
        if run_web else "Vector search dispatched; the web branch is not active.",
        branches=["SEARCH_VECTOR", "SEARCH_WEB"] if run_web else ["SEARCH_VECTOR"],
        parallel=run_web,
    )

    # DELIBERATELY NOT `with ThreadPoolExecutor(...)`. The context manager's exit
    # calls shutdown(wait=True), which blocks until every submitted task finishes
    # -- so a web provider hanging for two minutes would hold the request open for
    # two minutes AFTER its timeout had already fired, and the timeout below would
    # bound nothing at all. The pool is shut down without waiting instead: the
    # abandoned thread finishes into a result nobody reads.
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="search-fanout")
    try:
        vector_future: Future = pool.submit(retrieve, question, k)
        web_future: Optional[Future] = pool.submit(web_search.search, question) if run_web else None

        timeout = config.SEARCH_PARALLEL_TIMEOUT_S

        # --- vector branch ----------------------------------------------------
        with trace.node("SEARCH_VECTOR") as node:
            try:
                retrieval = vector_future.result(timeout=timeout)
            except FuturesTimeout:
                node.status = STATUS_DEGRADED
                node.detail = f"Vector search did not return within {timeout:.0f}s."
                retrieval = None
            except Exception as exc:
                node.status = STATUS_DEGRADED
                node.detail = f"Vector search failed: {type(exc).__name__}: {exc}"
                retrieval = None
            else:
                if retrieval.refused:
                    node.status = STATUS_REFUSED
                    node.detail = retrieval.reason or "Nothing cleared the relevance floor."
                else:
                    node.detail = (f"{len(retrieval.chunks)} passage(s) above the "
                                   f"{retrieval.floor:.3f} relevance floor")
                node.metrics = {
                    "passages": 0 if retrieval.refused else len(retrieval.chunks),
                    "relevance_floor": retrieval.floor,
                    "best_score": retrieval.best_score,
                    "refused": retrieval.refused,
                }

        # --- web branch -------------------------------------------------------
        raw_web: List[Dict[str, Any]] = []
        if web_future is None:
            trace.skip("SEARCH_WEB", web_off_reason or "Web path inactive.")
        else:
            with trace.node("SEARCH_WEB") as node:
                try:
                    raw_web = web_future.result(timeout=timeout) or []
                except FuturesTimeout:
                    node.status = STATUS_DEGRADED
                    node.detail = (f"The web provider did not answer within {timeout:.0f}s. "
                                   f"Answering from the held corpus alone.")
                    web_off_reason = node.detail
                except Exception as exc:
                    node.status = STATUS_DEGRADED
                    node.detail = f"Web search failed: {type(exc).__name__}. Held corpus only."
                    web_off_reason = node.detail
                else:
                    node.detail = (f"{len(raw_web)} unjudged result(s) from "
                                   f"{config.WEB_SEARCH_PROVIDER}")
                    node.metrics = {"results": len(raw_web),
                                    "provider": config.WEB_SEARCH_PROVIDER}
                    if not raw_web:
                        node.status = STATUS_DEGRADED
                        node.detail = "The web provider returned nothing for this query."
    finally:
        # wait=False so a branch that overran its timeout cannot hold the request
        # open; cancel_futures clears anything not yet started.
        pool.shutdown(wait=False, cancel_futures=True)

    return retrieval, raw_web, web_off_reason


def run(question: str, k: int = 4, include_web: bool = True) -> Dict[str, Any]:
    """
    Answer a question through the agent path.

    Returns the composed answer, the render contract a client draws from, and the
    working: what the filter accepted and rejected, how the evidence was ordered,
    and which node did what. The working is not debug output -- it is the evidence
    that the pipeline did what it claims.
    """
    from backend.llm.explainer import clinical_explainer

    trace = PipelineTrace(SEARCH_PIPELINE_ID)
    question = (question or "").strip()

    with trace.node("SEARCH_QUERY") as node:
        node.detail = f"{len(question)} character question" if question else "Empty question"
    if not question:
        return _refusal(trace, "", "EMPTY_QUERY", "No question was asked.")

    # --- the guards, before anything else runs -------------------------------
    with trace.node("SEARCH_GUARD") as node:
        cleaned, injected = clinical_explainer.sanitize_input(question)
        advice = not injected and is_personal_advice(cleaned)
        if injected or advice:
            node.status = STATUS_REFUSED
            node.detail = ("Prompt-injection content in the question."
                           if injected else "Request for personal medical advice.")
        else:
            node.detail = "Passed: no injection content, not a request for personal advice."
    if injected:
        return _refusal(trace, question, "PROMPT_INJECTION", INJECTION_REFUSAL)
    if advice:
        return _refusal(trace, question, "PERSONAL_MEDICAL_ADVICE", ADVICE_REFUSAL)

    # --- parallel fan-out: vector DB and web, together -----------------------
    retrieval, raw_web, web_skipped = _fan_out(
        cleaned, max(1, min(k, 10)), include_web, trace,
    )

    # --- Agent 2: authenticity filter over the web results -------------------
    filtration = None
    web_citations: List[Dict[str, Any]] = []
    if not raw_web:
        trace.skip("SEARCH_FILTER",
                   web_skipped or "No web results were retrieved, so there was nothing to filter.")
    else:
        with trace.node("SEARCH_FILTER") as node:
            filtration = filter_web_results(raw_web, cleaned)
            web_citations = filtration.accepted
            node.detail = (f"{len(filtration.accepted)} accepted, "
                           f"{len(filtration.rejected)} rejected at threshold "
                           f"{config.WEB_FILTER_ACCEPT_THRESHOLD}")
            node.metrics = {
                "accepted": len(filtration.accepted),
                "rejected": len(filtration.rejected),
                "threshold": config.WEB_FILTER_ACCEPT_THRESHOLD,
                "degraded_no_model": filtration.degraded,
                "verdicts": [
                    {"site": v.site, "accepted": v.accepted, "score": round(v.score, 3),
                     "reason": v.reason}
                    for v in filtration.verdicts
                ],
            }
            if filtration.degraded:
                node.status = STATUS_DEGRADED
                node.detail += " — no assessing model configured, so every result was refused."

    # --- Agent 3: couple both sources and ground by precedence ---------------
    with trace.node("SEARCH_COUPLE") as node:
        usable = retrieval if (retrieval is not None and not retrieval.refused) else None
        context = ground(cleaned, usable, web_citations,
                         max_passages=config.SEARCH_MAX_PASSAGES)
        node.detail = (f"{context.held_count} corpus + {context.web_count} web passage(s) "
                       f"ordered by precedence")
        node.metrics = {
            "held_passages": context.held_count,
            "web_passages": context.web_count,
            "sufficient_to_ground": context.sufficient_to_ground,
            "divergences": len(context.divergences),
            "caveats": len(context.caveats),
            "fusion": "DETERMINISTIC_PRECEDENCE_ORDER_NO_MODEL",
        }
        if not context.sufficient_to_ground:
            node.status = STATUS_REFUSED
            node.detail = context.insufficiency_reason or "Nothing to ground an answer on."

    # --- Agent 4: the structured answer --------------------------------------
    with trace.node("SEARCH_STRUCTURE") as node:
        answer = compose(context)
        node.detail = answer.mode
        node.metrics = {"mode": answer.mode, "model": answer.model,
                        "points": len(answer.points),
                        "rejected_because": answer.rejection}
        if answer.mode == "REFUSED_INSUFFICIENT_EVIDENCE":
            node.status = STATUS_REFUSED
        elif answer.rejection:
            # The model answered and the answer failed a post-generation check, so
            # the passages were returned instead. Degraded, and named as such.
            node.status = STATUS_DEGRADED

    payload = answer.to_dict()
    payload["pipeline"] = {
        "question_asked": question,
        "held_retrieval_refused": bool(getattr(retrieval, "refused", True)) if retrieval else True,
        "held_retrieval_reason": (retrieval.reason if retrieval and retrieval.refused else None),
        "held_passages": context.held_count,
        "web_passages": context.web_count,
        "sufficient_to_ground": context.sufficient_to_ground,
        "insufficiency_reason": context.insufficiency_reason,
        "filtration": filtration.to_dict() if filtration else None,
        "web_path_active": bool(raw_web),
        "web_skipped_reason": web_skipped,
        "parallel_fan_out": True,
        "agents_run": [a for a in [
            "AGENT_2_FILTRATION" if filtration else None,
            "AGENT_3_GROUNDING",
            "AGENT_4_COMPOSE",
        ] if a],
    }

    with trace.node("SEARCH_RENDER") as node:
        payload["render"] = render.build(
            question=question,
            answer=answer,
            context=context,
            filtration=filtration,
            retrieval=retrieval,
            web_path_active=bool(raw_web),
            web_skipped_reason=web_skipped,
            trace=None,
        )
        node.detail = (f"{len(payload['render']['citations'])} citation(s) in "
                       f"{len(payload['render']['sections'])} section(s)")
        node.metrics = {"schema": render.SCHEMA_VERSION}

    payload["trace"] = trace.to_dict()
    payload["render"]["trace"] = payload["trace"]
    return payload


def _refusal(trace: PipelineTrace, question: str, reason: str, message: str) -> Dict[str, Any]:
    for node_id in ("SEARCH_FANOUT", "SEARCH_VECTOR", "SEARCH_WEB", "SEARCH_FILTER",
                    "SEARCH_COUPLE", "SEARCH_STRUCTURE"):
        trace.skip(node_id, "Refused before any agent ran.")
    trace.mark("SEARCH_RENDER", STATUS_REFUSED, message)

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
                     "parallel_fan_out": False,
                     "note": "Refused before any agent ran."},
        "render": {
            "schema": render.SCHEMA_VERSION,
            "question": question,
            "answered": False,
            "answer_mode": "REFUSED_" + reason,
            "answer_mode_description": message,
            "refusal_reason": reason,
            "sections": [{"kind": "REFUSAL", "title": "Refused", "text": message}],
            "citations": [],
            "evidence_groups": [],
            "evidence": {"total": 0, "from_vector_db": 0, "from_web": 0,
                         "sufficient_to_ground": False,
                         "insufficiency_reason": message,
                         "carries_antimicrobial_authority": False},
            "sources": {"vector_db": {"ran": False}, "web": {"ran": False}},
            "trace": trace.to_dict(),
        },
        "trace": trace.to_dict(),
    }
