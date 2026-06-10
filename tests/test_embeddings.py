"""Tests for the dual-mode embedding module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from better_code_review_graph.embeddings import (
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
    semantic_search,
)
from better_code_review_graph.graph import GraphNode, GraphStore


@pytest.fixture(autouse=True)
def mock_qwen_backend(monkeypatch):
    """Mock Qwen3EmbedBackend to avoid real model downloads and inference."""

    class MockedQwen3EmbedBackend(Qwen3EmbedBackend):
        def __init__(self, model_name=None):
            self._model_name = model_name or "mocked/qwen3-embed"
            self._model = None

        @property
        def name(self) -> str:
            return f"local:{self._model_name}"

        def embed_texts(self, texts, dimensions=768):
            return [np.random.rand(dimensions or 768).tolist() for _ in texts]

        def embed_single(self, text, dimensions=768):
            return np.random.rand(dimensions or 768).tolist()

        def embed_single_query(self, text, dimensions=768):
            return np.random.rand(dimensions or 768).tolist()

        def check_available(self):
            return 768

    monkeypatch.setattr(
        "better_code_review_graph.embeddings.Qwen3EmbedBackend", MockedQwen3EmbedBackend
    )


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
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-..."}, clear=True):
            assert resolve_backend() == "cloud"

    def test_default_local(self):
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_backend() == "local"


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

    def test_check_available(self):
        backend = Qwen3EmbedBackend()
        dims = backend.check_available()
        assert dims > 0

    def test_embed_single(self):
        backend = Qwen3EmbedBackend()
        vector = backend.embed_single("hello world", dimensions=768)
        assert len(vector) == 768


# ---------------------------------------------------------------------------
# CloudEmbeddingBackend
# ---------------------------------------------------------------------------


class TestCloudEmbeddingBackend:
    def _mock_cohere_response(self, texts, dim=1024):
        mock_resp = MagicMock()
        mock_resp.embeddings.float_ = [
            np.random.rand(dim).tolist() for _ in range(len(texts))
        ]
        return mock_resp

    def test_cohere_v2_integration(self):
        """Test Cohere V2 SDK integration."""
        backend = CloudEmbeddingBackend(model="embed-english-v3.0", api_key="test-key")
        with patch("cohere.ClientV2") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.embed.return_value = self._mock_cohere_response(
                ["hello"], dim=768
            )

            vectors = backend.embed_texts(["hello"], dimensions=768)
            assert len(vectors) == 1
            assert len(vectors[0]) == 768
            mock_client.embed.assert_called_once()

    def test_retry_on_transient_error(self):
        """Backend should retry on 429/5xx errors."""
        backend = CloudEmbeddingBackend(api_key="test-key")
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Rate limit exceeded (429)")
            return self._mock_cohere_response(["test"], dim=768)

        with patch("cohere.ClientV2") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.embed.side_effect = side_effect

            with patch("time.sleep"):  # Skip actual delay
                vectors = backend.embed_texts(["test"], dimensions=768)
                assert len(vectors) == 1
                assert call_count == 2

    def test_dimensions_truncation(self):
        """Test that dimensions parameter truncates embeddings."""
        backend = CloudEmbeddingBackend(api_key="test-key")
        with patch("cohere.ClientV2") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.embed.return_value = self._mock_cohere_response(
                ["test"], dim=1024
            )
            vectors = backend.embed_texts(["test"], dimensions=768)
            assert len(vectors) == 1
            assert len(vectors[0]) == 768

    def test_api_key_resolution_from_env(self):
        """Test that API key is resolved per provider from env."""
        with patch.dict(os.environ, {"JINA_AI_API_KEY": "jina-key"}, clear=True):
            backend = CloudEmbeddingBackend(model="jina-embeddings-v3")
            assert backend._resolve_api_key() == "jina-key"

        with patch.dict(os.environ, {"GEMINI_API_KEY": "gem-key"}, clear=True):
            backend = CloudEmbeddingBackend(model="gemini-embedding-2")
            assert backend._resolve_api_key() == "gem-key"

        with patch.dict(os.environ, {"OPENAI_API_KEY": "oai-key"}, clear=True):
            backend = CloudEmbeddingBackend(model="text-embedding-3-large")
            assert backend._resolve_api_key() == "oai-key"

        with patch.dict(os.environ, {"COHERE_API_KEY": "co-key"}, clear=True):
            backend = CloudEmbeddingBackend(model="embed-multilingual-v3.0")
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
        assert store.count() == 0
        store.close()

    def test_embed_nodes_and_count(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)

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
        store.close()

    def test_embed_nodes_skips_files(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)

        nodes = [
            _make_node(kind="File", name="a.py", qualified_name="a.py"),
        ]
        count = store.embed_nodes(nodes)
        assert count == 0
        store.close()

    def test_embed_nodes_deduplicates(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)

        nodes = [
            _make_node(name="foo", qualified_name="a.py::foo"),
        ]
        count1 = store.embed_nodes(nodes)
        assert count1 == 1
        # Re-embed same node (no change) -- should skip
        count2 = store.embed_nodes(nodes)
        assert count2 == 0
        store.close()

    def test_search(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)

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
        # The firebase node should rank higher
        names = [qn for qn, _score in results]
        assert "auth.py::verify_firebase_token" in names
        store.close()

    def test_remove_node(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)

        nodes = [_make_node(name="foo", qualified_name="a.py::foo")]
        store.embed_nodes(nodes)
        assert store.count() == 1

        store.remove_node("a.py::foo")
        assert store.count() == 0
        store.close()

    def test_search_returns_empty_when_no_embeddings(self, tmp_path):
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)
        results = store.search("anything")
        assert results == []
        store.close()

    def test_fixed_768_dim_storage(self, tmp_path):
        """All embeddings should be stored at fixed 768 dimensions."""
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)

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
        store.close()

    def test_re_embeds_on_backend_change(self, tmp_path):
        """Changing backend name should trigger re-embedding."""
        db = tmp_path / "graph.db"
        backend = Qwen3EmbedBackend()
        store = EmbeddingStore(db, backend)

        nodes = [_make_node(name="foo", qualified_name="a.py::foo")]
        count1 = store.embed_nodes(nodes)
        assert count1 == 1
        store.close()

        # Open with a "different" backend by changing the backend_name
        store2 = EmbeddingStore(db, backend)
        # Manually override the stored provider to simulate switching
        store2._conn.execute("UPDATE embeddings SET provider = 'old_backend'")
        store2._conn.commit()

        count2 = store2.embed_nodes(nodes)
        assert count2 == 1  # re-embedded because provider changed
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
        _insert_file_and_functions(graph_store, "test.py", ["hello"])

        backend = Qwen3EmbedBackend()
        emb_store = EmbeddingStore(db_path, backend)
        count = embed_all_nodes(graph_store, emb_store)
        # File node is skipped, only "hello" function embedded
        assert count == 1
        assert emb_store.count() == 1

        emb_store.close()
        graph_store.close()


class TestSemanticSearch:
    def test_semantic_search_with_embeddings(self, tmp_path):
        db_path = tmp_path / "graph.db"
        graph_store = GraphStore(db_path)
        _insert_file_and_functions(
            graph_store, "app.py", ["auth_handler", "payment_process", "user_login"]
        )

        backend = Qwen3EmbedBackend()
        emb_store = EmbeddingStore(db_path, backend)
        embed_all_nodes(graph_store, emb_store)

        results = semantic_search("authentication", graph_store, emb_store, limit=3)
        assert len(results) >= 1
        # Should return dicts with similarity_score
        assert "similarity_score" in results[0]

        emb_store.close()
        graph_store.close()

    def test_semantic_search_fallback_to_keyword(self, tmp_path):
        """When no embeddings exist, falls back to keyword search."""
        db_path = tmp_path / "graph.db"
        graph_store = GraphStore(db_path)
        _insert_file_and_functions(graph_store, "test.py", ["my_function"])

        backend = Qwen3EmbedBackend()
        emb_store = EmbeddingStore(db_path, backend)
        # Don't embed -- should fallback to keyword
        results = semantic_search("my_function", graph_store, emb_store, limit=5)
        assert len(results) >= 1

        emb_store.close()
        graph_store.close()
