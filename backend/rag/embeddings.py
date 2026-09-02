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

import threading
from typing import List, Optional, Sequence

import numpy as np

from backend import config

# Read through backend.config, which loads the single .env at the repository
# root. Not os.getenv() here: a model id read at its own call site is a model id
# nobody can find when they need to know what the index was built with.
DEFAULT_MODEL = config.EMBEDDING_MODEL


class EmbeddingBackend:
    """Base contract: encode text to a unit-normalised float32 matrix."""

    name: str = "unset"
    dim: int = 0
    is_semantic: bool = False

    def encode(self, texts: Sequence[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def encode_query(self, texts: Sequence[str]) -> np.ndarray:
        """
        Embed text that is being used as a QUERY rather than stored as a passage.

        Symmetric models (MiniLM, TF-IDF) embed both sides identically, so the
        default delegates. Asymmetric retrieval models -- the NVIDIA embedqa
        family, and the Qwen3-Embedding models with their query instruction --
        produce a DIFFERENT vector for the same text depending on which side of
        the search it sits on, and embedding a query as a passage silently costs
        retrieval accuracy. Silently is the problem: nothing errors, scores just
        get worse, and the relevance floor then refuses questions it should
        answer. So the distinction is part of the backend contract rather than
        something each call site has to remember.
        """
        return self.encode(texts)


class SentenceTransformerBackend(EmbeddingBackend):
    """
    Any sentence-transformers model, named in .env as EMBEDDING_MODEL.

    The default is all-MiniLM-L6-v2 (~90 MB, CPU, offline after first download).
    Stronger retrieval models -- the Qwen3-Embedding family in particular -- are a
    one-line change here, but they are a HARDWARE decision, not a config
    preference, and the numbers are not close:

        all-MiniLM-L6-v2        ~ 90 MB    384 dim   CPU, minutes to embed
        Qwen/Qwen3-Embedding-0.6B ~1.2 GB  1024 dim   CPU, tens of minutes
        Qwen/Qwen3-Embedding-4B   ~8 GB    2560 dim   GPU strongly preferred
        Qwen/Qwen3-Embedding-8B  ~16 GB    4096 dim   GPU required in practice

    Whatever is chosen, the model name is recorded on the index and checked at
    query time, so the store refuses a mismatch rather than returning neighbours
    computed by a different model. Changing this value therefore requires
    scripts/migrate_embeddings.py, which re-embeds and verifies before swapping.
    """

    is_semantic = True

    def __init__(self, model_name: Optional[str] = None) -> None:
        from sentence_transformers import SentenceTransformer

        model_name = model_name or DEFAULT_MODEL
        self._model = SentenceTransformer(model_name, trust_remote_code=True)
        # Bare name for the historical MiniLM value so the committed index keeps
        # loading; fully qualified for anything else, because "Qwen3-Embedding-8B"
        # without its namespace does not identify a model.
        self.name = (f"sentence-transformers/{model_name}"
                     if "/" not in model_name else model_name)
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


class NvidiaEmbeddingBackend(EmbeddingBackend):
    """
    Hosted embeddings through the NVIDIA endpoint configured in .env.

    Semantic, and stronger than MiniLM on clinical text -- at the cost of the
    property MiniLM has and this does not: MiniLM runs offline on CPU. A district
    hospital with intermittent connectivity keeps working on the local backend and
    stops retrieving on this one. That is a deployment decision, not a quality
    one, which is why both backends stay in the tree and .env picks.

    An index built here CANNOT be queried by the local backend or the reverse. The
    store enforces that by recorded model name (see store.py) -- so switching
    EMBEDDING_BACKEND without re-running scripts/migrate_embeddings.py takes
    retrieval down rather than silently returning wrong neighbours. That failure
    is loud on purpose.
    """

    is_semantic = True

    def __init__(self, model_name: Optional[str] = None) -> None:
        from backend import config

        if not config.NVIDIA_API_KEY:
            raise RuntimeError("EMBEDDING_BACKEND=nvidia but NVIDIA_API_KEY is not set in .env")
        self._model = model_name or config.NVIDIA_EMBEDDING_MODEL
        self._url = f"{config.NVIDIA_BASE_URL.rstrip('/')}/embeddings"
        self._key = config.NVIDIA_API_KEY
        # The recorded name carries the model id, because an index is only
        # queryable by the exact model that built it and "nvidia" alone would not
        # catch a silent model swap on the vendor side.
        self.name = f"nvidia:{self._model}"
        self.dim = 0

    def encode_query(self, texts: Sequence[str]) -> np.ndarray:
        return self.encode(texts, input_type="query")

    def encode(self, texts: Sequence[str], input_type: str = "passage") -> np.ndarray:
        import httpx

        batch, out = 64, []
        items = list(texts)
        for i in range(0, len(items), batch):
            chunk = items[i:i + batch]
            response = httpx.post(
                self._url,
                headers={"Authorization": f"Bearer {self._key}", "Accept": "application/json"},
                json={
                    "input": chunk,
                    "model": self._model,
                    "input_type": input_type,
                    "encoding_format": "float",
                },
                timeout=120.0,
            )
            response.raise_for_status()
            rows = response.json()["data"]
            out.extend(row["embedding"] for row in sorted(rows, key=lambda r: r.get("index", 0)))

        matrix = np.asarray(out, dtype=np.float32)
        if matrix.size == 0:
            return matrix
        self.dim = int(matrix.shape[1])
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms


_backend: Optional[EmbeddingBackend] = None
_lock = threading.Lock()


def get_backend(prefer_semantic: bool = True) -> EmbeddingBackend:
    """
    Return the process-wide embedding backend, loading it once.

    Selection order: EMBEDDING_BACKEND from .env, then local sentence-transformers,
    then the lexical fallback. A configured NVIDIA backend that cannot start falls
    back rather than taking the application down -- retrieval degrades, and the
    recorded model name makes the degradation visible downstream. The clinical
    rules are unaffected either way; they never consult this module.
    """
    global _backend
    with _lock:
        if _backend is not None:
            return _backend

        from backend import config

        if config.EMBEDDING_BACKEND == "nvidia":
            try:
                _backend = NvidiaEmbeddingBackend()
                return _backend
            except Exception:
                pass

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
