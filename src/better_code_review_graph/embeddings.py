"""Dual-mode embedding: local ONNX (default) + LiteLLM cloud.

Supports two backends:
- **local**: Local inference via qwen3-embed ONNX. Zero-config, ~570MB model
  download on first use. Default backend.
- **litellm**: Cloud providers via LiteLLM (Gemini, OpenAI, Cohere, etc.).
  Auto-detected from API_KEYS or LITELLM_PROXY_URL env vars.

Backend selection (always returns a valid backend):
1. Explicit EMBEDDING_BACKEND env var
2. 'litellm' if API keys or proxy URL are configured
3. 'local' (default, always available)

All embeddings are stored at fixed 768 dimensions (MRL truncation).
Switching backend does NOT invalidate existing vectors.
"""

from __future__ import annotations

import hashlib
import logging
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
# LiteLLM Backend (cloud)
# ---------------------------------------------------------------------------


class LiteLLMBackend:
    """Cloud embedding via LiteLLM (Gemini, OpenAI, Cohere, etc.)."""

    MAX_BATCH_SIZE = 100

    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
    ):
        self.model = model or os.getenv(
            "EMBEDDING_MODEL", "gemini/gemini-embedding-001"
        )
        self.api_base = api_base or os.getenv("LITELLM_PROXY_URL")
        self.api_key = api_key or os.getenv("LITELLM_PROXY_KEY")
        self._setup_litellm()

    @property
    def name(self) -> str:
        return f"litellm:{self.model}"

    def _setup_litellm(self) -> None:
        """Silence LiteLLM logging and configure API keys from API_KEYS env."""
        os.environ.setdefault("LITELLM_LOG", "ERROR")
        import litellm

        litellm.suppress_debug_info = True  # type: ignore[assignment]
        litellm.set_verbose = False
        logging.getLogger("LiteLLM").setLevel(logging.ERROR)
        logging.getLogger("LiteLLM").handlers = [logging.NullHandler()]

        # Parse API_KEYS env var: "ENV_NAME:value,ENV_NAME:value"
        api_keys_str = os.getenv("API_KEYS", "")
        if api_keys_str:
            for pair in api_keys_str.split(","):
                pair = pair.strip()
                if ":" in pair:
                    env_name, value = pair.split(":", 1)
                    os.environ.setdefault(env_name.strip(), value.strip())

    def _embed_batch_inner(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed a single batch with retry logic for transient errors."""
        from litellm import embedding as litellm_embedding

        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
        }
        if dimensions:
            kwargs["dimensions"] = dimensions
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = litellm_embedding(**kwargs)
                data = sorted(response.data, key=lambda x: x["index"])
                return [d["embedding"] for d in data]
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
        """Check if the LiteLLM model is available via test request."""
        try:
            from litellm import embedding as litellm_embedding

            kwargs: dict[str, Any] = {
                "model": self.model,
                "input": ["test"],
                "encoding_format": "float",
            }
            if self.api_base:
                kwargs["api_base"] = self.api_base
            if self.api_key:
                kwargs["api_key"] = self.api_key
            response = litellm_embedding(**kwargs)
            if response.data:
                return len(response.data[0]["embedding"])
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
    2. 'litellm' if LITELLM_PROXY_URL or API_KEYS are set
    3. 'local' (default, always available)
    """
    explicit = os.getenv("EMBEDDING_BACKEND")
    if explicit:
        return explicit
    if os.getenv("LITELLM_PROXY_URL") or os.getenv("API_KEYS"):
        return "litellm"
    return "local"


def init_backend(mode: str | None = None) -> EmbeddingBackend:
    """Create an embedding backend instance.

    Args:
        mode: 'local', 'litellm', or None (auto-detect).

    Returns:
        Initialized backend instance.
    """
    mode = mode or resolve_backend()
    if mode == "litellm":
        return LiteLLMBackend()
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


def _decode_vector(blob: bytes) -> list[float]:
    """Decode a binary blob back to a float vector."""
    n = len(blob) // 4  # 4 bytes per float32
    return list(struct.unpack(f"{n}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


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

        # Brute-force cosine similarity scan
        scored: list[tuple[str, float]] = []
        cursor = self._conn.execute("SELECT qualified_name, vector FROM embeddings")
        chunk_size = 500
        while True:
            rows = cursor.fetchmany(chunk_size)
            if not rows:
                break
            for row in rows:
                vec = _decode_vector(row["vector"])
                sim = _cosine_similarity(query_vec, vec)
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


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def embed_all_nodes(graph_store: GraphStore, embedding_store: EmbeddingStore) -> int:
    """Embed all non-file nodes in the graph."""
    if not embedding_store.available:
        return 0

    all_files = graph_store.get_all_files()
    all_nodes: list[GraphNode] = []
    for f in all_files:
        all_nodes.extend(graph_store.get_nodes_by_file(f))

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
        output = []
        for qn, score in results:
            node = graph_store.get_node(qn)
            if node:
                d = node_to_dict(node)
                d["similarity_score"] = round(score, 4)
                output.append(d)
        return output

    # Fallback to keyword search
    nodes = graph_store.search_nodes(query, limit=limit)
    return [node_to_dict(n) for n in nodes]
