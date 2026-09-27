"""Exact Cohere dimensions and persisted index/query compatibility; no live calls."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from better_code_review_graph.credential_state import _current_sub
from better_code_review_graph.embeddings import (
    CloudEmbeddingBackend,
    EmbeddingStore,
    _encode_vector,
)
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo


@pytest.fixture(autouse=True)
def isolated_subject(monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    token = _current_sub.set(None)
    yield
    _current_sub.reset(token)


def _transport(monkeypatch, vectors):
    """Patch hull's OpenAICompatClient so cell checks stay live; returns the fake class."""
    import hull_core.providers.openai_spec as spec

    class _FakeClient:
        instances = []
        call_args_list = []  # SimpleNamespace(args, kwargs) per embeddings() call

        def __init__(self, cell, auth_mode="no-auth"):
            self.cell = cell
            _FakeClient.instances.append(self)

        async def embeddings(self, texts, dimensions=None, **extra):
            from types import SimpleNamespace

            _FakeClient.call_args_list.append(
                SimpleNamespace(args=(None, texts, dimensions), kwargs=dict(extra))
            )
            return [list(v) for v in vectors]

        async def aclose(self):
            return None

    _FakeClient.call_args_list = []
    monkeypatch.setattr(spec, "OpenAICompatClient", _FakeClient)
    monkeypatch.setenv("HULL_EMBED_API_KEY", "sk-test")
    return _FakeClient


def _response(*vectors):
    # Parsed provider output: _post_embeddings now owns HTTP + parse.
    return [list(v) for v in vectors]


def test_unsupported_cohere_width_is_rejected_without_dispatch(monkeypatch):
    monkeypatch.setenv("HULL_EMBED_API_KEY", "sk-test")
    backend = CloudEmbeddingBackend(model="cohere/embed-v4.0")
    with patch("hull_core.providers.openai_spec.OpenAICompatClient") as dispatch:
        with pytest.raises(ValueError, match="requires dimensions"):
            backend.embed_texts(["hello"], dimensions=768)
    dispatch.assert_not_called()


@pytest.mark.parametrize("wrong_width", [768, 1536])
def test_provider_width_mismatch_never_coerces_or_persists(
    tmp_path, monkeypatch, wrong_width
):
    backend = CloudEmbeddingBackend(model="cohere/embed-v4.0")
    graph = GraphStore(str(tmp_path / "graph.db"))
    store = EmbeddingStore(tmp_path / "graph.db", backend)
    try:
        graph.upsert_node(
            NodeInfo(
                kind="Function",
                name="first",
                file_path="a.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="a",
        )
        graph.upsert_node(
            NodeInfo(
                kind="Function",
                name="second",
                file_path="a.py",
                line_start=4,
                line_end=5,
                language="python",
            ),
            file_hash="a",
        )
        graph.commit()
        nodes = graph.get_nodes_by_files(["a.py"])
        _transport(monkeypatch, [[1.0] * 1024, [1.0] * wrong_width])
        with pytest.raises(ValueError, match="different width than requested"):
            store.embed_nodes(nodes)
        assert store.count() == 0
    finally:
        store.close()
        graph.close()


def test_cohere_reopen_reembed_legacy_width_and_query(tmp_path, monkeypatch):
    db = tmp_path / "graph.db"
    backend = CloudEmbeddingBackend(model="cohere/embed-v4.0")
    graph = GraphStore(str(db))
    try:
        graph.upsert_node(
            NodeInfo(
                kind="Function",
                name="authenticate",
                file_path="auth.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="a",
        )
        graph.commit()
        nodes = graph.get_nodes_by_files(["auth.py"])
        qn = nodes[0].qualified_name
        store = EmbeddingStore(db, backend)
        try:
            _transport(monkeypatch, [[1.0] * 1024])
            assert store.embed_nodes(nodes) == 1
        finally:
            store.close()

        # A pre-upgrade row has the same model and text hash but a sliced vector.
        with sqlite3.connect(db) as conn:
            conn.execute(
                "UPDATE embeddings SET vector = ?", (_encode_vector([1.0] * 768),)
            )

        store = EmbeddingStore(db, backend)
        try:
            with patch(
                "better_code_review_graph.embeddings._post_embeddings"
            ) as dispatch:
                with pytest.raises(ValueError, match="incompatible"):
                    store.search("authenticate a user")
                dispatch.assert_not_called()
            dispatch = _transport(monkeypatch, [[1.0] * 1024])
            assert store.embed_nodes(nodes) == 1
            assert store.embed_nodes(nodes) == 0
            assert store.search("authenticate a user", limit=1) == [
                (qn, pytest.approx(1.0))
            ]
            assert [call.kwargs["input_type"] for call in dispatch.call_args_list] == [
                "search_document",
                "search_query",
            ]
            assert all(call.args[2] == 1024 for call in dispatch.call_args_list)
        finally:
            store.close()
        with sqlite3.connect(db) as conn:
            assert (
                conn.execute("SELECT length(vector) FROM embeddings").fetchone()[0]
                == 4096
            )
    finally:
        graph.close()
