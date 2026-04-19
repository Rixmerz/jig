"""fastembed-based embedding service.

Singleton client with lazy model loading. The model runs in-process via
ONNX Runtime; no daemon, no container, no HTTP.

Default model: BAAI/bge-large-en-v1.5 (1024D). Override via `JIG_EMBED_MODEL` env.

Usage:
    from jig.core.embeddings import get_embedder
    emb = get_embedder()
    vec = emb.embed_one("some text")              # list[float], length = emb.dim
    vecs = emb.embed_many(["a", "b"])             # list[list[float]]

Availability:
    emb.available  → False if fastembed is not installed; embed_* returns None.
    Callers must handle None gracefully (fall back to BM25 or skip semantic scoring).
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

log = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-large-en-v1.5"
MODEL_DIMS: dict[str, int] = {
    "BAAI/bge-large-en-v1.5": 1024,
    "BAAI/bge-base-en-v1.5": 768,
    "BAAI/bge-small-en-v1.5": 384,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
}


def resolve_model() -> str:
    return os.environ.get("JIG_EMBED_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def model_slug(name: str | None = None) -> str:
    """Stable, filesystem-safe slug used as cache key."""
    n = name or resolve_model()
    return hashlib.sha1(n.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


class FastembedClient:
    """Thin wrapper around fastembed.TextEmbedding with lazy model load."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or resolve_model()
        self._model = None
        self._lock = threading.Lock()
        self._load_error: Exception | None = None

    @property
    def available(self) -> bool:
        """True if the model is usable (or can be loaded)."""
        if self._load_error is not None:
            return False
        try:
            import fastembed  # noqa: F401
        except ImportError:
            return False
        return True

    @property
    def dim(self) -> int:
        return MODEL_DIMS.get(self.model_name, 768)

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        if self._load_error is not None:
            return False
        with self._lock:
            if self._model is not None:
                return True
            try:
                from fastembed import TextEmbedding

                log.info("[jig.embeddings] loading model %s (first run may download)", self.model_name)
                self._model = TextEmbedding(model_name=self.model_name)
                return True
            except Exception as e:  # pragma: no cover
                log.warning("[jig.embeddings] failed to load model %s: %s", self.model_name, e)
                self._load_error = e
                return False

    def embed_one(self, text: str) -> list[float] | None:
        if not self._ensure_model():
            return None
        assert self._model is not None
        for vec in self._model.embed([text]):
            return [float(x) for x in vec]
        return None

    def embed_many(self, texts: "Iterable[str]") -> list[list[float]] | None:
        if not self._ensure_model():
            return None
        assert self._model is not None
        out: list[list[float]] = []
        for vec in self._model.embed(list(texts)):
            out.append([float(x) for x in vec])
        return out


@lru_cache(maxsize=1)
def get_embedder() -> FastembedClient:
    return FastembedClient()


__all__ = [
    "DEFAULT_MODEL",
    "FastembedClient",
    "MODEL_DIMS",
    "get_embedder",
    "model_slug",
    "resolve_model",
]
