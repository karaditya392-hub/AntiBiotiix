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


@dataclass
class RetrievedChunk:
    document_id: str
    document_title: str
    issuing_org: str
    geographic_scope: str
    version: str
    publication_date: str
    source_url: str
    page: int
    section: Optional[str]
    text: str
    score: float
    notes: str = ""

    def to_citation(self) -> Dict[str, Any]:
        loc = f"p. {self.page}"
        if self.section:
            loc = f"{self.section} ({loc})"
        return {
            "document_title": self.document_title,
            "issuing_org": self.issuing_org,
            "geographic_scope": self.geographic_scope,
            "guideline_version": self.version,
            "publication_date": self.publication_date,
            "source_url": self.source_url,
            "section_page": loc,
            "verbatim_passage": self.text,
            "retrieval_score": round(float(self.score), 4),
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
        self._lock = threading.Lock()

    # -- build -------------------------------------------------------------

    def build(self, backend: Optional[EmbeddingBackend] = None) -> int:
        """Embed every ingested chunk and persist the vectors."""
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
        np.savez_compressed(
            self.dir / "_vectors.npz",
            matrix=vecs,
            model=np.array([be.name]),
            semantic=np.array([be.is_semantic]),
        )
        return len(self.chunks)

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
        return {
            "available": self.available,
            "chunks": len(self.chunks),
            "documents": len(self.docs),
            "embedding_model": self.embedding_model,
            "semantic": self.is_semantic,
            "vector_backend": "in-process numpy cosine",
            "pgvector_status": "PENDING_POSTGRES_MIGRATION",
        }

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
            # A store built with one model is not queryable with another.
            return []
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
                    page=c["page"],
                    section=c.get("section"),
                    text=c["text"],
                    score=float(sims[int(i)]),
                    notes=doc.get("notes", ""),
                )
            )
            if len(out) >= k:
                break
        return out


vector_store = GuidelineVectorStore()
vector_store.load()
