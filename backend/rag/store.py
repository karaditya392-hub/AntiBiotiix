"""
Vector store for guideline chunks (Spec §15).

Backend-agnostic by design. Vectors are held in a numpy matrix and persisted to
an .npz sidecar next to the chunk JSON; the query path is a single cosine
similarity, which is the same operation pgvector performs server-side. Migrating
to pgvector means replacing `search()` with a SQL query and leaving every caller
unchanged.

Current status is reported honestly by `backend_description()`: vector search is
implemented, the pgvector backend is pending the PostgreSQL migration.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from backend.rag.embeddings import EmbeddingBackend, get_backend

RAG_DIR = Path(__file__).parent.parent / "guidelines" / "data" / "rag"


class RetrievalBackendMismatch(RuntimeError):
    """
    The index cannot be queried with the embedding backend available here.

    Raised rather than returning no results, because "I cannot read my index" and
    "the corpus contains nothing relevant" are different statements and only one
    of them is about the guidelines.
    """


# How a chunk's `page` number should be described to a clinician.
#
# A page number is only a citation if it points into the official document. For a
# transcription the number is a page of the TRANSCRIPT, and rendering it as "p. 4"
# would invite a reader to look up page 4 of an edition where the passage may sit
# somewhere else entirely. Each kind therefore renders differently.
PAGE_OFFICIAL = "OFFICIAL_DOCUMENT_PAGE"
PAGE_TRANSCRIPT = "TRANSCRIPT_PAGE_NOT_OFFICIAL"
PAGE_NONE = "NO_PAGINATION"


@dataclass
class RetrievedChunk:
    document_id: str
    document_title: str
    issuing_org: str
    geographic_scope: str
    version: str
    publication_date: str
    source_url: str
    page: Optional[int]
    section: Optional[str]
    text: str
    score: float
    notes: str = ""
    source_type: str = "OFFICIAL_PDF"
    page_reference_kind: str = PAGE_OFFICIAL
    provenance_basis: str = "HASH_VERIFIED_PDF"

    def location_label(self) -> str:
        """Render the location so it cannot be mistaken for an official page."""
        if self.page_reference_kind == PAGE_OFFICIAL and self.page:
            loc = f"p. {self.page}"
        elif self.page_reference_kind == PAGE_TRANSCRIPT and self.page:
            loc = f"transcript p. {self.page} (NOT an official page of this edition)"
        else:
            loc = "no pagination (plain-text transcription)"
        return f"{self.section} ({loc})" if self.section else loc

    def to_citation(self) -> Dict[str, Any]:
        return {
            "document_title": self.document_title,
            "issuing_org": self.issuing_org,
            "geographic_scope": self.geographic_scope,
            "guideline_version": self.version,
            "publication_date": self.publication_date,
            "source_url": self.source_url,
            "section_page": self.location_label(),
            "page_reference_kind": self.page_reference_kind,
            "source_type": self.source_type,
            "provenance_basis": self.provenance_basis,
            "verbatim_passage": self.text,
            "retrieval_score": round(float(self.score), 4),
            "provenance_note": self.notes or None,
        }


class GuidelineVectorStore:
    def __init__(self, rag_dir: Optional[Path] = None) -> None:
        self.dir = Path(rag_dir) if rag_dir else RAG_DIR
        self.docs: Dict[str, Dict[str, Any]] = {}
        self.chunks: List[Dict[str, Any]] = []
        self.vocabulary: set = set()
        self.vocab_prefixes: set = set()
        self.matrix: Optional[np.ndarray] = None
        self.embedding_model: Optional[str] = None
        self.is_semantic: bool = False
        # Set when this machine could not load the model the committed index was
        # built with and the index was re-embedded in memory with a weaker one.
        self.degraded_from: Optional[str] = None
        self._lock = threading.Lock()

    # -- build -------------------------------------------------------------

    def build(self, backend: Optional[EmbeddingBackend] = None, persist: bool = True) -> int:
        """
        Embed every ingested chunk.

        `persist=False` rebuilds in memory only. That is what recovery from a
        backend mismatch uses: a machine that cannot load the semantic model must
        not overwrite the committed index with a lexical one, because the next
        machine that CAN load the model would then silently get lexical results.
        """
        self._load_chunks()
        if not self.chunks:
            return 0
        texts = [c["text"] for c in self.chunks]
        be = backend or get_backend()
        if hasattr(be, "fit") and not getattr(be, "_fitted", True):
            be.fit(texts)  # TF-IDF fallback must see the corpus first
        vecs = be.encode(texts)
        self.matrix = vecs
        self.embedding_model = be.name
        self.is_semantic = be.is_semantic
        if persist:
            np.savez_compressed(
                self.dir / "_vectors.npz",
                matrix=vecs,
                model=np.array([be.name]),
                semantic=np.array([be.is_semantic]),
            )
        return len(self.chunks)

    def ensure_queryable(self, backend: Optional[EmbeddingBackend] = None) -> Dict[str, Any]:
        """
        Guarantee the loaded index can actually answer a query on THIS machine.

        The committed index is built with the semantic model. A machine that
        cannot load that model -- not installed, or the weights are not cached and
        there is no network -- falls back to the lexical backend, and a store built
        with one model cannot be queried with another.

        Previously that mismatch made search() return nothing, which retrieval then
        reported as "no sufficiently relevant evidence". That is a false statement
        about the corpus: the evidence is present and the system simply could not
        read its own index. Silence caused by a broken tool must never be dressed
        up as a finding about the guidelines.

        So the index is rebuilt in memory with whatever backend is available, and
        the degradation is recorded so every answer can say it came from lexical
        rather than semantic retrieval.
        """
        be = backend or get_backend()
        with self._lock:
            if self.matrix is None or not self.chunks:
                return {"queryable": False, "reason": "No index or no chunks loaded."}

            if be.name == self.embedding_model:
                self.degraded_from = None
                return {"queryable": True, "rebuilt": False, "backend": be.name}

            built_with = self.embedding_model
            count = self.build(backend=be, persist=False)
            self.degraded_from = built_with
            return {
                "queryable": count > 0,
                "rebuilt": True,
                "backend": be.name,
                "index_built_with": built_with,
                "semantic": be.is_semantic,
            }

    def _load_chunks(self) -> None:
        self.docs, self.chunks = {}, []
        if not self.dir.exists():
            return
        for f in sorted(self.dir.glob("*.json")):
            payload = json.loads(f.read_text(encoding="utf-8"))
            doc = payload["document"]
            self.docs[doc["document_id"]] = doc
            self.chunks.extend(payload["chunks"])
        # Corpus vocabulary, used to detect query terms that name entities the
        # corpus has never heard of (see retrieve.unknown_entities).
        import re as _re
        vocab = set()
        for c in self.chunks:
            vocab.update(_re.findall(r"[a-z]{4,}", c["text"].lower()))
        self.vocabulary = vocab
        # Prefix index so morphological variants count as grounded:
        # "renally" -> "renal", "contraindication" -> "contraindications".
        # Without this, ordinary inflections are mistaken for unknown entities.
        prefixes = set()
        for w in vocab:
            for n in range(5, len(w) + 1):
                prefixes.add(w[:n])
        self.vocab_prefixes = prefixes

    # -- load --------------------------------------------------------------

    def load(self) -> bool:
        """Load chunks + persisted vectors. Returns False if unavailable."""
        with self._lock:
            self._load_chunks()
            vec_file = self.dir / "_vectors.npz"
            if not self.chunks or not vec_file.exists():
                self.matrix = None
                return False
            data = np.load(vec_file, allow_pickle=False)
            matrix = data["matrix"]
            if matrix.shape[0] != len(self.chunks):
                # Corpus changed since the vectors were built; refuse to serve a
                # misaligned index rather than return wrong citations.
                self.matrix = None
                return False
            self.matrix = matrix
            self.embedding_model = str(data["model"][0])
            self.is_semantic = bool(data["semantic"][0])
            return True

    @property
    def available(self) -> bool:
        return self.matrix is not None and len(self.chunks) > 0

    def backend_description(self) -> Dict[str, Any]:
        # Reports the backend actually in use on THIS machine, not the one the
        # committed index was built with. Those differ whenever the semantic model
        # cannot be loaded here, and reporting the recorded model in that case
        # told the caller retrieval was semantic while it was returning nothing.
        desc: Dict[str, Any] = {
            "available": self.available,
            "chunks": len(self.chunks),
            "documents": len(self.docs),
            "embedding_model": self.embedding_model,
            "semantic": self.is_semantic,
            "vector_backend": "in-process numpy cosine",
            "pgvector_status": "PENDING_POSTGRES_MIGRATION",
        }
        if self.degraded_from:
            desc["degraded"] = True
            desc["index_built_with"] = self.degraded_from
            desc["degradation_note"] = (
                f"The semantic model this index was built with ({self.degraded_from}) could "
                f"not be loaded on this machine, so the corpus was re-embedded in memory with "
                f"{self.embedding_model}. Retrieval is LEXICAL, not semantic: it matches wording "
                f"rather than meaning, so a passage phrased differently from the question may be "
                f"missed. Citations remain verbatim and correctly attributed. Install "
                f"sentence-transformers and cache the model to restore semantic retrieval."
            )
        return desc

    # -- query -------------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 5,
        document_ids: Optional[List[str]] = None,
        backend: Optional[EmbeddingBackend] = None,
    ) -> List[RetrievedChunk]:
        if not self.available:
            return []
        be = backend or get_backend()
        if be.name != self.embedding_model:
            # A store built with one model is not queryable with another. Returning
            # [] here is what made a broken index look like an empty corpus, so
            # recover first and only give up if that fails.
            state = self.ensure_queryable(be)
            if not state.get("queryable"):
                raise RetrievalBackendMismatch(
                    f"The guideline index was built with {self.embedding_model!r} but this "
                    f"machine loaded {be.name!r}, and it could not be re-embedded."
                )
        qv = be.encode([query])[0]
        sims = self.matrix @ qv

        idx = np.argsort(-sims)
        out: List[RetrievedChunk] = []
        for i in idx:
            c = self.chunks[int(i)]
            if document_ids and c["document_id"] not in document_ids:
                continue
            doc = self.docs.get(c["document_id"], {})
            out.append(
                RetrievedChunk(
                    document_id=c["document_id"],
                    document_title=doc.get("title", c["document_id"]),
                    issuing_org=doc.get("issuing_org", "unknown"),
                    geographic_scope=doc.get("geographic_scope", "unknown"),
                    version=doc.get("version", c.get("version", "unknown")),
                    publication_date=doc.get("publication_date", ""),
                    source_url=doc.get("source_url", ""),
                    page=c.get("page"),
                    section=c.get("section"),
                    text=c["text"],
                    score=float(sims[int(i)]),
                    notes=doc.get("notes", ""),
                    # Documents ingested before these fields existed are official
                    # hash-verified PDFs, which is what the defaults describe.
                    source_type=doc.get("source_type", "OFFICIAL_PDF"),
                    page_reference_kind=doc.get("page_reference_kind", PAGE_OFFICIAL),
                    provenance_basis=doc.get("provenance_basis", "HASH_VERIFIED_PDF"),
                )
            )
            if len(out) >= k:
                break
        return out


vector_store = GuidelineVectorStore()
vector_store.load()

# Resolve a backend mismatch once, at import, rather than on the first query.
#
# The committed index is built with the semantic model. A machine that cannot load
# it -- not installed, or the weights are not cached and there is no network --
# would otherwise have every search return nothing, which retrieval used to report
# as "no sufficiently relevant evidence": a false claim about the corpus caused by
# a tool failure. Re-embedding here means the feature works on any machine, and
# backend_description() reports the degradation so no answer is passed off as
# semantic when it is lexical.
if vector_store.available:
    try:
        vector_store.ensure_queryable()
    except Exception:  # pragma: no cover - never block startup on retrieval
        pass
