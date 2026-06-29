"""Tests for the dual-mode embedding module."""

from __future__ import annotations

import os
import sqlite3
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from better_code_review_graph.embeddings import (
    _DEFAULT_DIMS,
    CloudEmbeddingBackend,
    EmbeddingStore,
    Qwen3EmbedBackend,
    _cosine_similarity,
    _decode_vector,
    _detect_embedding_provider,
    _encode_vector,
    _strip_provider,
    embed_all_nodes,
    init_backend,
    resolve_backend,
    resolve_embedding_chain,
    semantic_search,
)
from better_code_review_graph.graph import GraphNode, GraphStore


@pytest.fixture(autouse=True)
def mock_qwen_inference():
    """Mock Qwen3EmbedBackend model to avoid real downloads and inference."""
    with patch(
        "better_code_review_graph.embeddings.Qwen3EmbedBackend._get_model"
    ) as mock_get:
        mock_model = MagicMock()
        mock_get.return_value = mock_model
        # Mock embed and query_embed to return random vectors of requested dimension
        mock_model.embed.side_effect = lambda texts, **kwargs: [
            np.random.rand(kwargs.get("dim", 768)) for _ in texts
        ]
        mock_model.query_embed.side_effect = lambda text, **kwargs: [
            np.random.rand(kwargs.get("dim", 768))
        ]
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(**kwargs) -> GraphNode:
    defaults = {
        "id": 1,
        "kind": "Function",
        "name": "my_func",
        "qualified_name": "file.py::my_func",
        "file_path": "file.py",
        "line_start": 1,
        "line_end": 10,
        "language": "python",
        "parent_name": None,
        "params": None,
        "return_type": None,
        "is_test": False,
        "file_hash": None,
        "extra": {},
    }
    defaults.update(kwargs)
    return GraphNode(**defaults)


# ---------------------------------------------------------------------------
# Vector encoding
# ---------------------------------------------------------------------------


class TestVectorEncoding:
    def test_roundtrip(self):
        original = [1.0, 2.5, -3.14, 0.0, 100.0]
        blob = _encode_vector(original)
        decoded = _decode_vector(blob)
        assert len(decoded) == len(original)
        for a, b in zip(original, decoded, strict=True):
            assert abs(a - b) < 1e-5

    def test_empty_vector(self):
        blob = _encode_vector([])
        decoded = _decode_vector(blob)
        assert decoded == ()

    def test_blob_size(self):
        vec = [1.0, 2.0, 3.0]
        blob = _encode_vector(vec)
        assert len(blob) == 12  # 3 floats * 4 bytes each


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_different_lengths(self):
        a = [1.0, 2.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0


# ---------------------------------------------------------------------------
# Provider Detection
# ---------------------------------------------------------------------------


class TestProviderDetection:
    def test_detect_by_prefix(self):
        assert _detect_embedding_provider("jina-embeddings-v3") == "jina"
        assert _detect_embedding_provider("jina_ai/v3") == "jina"
        assert _detect_embedding_provider("gemini-embedding-2") == "gemini"
        assert _detect_embedding_provider("gemini/v2") == "gemini"
        assert _detect_embedding_provider("openai/text-embedding-3") == "openai"
        assert _detect_embedding_provider("text-embedding-3-large") == "openai"
        assert _detect_embedding_provider("embed-multilingual-v3.0") == "cohere"
        assert _detect_embedding_provider("cohere/v3") == "cohere"

    def test_detect_by_env_var(self):
        with patch.dict(os.environ, {"JINA_AI_API_KEY": "test"}, clear=True):
            assert _detect_embedding_provider("unknown") == "jina"
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}, clear=True):
            assert _detect_embedding_provider("unknown") == "gemini"
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test"}, clear=True):
            assert _detect_embedding_provider("unknown") == "gemini"
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
            assert _detect_embedding_provider("unknown") == "openai"

    def test_strip_provider(self):
        assert _strip_provider("gemini/embedding-v1") == "embedding-v1"
        assert _strip_provider("model-name") == "model-name"


# ---------------------------------------------------------------------------
# Backend Selection
# ---------------------------------------------------------------------------


class TestResolveBackend:
    def test_explicit_env_var(self):
        with patch.dict(os.environ, {"EMBEDDING_BACKEND": "cloud"}, clear=True):
            assert resolve_backend() == "cloud"
        with patch.dict(os.environ, {"EMBEDDING_BACKEND": "litellm"}, clear=True):
            assert resolve_backend() == "cloud"
        with patch.dict(os.environ, {"EMBEDDING_BACKEND": "local"}, clear=True):
            assert resolve_backend() == "local"

    def test_auto_detect_cloud(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            assert resolve_backend() == "cloud"

    def test_default_local(self):
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_backend() == "local"

    def test_unavailable_when_local_disabled_and_no_chain(self):
        """DISABLE_LOCAL_EMBED + empty chain -> 'unavailable' (NOT forced)."""
        with patch.dict(os.environ, {"DISABLE_LOCAL_EMBED": "true"}, clear=True):
            assert resolve_backend() == "unavailable"

    def test_cloud_wins_even_when_local_disabled(self):
        with patch.dict(
            os.environ,
            {
                "DISABLE_LOCAL_EMBED": "true",
                "EMBEDDING_MODELS": "gemini/gemini-embedding-001",
            },
            clear=True,
        ):
            assert resolve_backend() == "cloud"

    def test_init_backend_unavailable_raises_clear_error(self):
        import pytest

        from better_code_review_graph.embeddings import init_backend

        with patch.dict(os.environ, {"DISABLE_LOCAL_EMBED": "true"}, clear=True):
            with pytest.raises(ValueError, match="DISABLE_LOCAL_EMBED"):
                init_backend()


# ---------------------------------------------------------------------------
# Embedding model chain (per-task model-chain redesign)
# ---------------------------------------------------------------------------


class TestResolveEmbeddingChain:
    def test_explicit_models_from_env(self, monkeypatch):
        monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
        monkeypatch.setenv(
            "EMBEDDING_MODELS",
            "jina_ai/jina-embeddings-v5-text-small,gemini/gemini-embedding-001",
        )
        chain = resolve_embedding_chain()
        assert chain == [
            "jina_ai/jina-embeddings-v5-text-small",
            "gemini/gemini-embedding-001",
        ]
        assert resolve_backend() == "cloud"

    def test_explicit_models_strip_and_skip_empties(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODELS", " openai/text-embedding-3-large , , ")
        assert resolve_embedding_chain() == ["openai/text-embedding-3-large"]

    def test_empty_no_keys_is_local(self, monkeypatch):
        for k in (
            "EMBEDDING_MODELS",
            "EMBEDDING_MODEL",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        assert resolve_embedding_chain() == []
        assert resolve_backend() == "local"

    def test_default_chain_key_gated(self, monkeypatch):
        """Default keeps only models whose provider key is configured."""
        for k in (
            "EMBEDDING_BACKEND",
            "EMBEDDING_MODELS",
            "EMBEDDING_MODEL",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        # Only the openai model survives key-gating.
        assert resolve_embedding_chain() == ["openai/text-embedding-3-large"]
        assert resolve_backend() == "cloud"

    def test_default_chain_gemini_alias(self, monkeypatch):
        """GOOGLE_API_KEY satisfies the gemini model's key requirement."""
        for k in (
            "EMBEDDING_MODELS",
            "EMBEDDING_MODEL",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "g-test")
        assert resolve_embedding_chain() == ["gemini/gemini-embedding-001"]

    def test_default_chain_cohere_alias(self, monkeypatch):
        """CO_API_KEY satisfies the cohere model's key requirement."""
        for k in (
            "EMBEDDING_MODELS",
            "EMBEDDING_MODEL",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("CO_API_KEY", "co-test")
        assert resolve_embedding_chain() == ["cohere/embed-multilingual-v3.0"]

    def test_legacy_embedding_model_honored(self, monkeypatch):
        for k in (
            "EMBEDDING_BACKEND",
            "EMBEDDING_MODELS",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("EMBEDDING_MODEL", "gemini/gemini-embedding-001")
        assert resolve_embedding_chain() == ["gemini/gemini-embedding-001"]
        assert resolve_backend() == "cloud"

    def test_explicit_models_wins_over_legacy(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODELS", "openai/text-embedding-3-large")
        monkeypatch.setenv("EMBEDDING_MODEL", "gemini/gemini-embedding-001")
        assert resolve_embedding_chain() == ["openai/text-embedding-3-large"]

    def test_legacy_backend_env_honored(self, monkeypatch):
        for k in (
            "EMBEDDING_MODELS",
            "EMBEDDING_MODEL",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("EMBEDDING_BACKEND", "cloud")
        assert resolve_backend() == "cloud"
        monkeypatch.setenv("EMBEDDING_BACKEND", "litellm")
        assert resolve_backend() == "cloud"
        monkeypatch.setenv("EMBEDDING_BACKEND", "local")
        assert resolve_backend() == "local"

    def test_cloud_backend_uses_first_chain_model(self, monkeypatch):
        for k in (
            "EMBEDDING_MODEL",
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("EMBEDDING_MODELS", "gemini/gemini-embedding-001")
        backend = CloudEmbeddingBackend()
        assert backend.model == "gemini/gemini-embedding-001"


class TestInitBackend:
    def test_local_backend(self):
        with patch.dict(os.environ, {"EMBEDDING_BACKEND": "local"}, clear=True):
            backend = init_backend()
            assert isinstance(backend, Qwen3EmbedBackend)

    def test_cloud_backend(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
            backend = init_backend()
            assert isinstance(backend, CloudEmbeddingBackend)

    def test_auto_detect_local(self):
        with patch.dict(os.environ, {}, clear=True):
            backend = init_backend()
            assert isinstance(backend, Qwen3EmbedBackend)

    def test_invalid_mode(self):
        with pytest.raises(ValueError, match="Unknown backend type"):
            init_backend(mode="invalid")


# ---------------------------------------------------------------------------
# Qwen3EmbedBackend (local ONNX)
# ---------------------------------------------------------------------------


class TestQwen3EmbedBackend:
    def test_embed_produces_768_dim(self):
        backend = Qwen3EmbedBackend()
        vectors = backend.embed_texts(["hello world"], dimensions=768)
        assert len(vectors) == 1
        assert len(vectors[0]) == 768

    def test_embed_multiple_texts(self):
        backend = Qwen3EmbedBackend()
        vectors = backend.embed_texts(["hello", "world"], dimensions=768)
        assert len(vectors) == 2
        for v in vectors:
            assert len(v) == 768

    def test_embed_empty_list(self):
        backend = Qwen3EmbedBackend()
        vectors = backend.embed_texts([])
        assert vectors == []

    def test_embed_single(self):
        backend = Qwen3EmbedBackend()
        vector = backend.embed_single("hello world", dimensions=768)
        assert len(vector) == 768


# ---------------------------------------------------------------------------
# CloudEmbeddingBackend
# ---------------------------------------------------------------------------


def _embedding_response(texts, dim=1024, as_dict=False):
    """Build a fake ``mcp_core.llm.embedding`` response.

    ``resp.data`` items are either pydantic-like objects (``.index`` /
    ``.embedding``) or plain dicts depending on ``as_dict``.
    """
    resp = MagicMock()
    items = []
    for i in range(len(texts)):
        vec = np.random.rand(dim).tolist()
        if as_dict:
            items.append({"index": i, "embedding": vec})
        else:
            item = MagicMock()
            item.index = i
            item.embedding = vec
            items.append(item)
    resp.data = items
    return resp


class TestCloudEmbeddingBackend:
    def test_litellm_passthrough_integration(self):
        """Cloud backend dispatches through mcp_core.llm.embedding."""
        with patch.dict(os.environ, {}, clear=True):
            backend = CloudEmbeddingBackend(
                model="cohere/embed-english-v3.0", api_key="test-key"
            )
            with patch("mcp_core.llm.embedding") as mock_embed:
                mock_embed.return_value = _embedding_response(["hello"], dim=768)
                vectors = backend.embed_texts(["hello"], dimensions=768)
                assert len(vectors) == 1
                assert len(vectors[0]) == 768
                mock_embed.assert_called_once()
                call_kwargs = mock_embed.call_args.kwargs
                assert call_kwargs["model"] == "cohere/embed-english-v3.0"
                assert call_kwargs["input"] == ["hello"]
                assert call_kwargs["dimensions"] == 768
                # Cohere passes input_type through kwargs.
                assert call_kwargs["input_type"] == "search_document"
                # Explicit api_key forwarded; empty api_base normalised to None.
                assert call_kwargs["api_key"] == "test-key"
                assert call_kwargs["api_base"] is None

    def test_embedding_parse_dict_shape(self):
        """resp.data items as plain dicts are parsed + sorted by index."""
        with patch.dict(os.environ, {}, clear=True):
            backend = CloudEmbeddingBackend(
                model="openai/text-embedding-3-large", api_key="k"
            )
            resp = MagicMock()
            # Out-of-order indices to prove sorting.
            resp.data = [
                {"index": 1, "embedding": [0.2, 0.2]},
                {"index": 0, "embedding": [0.1, 0.1]},
            ]
            with patch("mcp_core.llm.embedding", return_value=resp):
                vectors = backend.embed_texts(["a", "b"])
            assert vectors == [[0.1, 0.1], [0.2, 0.2]]

    def test_embedding_parse_pydantic_shape(self):
        """resp.data items as pydantic-like objects are parsed + sorted."""
        with patch.dict(os.environ, {}, clear=True):
            backend = CloudEmbeddingBackend(
                model="openai/text-embedding-3-large", api_key="k"
            )
            item0 = MagicMock()
            item0.index = 0
            item0.embedding = [0.1, 0.1]
            item1 = MagicMock()
            item1.index = 1
            item1.embedding = [0.2, 0.2]
            resp = MagicMock()
            resp.data = [item1, item0]  # out of order
            with patch("mcp_core.llm.embedding", return_value=resp):
                vectors = backend.embed_texts(["a", "b"])
            assert vectors == [[0.1, 0.1], [0.2, 0.2]]

    def test_embedding_none_data_guard(self):
        """resp.data=None must not crash -- returns empty list."""
        with patch.dict(os.environ, {}, clear=True):
            backend = CloudEmbeddingBackend(model="openai/text-embedding-3-large")
            resp = MagicMock()
            resp.data = None
            with patch("mcp_core.llm.embedding", return_value=resp):
                vectors = backend.embed_texts(["a"])
            assert vectors == []

    def test_litellm_model_mapping(self):
        """_litellm_model maps bare names to provider/model strings."""
        with patch.dict(os.environ, {}, clear=True):
            # Jina bare -> jina_ai/ prefix
            b = CloudEmbeddingBackend(model="jina-embeddings-v3", api_key="k")
            assert b._litellm_model() == "jina_ai/jina-embeddings-v3"
            # Gemini bare -> gemini/ prefix
            b = CloudEmbeddingBackend(model="gemini-embedding-001", api_key="k")
            assert b._litellm_model() == "gemini/gemini-embedding-001"
            # Cohere bare -> cohere/ prefix
            b = CloudEmbeddingBackend(model="embed-multilingual-v3.0", api_key="k")
            assert b._litellm_model() == "cohere/embed-multilingual-v3.0"
            # OpenAI bare -> passthrough unchanged
            b = CloudEmbeddingBackend(model="text-embedding-3-large", api_key="k")
            assert b._litellm_model() == "text-embedding-3-large"
            # Already-prefixed -> unchanged
            b = CloudEmbeddingBackend(model="gemini/gemini-embedding-001", api_key="k")
            assert b._litellm_model() == "gemini/gemini-embedding-001"

    def test_embedding_api_base_from_env(self):
        """EMBEDDING_API_BASE env is forwarded as api_base."""
        with patch.dict(
            os.environ, {"EMBEDDING_API_BASE": "https://proxy.example/v1"}, clear=True
        ):
            backend = CloudEmbeddingBackend(model="text-embedding-3-large", api_key="k")
            with patch("mcp_core.llm.embedding") as mock_embed:
                mock_embed.return_value = _embedding_response(["x"], dim=4)
                backend.embed_texts(["x"])
            assert mock_embed.call_args.kwargs["api_base"] == "https://proxy.example/v1"

    def test_retry_on_transient_error(self):
        """Backend should retry on 429/5xx errors."""
        with patch.dict(os.environ, {}, clear=True):
            backend = CloudEmbeddingBackend(
                model="cohere/embed-english-v3.0", api_key="test-key"
            )
            call_count = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("Rate limit exceeded (429)")
                return _embedding_response(["test"], dim=768)

            with patch("mcp_core.llm.embedding", side_effect=side_effect):
                with patch("time.sleep"):  # Skip actual delay
                    vectors = backend.embed_texts(["test"], dimensions=768)
                    assert len(vectors) == 1
                    assert call_count == 2

    def test_dimensions_truncation(self):
        """Test that dimensions parameter truncates embeddings locally."""
        with patch.dict(os.environ, {}, clear=True):
            backend = CloudEmbeddingBackend(
                model="cohere/embed-english-v3.0", api_key="test-key"
            )
            with patch("mcp_core.llm.embedding") as mock_embed:
                # Provider returns 1024 dims; backend truncates to 768.
                mock_embed.return_value = _embedding_response(["test"], dim=1024)
                vectors = backend.embed_texts(["test"], dimensions=768)
                assert len(vectors) == 1
                assert len(vectors[0]) == 768

    def test_api_key_resolution_from_env(self):
        """Test that API key is resolved per provider from env."""
        with patch.dict(os.environ, {"JINA_AI_API_KEY": "jina-key"}, clear=True):
            backend = CloudEmbeddingBackend(model="jina/v3")
            assert backend._resolve_api_key() == "jina-key"

        with patch.dict(os.environ, {"GEMINI_API_KEY": "gem-key"}, clear=True):
            backend = CloudEmbeddingBackend(model="gemini/embedding-v1")
            assert backend._resolve_api_key() == "gem-key"

        with patch.dict(os.environ, {"OPENAI_API_KEY": "oai-key"}, clear=True):
            backend = CloudEmbeddingBackend(model="openai/text-embedding-3-large")
            assert backend._resolve_api_key() == "oai-key"

        with patch.dict(os.environ, {"COHERE_API_KEY": "co-key"}, clear=True):
            backend = CloudEmbeddingBackend(model="cohere/embed-multilingual-v3.0")
            assert backend._resolve_api_key() == "co-key"

    def test_explicit_api_key_overrides_env(self):
        """Explicit api_key param takes priority over env."""
        with patch.dict(os.environ, {"COHERE_API_KEY": "env-key"}, clear=True):
            backend = CloudEmbeddingBackend(api_key="explicit-key")
            assert backend._resolve_api_key() == "explicit-key"


# ---------------------------------------------------------------------------
# EmbeddingStore
# ---------------------------------------------------------------------------


class TestEmbeddingStore:
    def test_store_initializes(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)
        try:
            assert store.count() == 0
        finally:
            store.close()

    def test_embed_nodes_and_count(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [
                _make_node(
                    name="foo",
                    qualified_name="a.py::foo",
                    file_path="a.py",
                ),
                _make_node(
                    name="bar",
                    qualified_name="b.py::bar",
                    file_path="b.py",
                ),
            ]
            count = store.embed_nodes(nodes)
            assert count == 2
            assert store.count() == 2
        finally:
            store.close()

    def test_embed_nodes_skips_files(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [
                _make_node(kind="File", name="a.py", qualified_name="a.py"),
            ]
            count = store.embed_nodes(nodes)
            assert count == 0
        finally:
            store.close()

    def test_embed_nodes_deduplicates(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [
                _make_node(name="foo", qualified_name="a.py::foo"),
            ]
            count1 = store.embed_nodes(nodes)
            assert count1 == 1
            # Re-embed same node (no change) -- should skip
            count2 = store.embed_nodes(nodes)
            assert count2 == 0
        finally:
            store.close()

    def test_search(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [
                _make_node(
                    name="verify_firebase_token",
                    qualified_name="auth.py::verify_firebase_token",
                    language="python",
                ),
                _make_node(
                    name="process_payment",
                    qualified_name="payment.py::process_payment",
                    language="python",
                ),
            ]
            store.embed_nodes(nodes)

            results = store.search("firebase authentication", limit=2)
            assert len(results) >= 1
            names = [qn for qn, _score in results]
            assert "auth.py::verify_firebase_token" in names
        finally:
            store.close()

    def test_remove_node(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [_make_node(name="foo", qualified_name="a.py::foo")]
            store.embed_nodes(nodes)
            assert store.count() == 1

            store.remove_node("a.py::foo")
            assert store.count() == 0
        finally:
            store.close()

    def test_search_returns_empty_when_no_embeddings(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)
        try:
            results = store.search("anything")
            assert results == []
        finally:
            store.close()

    def test_fixed_768_dim_storage(self, tmp_path):
        """All embeddings should be stored at fixed 768 dimensions."""
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [_make_node(name="foo", qualified_name="a.py::foo")]
            store.embed_nodes(nodes)

            # Read raw vector from DB and verify dimension
            row = store._conn.execute(
                "SELECT vector FROM embeddings WHERE qualified_name = ?",
                ("a.py::foo",),
            ).fetchone()
            assert row is not None
            vec = _decode_vector(row["vector"])
            assert len(vec) == 768
        finally:
            store.close()

    def test_search_filters_by_active_provider(self, tmp_path):
        """search() must only score rows of the active provider.

        Switching embedding providers must NOT mix vectors from different
        models in one cosine ranking. Rows stored under a different provider
        than the active backend must be excluded from the scan.
        """
        db = tmp_path / "graph.db"
        # No embed_single_query attr -> search() uses embed_single fallback.
        backend = MagicMock(spec=["name", "embed_single", "embed_texts"])
        backend.name = "cloud:openai:openai/text-embedding-3-large"
        # Deterministic query vector so cosine is well-defined.
        backend.embed_single.return_value = [1.0] * _DEFAULT_DIMS

        store = EmbeddingStore(db, backend)
        try:
            # Two rows under DIFFERENT providers, identical vectors.
            vec_blob = _encode_vector([1.0] * _DEFAULT_DIMS)
            store._conn.execute(
                "INSERT INTO embeddings "
                "(qualified_name, vector, text_hash, provider) "
                "VALUES (?, ?, ?, ?)",
                ("active.py::keep", vec_blob, "h1", backend.name),
            )
            store._conn.execute(
                "INSERT INTO embeddings "
                "(qualified_name, vector, text_hash, provider) "
                "VALUES (?, ?, ?, ?)",
                ("other.py::drop", vec_blob, "h2", "cloud:cohere:cohere/embed-v3"),
            )
            store._conn.commit()

            results = store.search("anything", limit=10)
            names = [qn for qn, _score in results]
            assert "active.py::keep" in names
            assert "other.py::drop" not in names
        finally:
            store.close()

    def test_re_embeds_on_backend_change(self, tmp_path):
        """Changing backend name should trigger re-embedding."""
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)
        try:
            nodes = [_make_node(name="foo", qualified_name="a.py::foo")]
            count1 = store.embed_nodes(nodes)
            assert count1 == 1
        finally:
            store.close()

        # Open with a "different" backend by changing the backend_name
        store2 = EmbeddingStore(db, backend)
        try:
            # Manually override the stored provider to simulate switching
            store2._conn.execute("UPDATE embeddings SET provider = 'old_backend'")
            store2._conn.commit()

            count2 = store2.embed_nodes(nodes)
            assert count2 == 1  # re-embedded because provider changed
        finally:
            store2.close()


# ---------------------------------------------------------------------------
# embed_all_nodes + semantic_search (integration)
# ---------------------------------------------------------------------------


def _insert_file_and_functions(
    graph_store, file_path, function_names, language="python"
):
    """Helper: insert a File node and Function nodes into the graph store."""
    from better_code_review_graph.parser import NodeInfo

    # File node is required for get_all_files() to find the file
    graph_store.upsert_node(
        NodeInfo(
            kind="File",
            name=file_path,
            file_path=file_path,
            line_start=1,
            line_end=100,
            language=language,
        )
    )
    for name in function_names:
        graph_store.upsert_node(
            NodeInfo(
                kind="Function",
                name=name,
                file_path=file_path,
                line_start=1,
                line_end=5,
                language=language,
                params="()",
            )
        )
    graph_store.commit()


class TestEmbedAllNodes:
    def test_embed_all_nodes(self, tmp_path):
        db_path = tmp_path / "graph.db"
        graph_store = GraphStore(db_path)
        try:
            _insert_file_and_functions(graph_store, "test.py", ["hello"])

            backend = Qwen3EmbedBackend()
            emb_store = EmbeddingStore(db_path, backend)
            try:
                count = embed_all_nodes(graph_store, emb_store)
                # File node is skipped, only "hello" function embedded
                assert count == 1
                assert emb_store.count() == 1
            finally:
                emb_store.close()
        finally:
            graph_store.close()


class TestSemanticSearch:
    def test_semantic_search_with_embeddings(self, tmp_path):
        db_path = tmp_path / "graph.db"
        graph_store = GraphStore(db_path)
        try:
            _insert_file_and_functions(
                graph_store, "app.py", ["auth_handler", "payment_process", "user_login"]
            )

            backend = Qwen3EmbedBackend()
            emb_store = EmbeddingStore(db_path, backend)
            try:
                embed_all_nodes(graph_store, emb_store)

                results = semantic_search(
                    "authentication", graph_store, emb_store, limit=3
                )
                assert len(results) >= 1
                # Should return dicts with similarity_score
                assert "similarity_score" in results[0]
            finally:
                emb_store.close()
        finally:
            graph_store.close()

    def test_semantic_search_fallback_to_keyword(self, tmp_path):
        """When no embeddings exist, falls back to keyword search."""
        db_path = tmp_path / "graph.db"
        graph_store = GraphStore(db_path)
        try:
            _insert_file_and_functions(graph_store, "test.py", ["my_function"])

            backend = Qwen3EmbedBackend()
            emb_store = EmbeddingStore(db_path, backend)
            try:
                # Don't embed -- should fallback to keyword
                results = semantic_search(
                    "my_function", graph_store, emb_store, limit=5
                )
                assert len(results) >= 1
            finally:
                emb_store.close()
        finally:
            graph_store.close()

    def test_migration_adds_provider_column(self, tmp_path):
        """Test that the provider column is added if it's missing (migration path)."""
        db = tmp_path / "migration.db"

        # 1. Create a DB with the old schema (missing provider column)
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE embeddings (
                qualified_name TEXT PRIMARY KEY,
                vector BLOB NOT NULL,
                text_hash TEXT NOT NULL
            )
        """)
        conn.close()

        # 2. Instantiate EmbeddingStore, which should trigger the migration
        backend = MagicMock(spec=["name"])
        backend.name = "test_backend"
        store = EmbeddingStore(db, backend)

        try:
            # 3. Verify the provider column exists and has the default value
            # We'll insert a row to test it
            vec_blob = _encode_vector([0.1] * _DEFAULT_DIMS)
            store._conn.execute(
                "INSERT INTO embeddings (qualified_name, vector, text_hash) "
                "VALUES (?, ?, ?)",
                ("test.py::func", vec_blob, "hash1"),
            )
            store._conn.commit()

            row = store._conn.execute(
                "SELECT provider FROM embeddings WHERE qualified_name = ?",
                ("test.py::func",),
            ).fetchone()
            assert row is not None
            assert row["provider"] == "unknown"
        finally:
            store.close()


class TestEmbeddingStoreExtra:
    def test_migration_adds_provider_column(self, tmp_path):
        """Test that the provider column is added if it's missing (migration path)."""
        db = tmp_path / "migration.db"
        import sqlite3

        conn = sqlite3.connect(str(db))
        # Create table without provider column
        conn.execute(
            "CREATE TABLE embeddings (qualified_name TEXT PRIMARY KEY, vector BLOB, text_hash TEXT)"
        )
        conn.close()

        backend = MagicMock(spec=["name"])
        backend.name = "test"
        store = EmbeddingStore(db, backend)
        try:
            # Verify column exists and migration didn't crash
            store._conn.execute("SELECT provider FROM embeddings LIMIT 1")
        finally:
            store.close()

    def test_migration_handles_existing_column(self, tmp_path):
        """Test that the migration handles the case where the column already exists."""
        db = tmp_path / "existing.db"
        import sqlite3

        conn = sqlite3.connect(str(db))
        # Create table WITH provider column
        conn.execute(
            "CREATE TABLE embeddings (qualified_name TEXT PRIMARY KEY, vector BLOB, text_hash TEXT, provider TEXT)"
        )
        conn.close()

        backend = MagicMock(spec=["name"])
        backend.name = "test"
        store = EmbeddingStore(db, backend)
        try:
            # Should not crash
            store._conn.execute("SELECT provider FROM embeddings LIMIT 1")
        finally:
            store.close()

    def test_migration_operational_error_mocked(self):
        """Specifically test the OperationalError catch using mocks to satisfy rationale."""
        import sqlite3

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            # Raise OperationalError when trying to ALTER (simulates column already exists)
            mock_conn.execute.side_effect = sqlite3.OperationalError(
                "duplicate column name: provider"
            )

            backend = MagicMock(spec=["name"])
            backend.name = "test"
            from better_code_review_graph.embeddings import EmbeddingStore

            # Should not raise exception
            EmbeddingStore(":memory:", backend)

            # Verify ALTER was attempted
            calls = [call[0][0] for call in mock_conn.execute.call_args_list]
            assert any("ALTER TABLE embeddings ADD COLUMN provider" in c for c in calls)
            assert mock_conn.commit.called

    def test_embedding_store_no_backend(self, tmp_path):
        """Coverage for EmbeddingStore methods when no backend is provided."""
        db = tmp_path / "no_backend.db"
        store = EmbeddingStore(db, backend=None)
        try:
            assert store._get_backend_name() == "none"
            assert store.embed_nodes([]) == 0
            assert store.search("query") == []
            store.clear()
        finally:
            store.close()

    def test_embed_all_nodes_no_backend(self, tmp_path):
        """Coverage for embed_all_nodes when embedding_store is not available."""
        db = tmp_path / "no_backend_all.db"
        gs = GraphStore(db)
        es = EmbeddingStore(db, backend=None)
        try:
            assert not es.available
            assert embed_all_nodes(gs, es) == 0
        finally:
            es.close()
            gs.close()

    def test_node_to_text_full(self):
        """Coverage for _node_to_text with all fields populated."""
        from better_code_review_graph.embeddings import _node_to_text

        node = MagicMock(spec=GraphNode)
        node.name = "func"
        node.kind = "Function"
        node.parent_name = "Class"
        node.params = "(a, b)"
        node.return_type = "int"
        node.language = "python"
        text = _node_to_text(node)
        assert "func" in text
        assert "function" in text
        assert "in Class" in text
        assert "(a, b)" in text
        assert "returns int" in text
        assert "python" in text

    def test_is_retryable(self):
        """Coverage for _is_retryable utility."""
        from better_code_review_graph.embeddings import _is_retryable

        assert _is_retryable(Exception("rate limit exceeded"))
        assert _is_retryable(Exception("503 Service Unavailable"))
        assert not _is_retryable(Exception("fatal error"))

    def test_semantic_search_stale_embedding(self, tmp_path):
        """Coverage for semantic_search branch where embedding exists but node is missing from graph."""
        db = tmp_path / "stale.db"
        gs = GraphStore(db)
        # Add one node so semantic_search doesn't just return early due to empty graph
        from better_code_review_graph.parser import NodeInfo

        gs.upsert_node(
            NodeInfo(
                kind="Function",
                name="func1",
                file_path="test.py",
                line_start=1,
                line_end=5,
            )
        )
        gs.commit()

        backend = MagicMock(spec=["name", "embed_single", "embed_texts"])
        backend.name = "test"
        backend.embed_single.return_value = [0.1] * _DEFAULT_DIMS

        es = EmbeddingStore(db, backend)
        try:
            # Manually insert a stale embedding for a non-existent node
            vec_blob = _encode_vector([0.1] * _DEFAULT_DIMS)
            es._conn.execute(
                "INSERT INTO embeddings (qualified_name, vector, text_hash, provider) "
                "VALUES (?, ?, ?, ?)",
                ("non_existent::node", vec_blob, "h", "test"),
            )
            es._conn.commit()

            # Search should find the stale embedding but skip it in results as it's not in node_map
            results = semantic_search("query", gs, es)
            assert all(r.get("qualified_name") != "non_existent::node" for r in results)
        finally:
            es.close()
            gs.close()
