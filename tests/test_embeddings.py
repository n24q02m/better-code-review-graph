"""Tests for the dual-mode embedding module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.embeddings import (
    CloudEmbeddingBackend,
    EmbeddingStore,
    Qwen3EmbedBackend,
    _cosine_similarity,
    _decode_vector,
    _detect_embedding_provider,
    _encode_vector,
    _node_to_text,
    _strip_provider,
    embed_all_nodes,
    init_backend,
    resolve_backend,
    semantic_search,
)
from better_code_review_graph.graph import GraphNode, GraphStore

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

    def test_dimension_mismatch(self):
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0]
        assert _cosine_similarity(a, b) == 0.0


# ---------------------------------------------------------------------------
# Node to text
# ---------------------------------------------------------------------------


class TestNodeToText:
    def test_basic_function(self):
        node = _make_node()
        text = _node_to_text(node)
        assert "my_func" in text
        assert "function" in text
        assert "python" in text

    def test_method_with_parent(self):
        node = _make_node(parent_name="MyClass")
        text = _node_to_text(node)
        assert "in MyClass" in text

    def test_with_params_and_return_type(self):
        node = _make_node(params="(x: int, y: str)", return_type="bool")
        text = _node_to_text(node)
        assert "(x: int, y: str)" in text
        assert "returns bool" in text

    def test_file_node_no_kind(self):
        node = _make_node(kind="File", name="file.py")
        text = _node_to_text(node)
        assert "file.py" in text


# ---------------------------------------------------------------------------
# Backend auto-detection
# ---------------------------------------------------------------------------


class TestResolveBackend:
    def test_default_is_local(self):
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_backend() == "local"

    def test_cohere_api_key_triggers_cloud(self):
        with patch.dict(os.environ, {"COHERE_API_KEY": "test-key"}, clear=True):
            assert resolve_backend() == "cloud"

    def test_co_api_key_triggers_cloud(self):
        with patch.dict(os.environ, {"CO_API_KEY": "test-key"}, clear=True):
            assert resolve_backend() == "cloud"

    def test_jina_api_key_triggers_cloud(self):
        with patch.dict(os.environ, {"JINA_AI_API_KEY": "test-key"}, clear=True):
            assert resolve_backend() == "cloud"

    def test_gemini_api_key_triggers_cloud(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            assert resolve_backend() == "cloud"

    def test_google_api_key_triggers_cloud(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=True):
            assert resolve_backend() == "cloud"

    def test_openai_api_key_triggers_cloud(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            assert resolve_backend() == "cloud"

    def test_explicit_backend_overrides(self):
        with patch.dict(
            os.environ,
            {"EMBEDDING_BACKEND": "local", "COHERE_API_KEY": "test-key"},
            clear=True,
        ):
            assert resolve_backend() == "local"

        with patch.dict(os.environ, {"EMBEDDING_BACKEND": "cloud"}, clear=True):
            assert resolve_backend() == "cloud"

    def test_litellm_alias_resolves_to_cloud(self):
        with patch.dict(os.environ, {"EMBEDDING_BACKEND": "litellm"}, clear=True):
            assert resolve_backend() == "cloud"


# ---------------------------------------------------------------------------
# init_backend factory
# ---------------------------------------------------------------------------


class TestInitBackend:
    def test_local_backend(self):
        backend = init_backend("local")
        assert isinstance(backend, Qwen3EmbedBackend)

    def test_cloud_backend(self):
        backend = init_backend("cloud")
        assert isinstance(backend, CloudEmbeddingBackend)

    def test_litellm_backward_compat(self):
        backend = init_backend("litellm")
        assert isinstance(backend, CloudEmbeddingBackend)

    def test_auto_detect_local(self):
        with patch.dict(os.environ, {}, clear=True):
            backend = init_backend()
            assert isinstance(backend, Qwen3EmbedBackend)

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown backend"):
            init_backend("unknown_backend")


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


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------


class TestProviderDetection:
    def test_jina_prefix(self):
        assert _detect_embedding_provider("jina_ai/jina-embeddings-v3") == "jina"
        assert _detect_embedding_provider("jina-embeddings-v3") == "jina"

    def test_gemini_prefix(self):
        assert _detect_embedding_provider("gemini/gemini-embedding-2") == "gemini"
        assert _detect_embedding_provider("gemini-embedding-2-preview") == "gemini"

    def test_cohere_prefix(self):
        assert _detect_embedding_provider("embed-multilingual-v3.0") == "cohere"
        assert _detect_embedding_provider("cohere/embed-english-v3.0") == "cohere"

    def test_openai_prefix(self):
        assert _detect_embedding_provider("text-embedding-3-large") == "openai"
        assert _detect_embedding_provider("openai/text-embedding-3-small") == "openai"

    def test_fallback_jina_env(self):
        with patch.dict(os.environ, {"JINA_AI_API_KEY": "key"}, clear=True):
            assert _detect_embedding_provider("unknown-model") == "jina"

    def test_fallback_gemini_env(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "key"}, clear=True):
            assert _detect_embedding_provider("unknown-model") == "gemini"

    def test_fallback_google_env(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "key"}, clear=True):
            assert _detect_embedding_provider("unknown-model") == "gemini"

    def test_fallback_openai_env(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
            assert _detect_embedding_provider("unknown-model") == "openai"

    def test_fallback_default_cohere(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _detect_embedding_provider("unknown-model") == "cohere"

    def test_strip_provider(self):
        assert _strip_provider("gemini/model-name") == "model-name"
        assert _strip_provider("model-name") == "model-name"
        assert _strip_provider("jina_ai/jina-embeddings-v3") == "jina-embeddings-v3"


# ---------------------------------------------------------------------------
# CloudEmbeddingBackend (mocked, multi-provider)
# ---------------------------------------------------------------------------


class TestCloudEmbeddingBackend:
    @pytest.fixture(autouse=True)
    def _clean_cloud_env(self, monkeypatch):
        """Remove cloud keys so auto-selection falls back to Cohere default.

        Tests that patch ``cohere.ClientV2`` expect the backend's default
        provider to be Cohere. Without this fixture, a developer whose
        environment has ``JINA_AI_API_KEY`` set (e.g. after running an E2E
        relay submit) would see those tests pick Jina instead and fail.
        """
        for key in (
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
            "CO_API_KEY",
            "EMBEDDING_MODEL",
        ):
            monkeypatch.delenv(key, raising=False)

    def _mock_cohere_response(self, texts, dim=768):
        """Build a mock Cohere embed response."""
        mock_resp = MagicMock()
        mock_resp.embeddings.float_ = [[0.1] * dim for _ in range(len(texts))]
        return mock_resp

    def test_provider_auto_detection(self):
        backend = CloudEmbeddingBackend(model="jina-embeddings-v3", api_key="k")
        assert backend._provider == "jina"

        backend = CloudEmbeddingBackend(model="gemini-embedding-2", api_key="k")
        assert backend._provider == "gemini"

        backend = CloudEmbeddingBackend(model="text-embedding-3-large", api_key="k")
        assert backend._provider == "openai"

        backend = CloudEmbeddingBackend(model="embed-multilingual-v3.0", api_key="k")
        assert backend._provider == "cohere"

    def test_name_includes_provider(self):
        backend = CloudEmbeddingBackend(model="jina-embeddings-v3", api_key="k")
        assert "jina" in backend.name
        assert "cloud:" in backend.name

    def test_embed_cohere(self):
        backend = CloudEmbeddingBackend(api_key="test-key")
        with patch("cohere.ClientV2") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.embed.return_value = self._mock_cohere_response(["test"])
            vectors = backend.embed_texts(["test"], dimensions=768)
            assert len(vectors) == 1
            assert len(vectors[0]) == 768

    def test_embed_gemini(self):
        backend = CloudEmbeddingBackend(
            model="gemini-embedding-2-preview", api_key="test-key"
        )
        with patch(
            "better_code_review_graph.embeddings.CloudEmbeddingBackend._embed_gemini"
        ) as mock_embed:
            mock_embed.return_value = [[0.1] * 768]
            vectors = backend.embed_texts(["test"], dimensions=768)
            assert len(vectors) == 1
            assert len(vectors[0]) == 768

    def test_embed_openai(self):
        backend = CloudEmbeddingBackend(
            model="text-embedding-3-large", api_key="test-key"
        )
        with patch(
            "better_code_review_graph.embeddings.CloudEmbeddingBackend._embed_openai"
        ) as mock_embed:
            mock_embed.return_value = [[0.1] * 768]
            vectors = backend.embed_texts(["test"], dimensions=768)
            assert len(vectors) == 1
            assert len(vectors[0]) == 768

    def test_embed_jina(self):
        backend = CloudEmbeddingBackend(model="jina-embeddings-v3", api_key="test-key")
        with patch(
            "better_code_review_graph.embeddings.CloudEmbeddingBackend._embed_jina"
        ) as mock_embed:
            mock_embed.return_value = [[0.1] * 768]
            vectors = backend.embed_texts(["test"], dimensions=768)
            assert len(vectors) == 1
            assert len(vectors[0]) == 768

    def test_embed_texts_empty(self):
        backend = CloudEmbeddingBackend(api_key="test-key")
        vectors = backend.embed_texts([])
        assert vectors == []

    def test_embed_texts_multi_batch(self):
        backend = CloudEmbeddingBackend(api_key="test-key")
        texts = [f"text_{i}" for i in range(150)]
        with patch("cohere.ClientV2") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.embed.side_effect = lambda **kwargs: self._mock_cohere_response(
                kwargs["texts"]
            )
            vectors = backend.embed_texts(texts, dimensions=768)
            assert len(vectors) == 150
            # Should have been called twice (96 + 54)
            assert mock_client.embed.call_count == 2

    def test_embed_single(self):
        backend = CloudEmbeddingBackend(api_key="test-key")
        with patch("cohere.ClientV2") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.embed.return_value = self._mock_cohere_response(["test"])
            vector = backend.embed_single("test", dimensions=768)
            assert len(vector) == 768


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
