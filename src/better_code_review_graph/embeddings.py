"""Dual-mode embedding: local ONNX (default) + cloud (multi-provider).

Supports two backends:
- **local**: Local inference via qwen3-embed ONNX. Zero-config, ~570MB model
  download on first use. Default backend.
- **cloud**: Cloud embedding via native SDKs. Supports Jina, Gemini, OpenAI,
  and Cohere. Auto-detected from API key env vars with priority:
  jina > gemini > openai > cohere.

Backend selection (always returns a valid backend):
1. Explicit EMBEDDING_BACKEND env var
2. 'cloud' if any provider API key is set
3. 'local' (default, always available)

All embeddings are stored at fixed 768 dimensions (MRL truncation).
Switching backend does NOT invalidate existing vectors.
"""

from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any, Protocol

from .graph import GraphNode, GraphStore, node_to_dict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DIMS = 768  # Fixed storage dimension (MRL truncation)

# Retry config for transient errors (rate limits, 5xx, network).
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds, doubles each retry

_RETRYABLE_PATTERNS = (
    "rate limit",
    "rate_limit",
    "429",
    "quota",
    "too many requests",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection",
    "temporarily unavailable",
    "overloaded",
    "resource exhausted",
    "resource_exhausted",
)


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is transient and worth retrying."""
    msg = str(exc).lower()
    return any(p in msg for p in _RETRYABLE_PATTERNS)


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------


def _detect_embedding_provider(model: str) -> str:
    """Detect provider from model name. Returns 'jina', 'gemini', 'openai', or 'cohere'."""
    lower = model.lower()
    if lower.startswith("jina_ai/") or lower.startswith("jina"):
        return "jina"
    if lower.startswith("gemini/") or "gemini" in lower:
        return "gemini"
    if lower.startswith("embed-") or lower.startswith("cohere/"):
        return "cohere"
    if lower.startswith("text-embedding") or lower.startswith("openai/"):
        return "openai"
    # Fallback: check env vars in priority order
    if os.getenv("JINA_AI_API_KEY"):
        return "jina"
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "cohere"


def _strip_provider(model: str) -> str:
    """Strip provider prefix (e.g. 'gemini/model' -> 'model')."""
    if "/" in model:
        return model.split("/", 1)[1]
    return model


# ---------------------------------------------------------------------------
# Backend Protocol
# ---------------------------------------------------------------------------


class EmbeddingBackend(Protocol):  # pragma: no cover
    """Protocol for embedding backends."""

    def embed_texts(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed a batch of texts. Returns list of embedding vectors."""
        ...

    def embed_single(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a single text. Returns embedding vector."""
        ...

    def check_available(self) -> int:
        """Check if backend is available.

        Returns:
            Embedding dimensions if available, 0 if not.
        """
        ...


# ---------------------------------------------------------------------------
# Qwen3EmbedBackend (local ONNX)
# ---------------------------------------------------------------------------


class Qwen3EmbedBackend:
    """Local ONNX embedding via qwen3-embed (Qwen3-Embedding-0.6B).

    Uses last-token pooling with instruction-aware queries.
    Model is downloaded on first use (~0.57GB).
    Batch size is forced to 1 (static ONNX graph).
    """

    DEFAULT_MODEL = "n24q02m/Qwen3-Embedding-0.6B-ONNX"

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or self.DEFAULT_MODEL
        self._model = None

    @property
    def name(self) -> str:
        return f"local:{self._model_name}"

    def _get_model(self):
        """Lazy-load the embedding model.

        On first call, downloads the ONNX model (~570 MB) from HuggingFace
        if not already cached.
        """
        if self._model is None:
            from qwen3_embed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed_texts(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed texts using local ONNX model."""
        if not texts:
            return []

        model = self._get_model()
        kwargs: dict[str, Any] = {}
        if dimensions and dimensions > 0:
            kwargs["dim"] = dimensions
        embeddings = list(model.embed(texts, **kwargs))
        return [emb.tolist() for emb in embeddings]

    def embed_single(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a single text (document/passage)."""
        results = self.embed_texts([text], dimensions)
        return results[0]

    def embed_single_query(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a query with instruction prefix (asymmetric retrieval)."""
        model = self._get_model()
        kwargs: dict[str, Any] = {}
        if dimensions and dimensions > 0:
            kwargs["dim"] = dimensions
        result = list(model.query_embed(text, **kwargs))
        return result[0].tolist()

    def check_available(self) -> int:
        """Check if qwen3-embed is available."""
        try:
            model = self._get_model()
            result = list(model.embed(["test"]))
            if result:
                return len(result[0])
            return 0  # pragma: no cover
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Cloud Embedding Backend (multi-provider: Jina, Gemini, OpenAI, Cohere)
# ---------------------------------------------------------------------------


class CloudEmbeddingBackend:
    """Cloud embedding via native SDKs (Jina, Gemini, OpenAI, Cohere).

    Provider is auto-detected from the model name or env vars.
    Priority: jina > gemini > openai > cohere.
    """

    MAX_BATCH_SIZE = 96

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        self.model = model or os.getenv("EMBEDDING_MODEL", "embed-multilingual-v3.0")
        self.api_key = api_key
        self._provider = _detect_embedding_provider(self.model)
        self._bare_model = _strip_provider(self.model)

    @property
    def name(self) -> str:
        return f"cloud:{self._provider}:{self.model}"

    def _resolve_api_key(self) -> str:
        """Resolve API key for the current provider."""
        if self.api_key:
            return self.api_key
        if self._provider == "jina":
            return os.getenv("JINA_AI_API_KEY") or ""
        if self._provider == "gemini":
            return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        if self._provider == "openai":
            return os.getenv("OPENAI_API_KEY") or ""
        # cohere
        return os.getenv("COHERE_API_KEY") or os.getenv("CO_API_KEY") or ""

    def _call_provider(
        self, texts: list[str], dimensions: int | None = None
    ) -> list[list[float]]:
        """Route to the correct provider SDK."""
        if self._provider == "jina":
            return self._embed_jina(texts, dimensions)
        elif self._provider == "gemini":
            return self._embed_gemini(texts, dimensions)
        elif self._provider == "openai":
            return self._embed_openai(texts, dimensions)
        else:
            return self._embed_cohere(texts, dimensions)

    def _embed_jina(
        self, texts: list[str], dimensions: int | None = None
    ) -> list[list[float]]:
        """Embed via Jina AI (httpx, REST API)."""
        import httpx

        key = self._resolve_api_key()
        payload: dict[str, Any] = {
            "model": self._bare_model,
            "input": texts,
        }
        if dimensions:
            payload["dimensions"] = dimensions

        response = httpx.post(
            "https://api.jina.ai/v1/embeddings",
            json=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()["data"]
        data_sorted = sorted(data, key=lambda x: x["index"])
        return [d["embedding"] for d in data_sorted]

    def _embed_gemini(
        self, texts: list[str], dimensions: int | None = None
    ) -> list[list[float]]:
        """Embed via Google Gemini (google-genai SDK)."""
        from google import genai
        from google.genai import types

        key = self._resolve_api_key()
        client = genai.Client(api_key=key)

        config_kwargs: dict[str, Any] = {}
        if dimensions:
            config_kwargs["output_dimensionality"] = dimensions

        result = client.models.embed_content(
            model=self._bare_model,
            contents=texts,
            config=types.EmbedContentConfig(**config_kwargs) if config_kwargs else None,
        )

        embeddings = result.embeddings or []
        return [list(e.values or []) for e in embeddings]

    def _embed_openai(
        self, texts: list[str], dimensions: int | None = None
    ) -> list[list[float]]:
        """Embed via OpenAI SDK."""
        from openai import OpenAI

        key = self._resolve_api_key()
        client = OpenAI(api_key=key)

        kwargs: dict[str, Any] = {
            "model": self._bare_model,
            "input": texts,
        }
        if dimensions:
            kwargs["dimensions"] = dimensions

        response = client.embeddings.create(**kwargs)
        data = sorted(response.data, key=lambda x: x.index)
        return [d.embedding for d in data]

    def _embed_cohere(
        self, texts: list[str], dimensions: int | None = None
    ) -> list[list[float]]:
        """Embed via Cohere SDK (ClientV2)."""
        import cohere

        key = self._resolve_api_key()
        client = cohere.ClientV2(api_key=key)

        response = client.embed(
            model=self._bare_model,
            texts=texts,
            input_type="search_document",
            embedding_types=["float"],
            truncate="END",
        )
        embeddings: list[list[float]] = list(response.embeddings.float_ or [])
        if dimensions and embeddings and len(embeddings[0]) > dimensions:
            embeddings = [e[:dimensions] for e in embeddings]
        return embeddings

    def _embed_batch_inner(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed a single batch with retry logic for transient errors."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return self._call_provider(texts, dimensions)
            except Exception as e:
                last_exc = e
                if attempt < _MAX_RETRIES - 1 and _is_retryable(e):
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                    time.sleep(delay)
                else:
                    break

        raise last_exc  # type: ignore[misc]

    def embed_texts(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed texts with auto batch splitting."""
        if not texts:
            return []

        if len(texts) <= self.MAX_BATCH_SIZE:
            return self._embed_batch_inner(texts, dimensions)

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i : i + self.MAX_BATCH_SIZE]
            batch_result = self._embed_batch_inner(batch, dimensions)
            all_embeddings.extend(batch_result)

        return all_embeddings

    def embed_single(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a single text."""
        results = self.embed_texts([text], dimensions)
        return results[0]

    def check_available(self) -> int:
        """Check if the cloud model is available via test request."""
        try:
            embeddings = self._call_provider(["test"])
            if embeddings:
                return len(embeddings[0])
            return 0  # pragma: no cover
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def resolve_backend() -> str:
    """Auto-detect backend from env vars.

    Priority:
    1. Explicit EMBEDDING_BACKEND env var
    2. 'cloud' if any provider API key is set
    3. 'local' (default, always available)
    """
    explicit = os.getenv("EMBEDDING_BACKEND")
    if explicit:
        if explicit == "litellm":
            return "cloud"
        return explicit
    if any(
        os.getenv(k)
        for k in (
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        )
    ):
        return "cloud"
    return "local"


def init_backend(mode: str | None = None) -> EmbeddingBackend:
    """Create an embedding backend instance.

    Args:
        mode: 'local', 'cloud', 'litellm' (backward compat), or None (auto-detect).

    Returns:
        Initialized backend instance.
    """
    mode = mode or resolve_backend()
    if mode in ("cloud", "litellm"):
        return CloudEmbeddingBackend()
    if mode == "local":
        return Qwen3EmbedBackend()
    raise ValueError(f"Unknown backend type: {mode}")


# ---------------------------------------------------------------------------
# SQLite vector storage
# ---------------------------------------------------------------------------

_EMBEDDINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    qualified_name TEXT PRIMARY KEY,
    vector BLOB NOT NULL,
    text_hash TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown'
);
"""


def _encode_vector(vec: list[float]) -> bytes:
    """Encode a float vector as a compact binary blob."""
    return struct.pack(f"{len(vec)}f", *vec)


def _decode_vector(blob: bytes) -> tuple[float, ...]:
    """Decode a binary blob back to a float vector."""
    n = len(blob) // 4  # 4 bytes per float32
    return struct.unpack(f"{n}f", blob)


def _cosine_similarity(
    a: list[float] | tuple[float, ...],
    b: list[float] | tuple[float, ...],
    norm_a: float | None = None,
) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector.
        norm_a: Optional precalculated Euclidean norm of ``a`` to avoid
            redundant recalculation in hot loops.
    """
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    # math.sumprod computes dot product entirely in C (Python 3.12+)
    dot = math.sumprod(a, b)
    # math.hypot calculates the Euclidean norm efficiently in C
    n_a = norm_a if norm_a is not None else math.hypot(*a)
    n_b = math.hypot(*b)
    if n_a == 0 or n_b == 0:
        return 0.0
    return dot / (n_a * n_b)


def _node_to_text(node: GraphNode) -> str:
    """Convert a node to a searchable text representation."""
    parts = [node.name]
    if node.kind != "File":
        parts.append(node.kind.lower())
    if node.parent_name:
        parts.append(f"in {node.parent_name}")
    if node.params:
        parts.append(node.params)
    if node.return_type:
        parts.append(f"returns {node.return_type}")
    if node.language:
        parts.append(node.language)
    return " ".join(parts)


class EmbeddingStore:
    """Manages vector embeddings for graph nodes in SQLite.

    Uses a fixed 768-dim storage via MRL truncation. The backend name is
    tracked per row so that switching backends triggers re-embedding.
    """

    def __init__(
        self, db_path: str | Path, backend: EmbeddingBackend | None = None
    ) -> None:
        self.backend = backend
        self.available = backend is not None
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_EMBEDDINGS_SCHEMA)

        # Migration for existing DBs missing the provider column
        try:
            self._conn.execute("SELECT provider FROM embeddings LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.execute(
                "ALTER TABLE embeddings ADD COLUMN provider "
                "TEXT NOT NULL DEFAULT 'unknown'"
            )

        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _get_backend_name(self) -> str:
        if self.backend is None:
            return "none"
        return getattr(self.backend, "name", "unknown")

    def embed_nodes(self, nodes: list[GraphNode], batch_size: int = 64) -> int:
        """Compute and store embeddings for a list of nodes.

        Skips File nodes and nodes whose text + provider haven't changed.
        """
        if not self.backend:
            return 0

        provider_name = self._get_backend_name()

        # Filter to nodes that need embedding
        to_embed: list[tuple[GraphNode, str, str]] = []

        for node in nodes:
            if node.kind == "File":
                continue
            text = _node_to_text(node)
            text_hash = hashlib.sha256(text.encode()).hexdigest()

            existing = self._conn.execute(
                "SELECT text_hash, provider FROM embeddings WHERE qualified_name = ?",
                (node.qualified_name,),
            ).fetchone()

            if (
                existing
                and existing["text_hash"] == text_hash
                and existing["provider"] == provider_name
            ):
                continue
            to_embed.append((node, text, text_hash))

        if not to_embed:
            return 0

        # Encode in batches
        texts = [t for _, t, _ in to_embed]
        vectors = self.backend.embed_texts(texts, dimensions=_DEFAULT_DIMS)

        for (node, _text, text_hash), vec in zip(to_embed, vectors, strict=True):
            blob = _encode_vector(vec)
            self._conn.execute(
                """INSERT OR REPLACE INTO embeddings
                   (qualified_name, vector, text_hash, provider)
                   VALUES (?, ?, ?, ?)""",
                (node.qualified_name, blob, text_hash, provider_name),
            )

        self._conn.commit()
        return len(to_embed)

    def search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        """Search for nodes by semantic similarity.

        Uses embed_single_query if available (asymmetric retrieval),
        otherwise falls back to embed_single.
        """
        if not self.backend:
            return []

        # Count embeddings first
        count = self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        if count == 0:
            return []

        # Embed query -- use query-specific method if available
        if hasattr(self.backend, "embed_single_query"):
            query_vec = self.backend.embed_single_query(query, dimensions=_DEFAULT_DIMS)
        else:
            query_vec = self.backend.embed_single(query, dimensions=_DEFAULT_DIMS)

        # Brute-force cosine similarity scan with precalculated query norm
        scored: list[tuple[str, float]] = []
        query_norm = math.hypot(*query_vec)
        cursor = self._conn.execute("SELECT qualified_name, vector FROM embeddings")
        chunk_size = 500
        while True:
            rows = cursor.fetchmany(chunk_size)
            if not rows:
                break
            for row in rows:
                vec = _decode_vector(row["vector"])
                sim = _cosine_similarity(query_vec, vec, norm_a=query_norm)
                scored.append((row["qualified_name"], sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def remove_node(self, qualified_name: str) -> None:
        self._conn.execute(
            "DELETE FROM embeddings WHERE qualified_name = ?", (qualified_name,)
        )
        self._conn.commit()

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

    def clear(self) -> None:
        """Remove all embeddings."""
        self._conn.execute("DELETE FROM embeddings")
        self._conn.commit()


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def embed_all_nodes(graph_store: GraphStore, embedding_store: EmbeddingStore) -> int:
    """Embed all non-file nodes in the graph."""
    if not embedding_store.available:
        return 0

    all_files = graph_store.get_all_files()
    all_nodes = graph_store.get_nodes_by_files(all_files)

    return embedding_store.embed_nodes(all_nodes)


def semantic_search(
    query: str,
    graph_store: GraphStore,
    embedding_store: EmbeddingStore,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search nodes using vector similarity, falling back to keyword search."""
    if embedding_store.available and embedding_store.count() > 0:
        results = embedding_store.search(query, limit=limit)
        # Batch fetch all nodes to avoid N+1 queries
        qns = [r[0] for r in results]
        node_list = graph_store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in node_list}

        output = []
        for qn, score in results:
            if qn in node_map:
                d = node_to_dict(node_map[qn])
                d["similarity_score"] = round(score, 4)
                output.append(d)
        return output

    # Fallback to keyword search
    nodes = graph_store.search_nodes(query, limit=limit)
    return [node_to_dict(n) for n in nodes]
