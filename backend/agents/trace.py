"""
Pipeline execution traces, and the graph shape the UI draws them on.

WHY THE GRAPH LIVES IN THE BACKEND. A flow diagram maintained in the frontend is
a drawing of what someone believed the pipeline did on the day they drew it. It
stays on screen unchanged after a node is removed, and it shows a filtration step
running when no key is configured and nothing filtered anything. That is worse
than no diagram: a reader trusts a picture more than prose, so a wrong picture
misleads harder.

So the nodes and edges are declared HERE, next to the code that executes them,
and `/api/agents/graph` serves them. Every run then returns a trace keyed by the
same node ids, and the UI colours the declared graph with the actual run. A node
that did not run shows as SKIPPED with the reason, which is the state a diagram
normally cannot express and the one that matters most -- "the web path was off"
and "the web path found nothing" look identical on screen otherwise.

A trace is not debug output. It records which agents ran, which were skipped and
why, and how long each took, for a system whose entire claim is that its evidence
handling can be reviewed afterwards.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_OK = "OK"
STATUS_SKIPPED = "SKIPPED"
STATUS_REFUSED = "REFUSED"
STATUS_FAILED = "FAILED"
STATUS_DEGRADED = "DEGRADED"

KIND_START = "START"
KIND_AGENT = "AGENT"
KIND_DETERMINISTIC = "DETERMINISTIC"
KIND_LLM = "LLM"
KIND_STORE = "STORE"
KIND_EXTERNAL = "EXTERNAL"
KIND_GUARD = "GUARD"
KIND_END = "END"


@dataclass
class NodeRun:
    node_id: str
    status: str = STATUS_PENDING
    detail: str = ""
    started_at: Optional[str] = None
    duration_ms: Optional[int] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "detail": self.detail,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "metrics": self.metrics,
        }


class PipelineTrace:
    """
    The record of one run.

    Node order in `runs` is completion order, which is deliberately NOT the graph
    order: in the search pipeline two nodes run concurrently, and a trace that
    re-sorted them into the drawn order would hide the one property the parallel
    fan-out exists to have.
    """

    def __init__(self, pipeline_id: str) -> None:
        self.pipeline_id = pipeline_id
        self.started = time.perf_counter()
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.runs: List[NodeRun] = []
        self._by_id: Dict[str, NodeRun] = {}

    def _record(self, node: NodeRun) -> NodeRun:
        existing = self._by_id.get(node.node_id)
        if existing is not None:
            self.runs.remove(existing)
        self.runs.append(node)
        self._by_id[node.node_id] = node
        return node

    @contextmanager
    def node(self, node_id: str, detail: str = "") -> Iterator[NodeRun]:
        """
        Time one node.

        An exception inside the block is recorded as FAILED and RE-RAISED. Swallowing
        it here would produce a trace saying a node failed beside a response that
        behaved as though it had not.
        """
        run = self._record(NodeRun(node_id, STATUS_RUNNING, detail,
                                   datetime.now(timezone.utc).isoformat(timespec="seconds")))
        clock = time.perf_counter()
        try:
            yield run
        except Exception as exc:
            run.status = STATUS_FAILED
            run.detail = f"{type(exc).__name__}: {exc}"
            run.duration_ms = int((time.perf_counter() - clock) * 1000)
            raise
        else:
            run.duration_ms = int((time.perf_counter() - clock) * 1000)
            if run.status == STATUS_RUNNING:
                run.status = STATUS_OK

    def mark(self, node_id: str, status: str, detail: str = "", **metrics: Any) -> NodeRun:
        """Record a node that took no measurable time -- a skip, a guard, a terminal state."""
        run = self._record(NodeRun(node_id, status, detail,
                                   datetime.now(timezone.utc).isoformat(timespec="seconds"), 0))
        run.metrics.update(metrics)
        return run

    def skip(self, node_id: str, why: str) -> NodeRun:
        return self.mark(node_id, STATUS_SKIPPED, why)

    @property
    def total_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline": self.pipeline_id,
            "started_at": self.started_at,
            "total_ms": self.total_ms,
            "nodes": [r.to_dict() for r in self.runs],
            "node_count": len(self.runs),
        }


# ---------------------------------------------------------------------------
# The declared graphs
#
# `lane` positions a node horizontally and `row` vertically, so the two nodes that
# genuinely run at the same time sit in the same lane on different rows. The UI
# does not decide which steps are concurrent; it reads it here.
# ---------------------------------------------------------------------------

INGESTION_PIPELINE_ID = "INGESTION"
SEARCH_PIPELINE_ID = "SEARCH"

INGESTION_GRAPH: Dict[str, Any] = {
    "id": INGESTION_PIPELINE_ID,
    "title": "Document Ingestion Agent",
    "subtitle": "PDF or document in, verified Markdown and a searchable index out.",
    "nodes": [
        {"id": "INGEST_RECEIVE", "label": "Document received", "kind": KIND_START, "lane": 0, "row": 0,
         "description": "The uploaded file, its size and its SHA-256. The hash is what proves later which bytes were read."},
        {"id": "INGEST_CONVERT", "label": "Convert to Markdown", "kind": KIND_DETERMINISTIC, "lane": 1, "row": 0,
         "description": "PyMuPDF structural conversion: headings by font size, tables as pipe tables, page anchors preserved. No model, no paraphrase."},
        {"id": "INGEST_EXTRACT", "label": "Extract content", "kind": KIND_DETERMINISTIC, "lane": 2, "row": 0,
         "description": "Headings, tables, page count and plain text pulled out of the Markdown for the checks that follow."},
        {"id": "INGEST_VALIDATE", "label": "Validate (guardrails)", "kind": KIND_GUARD, "lane": 3, "row": 0,
         "description": "Seven deterministic rules: content volume, injection, patient identifiers, encoding, structure, issuer, blank-form. A blocking failure ends the run here."},
        {"id": "INGEST_REVIEW", "label": "LLM content review", "kind": KIND_LLM, "lane": 4, "row": 0,
         "description": "A bounded model review that may only REJECT. It can never clear a document a rule blocked and never raises its standing."},
        {"id": "INGEST_CLASSIFY", "label": "Classify & rank", "kind": KIND_AGENT, "lane": 5, "row": 0,
         "description": "What kind of document it is, and the precedence rank that supports. The uploader's claim is a request; agreement is required to grant it."},
        {"id": "INGEST_CHUNK", "label": "Chunk", "kind": KIND_DETERMINISTIC, "lane": 6, "row": 0,
         "description": "Markdown split on structure with page and section carried on every chunk, so a citation resolves to a place in the document."},
        {"id": "INGEST_EMBED", "label": "Embed & index", "kind": KIND_STORE, "lane": 7, "row": 0,
         "description": "Chunks embedded and spliced into the vector index by document id, verified row-for-row before anything is written."},
        {"id": "INGEST_RETURN", "label": "Markdown returned", "kind": KIND_END, "lane": 8, "row": 0,
         "description": "The Markdown file is saved and offered back for download, and the document is retrievable by search and by RAG chat from this moment."},
    ],
    "edges": [
        {"from": "INGEST_RECEIVE", "to": "INGEST_CONVERT"},
        {"from": "INGEST_CONVERT", "to": "INGEST_EXTRACT"},
        {"from": "INGEST_EXTRACT", "to": "INGEST_VALIDATE"},
        {"from": "INGEST_VALIDATE", "to": "INGEST_REVIEW"},
        {"from": "INGEST_REVIEW", "to": "INGEST_CLASSIFY"},
        {"from": "INGEST_CLASSIFY", "to": "INGEST_CHUNK"},
        {"from": "INGEST_CHUNK", "to": "INGEST_EMBED"},
        {"from": "INGEST_EMBED", "to": "INGEST_RETURN"},
    ],
}

SEARCH_GRAPH: Dict[str, Any] = {
    "id": SEARCH_PIPELINE_ID,
    "title": "Evidence Search Agent",
    "subtitle": "One query, two sources searched at once, coupled and grounded into one structured answer.",
    "nodes": [
        {"id": "SEARCH_QUERY", "label": "Query received", "kind": KIND_START, "lane": 0, "row": 1,
         "description": "The clinician's question, before anything runs."},
        {"id": "SEARCH_GUARD", "label": "Refusal guards", "kind": KIND_GUARD, "lane": 1, "row": 1,
         "description": "Prompt injection and personal-medical-advice guards. The same refusals the extractive endpoint makes: adding agents must never remove a refusal."},
        {"id": "SEARCH_FANOUT", "label": "Parallel fan-out", "kind": KIND_DETERMINISTIC, "lane": 2, "row": 1,
         "description": "Vector search and web search dispatched together on separate threads. Both are I/O-bound, and running them in sequence made the slower one the whole latency."},
        {"id": "SEARCH_VECTOR", "label": "Vector DB search", "kind": KIND_STORE, "lane": 3, "row": 0,
         "description": "Semantic retrieval over the held corpus, including every clinician-ingested document. Below the relevance floor, nothing is returned rather than the best of a bad set."},
        {"id": "SEARCH_WEB", "label": "Web search", "kind": KIND_EXTERNAL, "lane": 3, "row": 2,
         "description": "Live retrieval. Returns raw, unjudged results in a shape nothing downstream can render, so none of it can reach a reader unfiltered."},
        {"id": "SEARCH_FILTER", "label": "Authenticity filter (LLM)", "kind": KIND_LLM, "lane": 4, "row": 2,
         "description": "Every web result judged individually and concurrently. Deterministic rejections run before the model; a score below threshold is a rejection, not a weak acceptance."},
        {"id": "SEARCH_COUPLE", "label": "Couple & ground", "kind": KIND_AGENT, "lane": 5, "row": 1,
         "description": "Both evidence sets joined into one payload ordered by precedence. Assembled, not blended: every passage keeps its own rank, origin and caveat."},
        {"id": "SEARCH_STRUCTURE", "label": "Structured output (LLM)", "kind": KIND_LLM, "lane": 6, "row": 1,
         "description": "The render schema is produced here, then checked: no unsourced drug, no invented citation, no uncited claim. A failed check discards the answer."},
        {"id": "SEARCH_RENDER", "label": "JSON to the client", "kind": KIND_END, "lane": 7, "row": 1,
         "description": "The structured answer, its citations, the filter's accepted AND rejected verdicts, and this trace."},
    ],
    "edges": [
        {"from": "SEARCH_QUERY", "to": "SEARCH_GUARD"},
        {"from": "SEARCH_GUARD", "to": "SEARCH_FANOUT"},
        {"from": "SEARCH_FANOUT", "to": "SEARCH_VECTOR", "parallel": True},
        {"from": "SEARCH_FANOUT", "to": "SEARCH_WEB", "parallel": True},
        {"from": "SEARCH_WEB", "to": "SEARCH_FILTER"},
        {"from": "SEARCH_VECTOR", "to": "SEARCH_COUPLE"},
        {"from": "SEARCH_FILTER", "to": "SEARCH_COUPLE"},
        {"from": "SEARCH_COUPLE", "to": "SEARCH_STRUCTURE"},
        {"from": "SEARCH_STRUCTURE", "to": "SEARCH_RENDER"},
    ],
}


def graphs() -> Dict[str, Any]:
    """Both declared graphs, for `/api/agents/graph`."""
    return {
        "pipelines": [INGESTION_GRAPH, SEARCH_GRAPH],
        "statuses": [STATUS_PENDING, STATUS_RUNNING, STATUS_OK, STATUS_SKIPPED,
                     STATUS_REFUSED, STATUS_FAILED, STATUS_DEGRADED],
        "kinds": [KIND_START, KIND_AGENT, KIND_DETERMINISTIC, KIND_LLM, KIND_STORE,
                  KIND_EXTERNAL, KIND_GUARD, KIND_END],
    }
