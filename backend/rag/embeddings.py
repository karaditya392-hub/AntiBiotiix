"""
Embedding backend for guideline retrieval (Spec §9, §15).

Two backends, selected by availability:

  1. sentence-transformers `all-MiniLM-L6-v2` (default) — local, offline after
     first download, deterministic for a fixed model version.
  2. scikit-learn TF-IDF (fallback) — zero download, deterministic, but LEXICAL
     not semantic. When this backend is active the model name recorded on every
     chunk says so, because a store built lexically must never be described as
     semantic search.

A store built with one backend is not queryable with another. The model name and
dimension are recorded on every chunk and checked at query time.
"""
from __future__ import annotations

import os
import threading
from typing import List, Optional, Sequence

import numpy as np

DEFAULT_MODEL = os.getenv("S11_EMBEDDING_MODEL", "all-MiniLM-L6-v2")


class EmbeddingBackend:
    """Base contract: encode text to a unit-normalised float32 matrix."""

    name: str = "unset"
    dim: int = 0
    is_semantic: bool = False

    def encode(self, texts: Sequence[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class SentenceTransformerBackend(EmbeddingBackend):
    is_semantic = True

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.name = f"sentence-transformers/{model_name}"
        # get_sentence_embedding_dimension was renamed in sentence-transformers 6;
        # support both so the ingester works across versions.
        get_dim = getattr(
            self._model, "get_embedding_dimension",
            self._model.get_sentence_embedding_dimension,
        )
        self.dim = int(get_dim())

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vecs = self._model.encode(
            list(texts),
            batch_size=64,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)


class TfidfBackend(EmbeddingBackend):
    """
    Deterministic lexical fallback. Honest about what it is: this is NOT semantic
    search, and the recorded model name makes that explicit downstream.
    """

    is_semantic = False

    def __init__(self, corpus: Optional[Sequence[str]] = None) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vec = TfidfVectorizer(
            lowercase=True, stop_words="english", ngram_range=(1, 2),
            max_features=40000, sublinear_tf=True,
        )
        self.name = "sklearn-tfidf-LEXICAL-NOT-SEMANTIC"
        self._fitted = False
        if corpus:
            self.fit(corpus)

    def fit(self, corpus: Sequence[str]) -> None:
        self._vec.fit(list(corpus))
        self._fitted = True
        self.dim = len(self._vec.vocabulary_)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("TF-IDF backend must be fitted on the corpus before encoding")
        m = self._vec.transform(list(texts)).astype(np.float32).toarray()
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return m / norms


_backend: Optional[EmbeddingBackend] = None
_lock = threading.Lock()


def get_backend(prefer_semantic: bool = True) -> EmbeddingBackend:
    """Return the process-wide embedding backend, loading it once."""
    global _backend
    with _lock:
        if _backend is not None:
            return _backend
        if prefer_semantic:
            try:
                _backend = SentenceTransformerBackend()
                return _backend
            except Exception:
                # Fall through to the lexical backend rather than failing the
                # whole application; retrieval degrades, rules are unaffected.
                pass
        _backend = TfidfBackend()
        return _backend


def reset_backend() -> None:
    """Test hook."""
    global _backend
    with _lock:
        _backend = None
