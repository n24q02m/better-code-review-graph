"""Exact Cohere dimensions and persisted index/query compatibility; no live calls."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
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


def _response(*vectors):
    return SimpleNamespace(
        data=[
            {"index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ]
    )


def test_unsupported_cohere_width_is_rejected_without_dispatch():
    backend = CloudEmbeddingBackend(model="cohere/embed-v4.0", api_key="test")
    with patch("mcp_core.llm.embedding") as dispatch:
        with pytest.raises(ValueError, match="requires dimensions"):
            backend.embed_texts(["hello"], dimensions=768)
    dispatch.assert_not_called()


@pytest.mark.parametrize("wrong_width", [768, 1536])
def test_provider_width_mismatch_never_coerces_or_persists(tmp_path, wrong_width):
    backend = CloudEmbeddingBackend(model="cohere/embed-v4.0", api_key="test")
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
        with patch(
            "mcp_core.llm.embedding",
            return_value=_response([1.0] * 1024, [1.0] * wrong_width),
        ):
            with pytest.raises(ValueError, match="different width"):
                store.embed_nodes(nodes)
        assert store.count() == 0
    finally:
        store.close()
        graph.close()


def test_cohere_reopen_reembed_legacy_width_and_query(tmp_path):
    db = tmp_path / "graph.db"
    backend = CloudEmbeddingBackend(model="cohere/embed-v4.0", api_key="test")
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
            with patch("mcp_core.llm.embedding", return_value=_response([1.0] * 1024)):
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
            with patch("mcp_core.llm.embedding") as dispatch:
                with pytest.raises(ValueError, match="incompatible"):
                    store.search("authenticate a user")
                dispatch.assert_not_called()
            with patch(
                "mcp_core.llm.embedding", return_value=_response([1.0] * 1024)
            ) as dispatch:
                assert store.embed_nodes(nodes) == 1
                assert store.embed_nodes(nodes) == 0
                assert store.search("authenticate a user", limit=1) == [
                    (qn, pytest.approx(1.0))
                ]
                assert [
                    call.kwargs["input_type"] for call in dispatch.call_args_list
                ] == ["search_document", "search_query"]
                assert all(
                    call.kwargs["dimensions"] == 1024
                    for call in dispatch.call_args_list
                )
        finally:
            store.close()
        with sqlite3.connect(db) as conn:
            assert (
                conn.execute("SELECT length(vector) FROM embeddings").fetchone()[0]
                == 4096
            )
    finally:
        graph.close()


def test_duplicate_response_indices_do_not_assign_vectors_to_wrong_nodes():
    backend = CloudEmbeddingBackend(model="cohere/embed-v4.0", api_key="test")
    response = SimpleNamespace(
        data=[
            {"index": 0, "embedding": [1.0] * 1024},
            {"index": 0, "embedding": [0.5] * 1024},
        ]
    )
    with patch("mcp_core.llm.embedding", return_value=response):
        with pytest.raises(ValueError, match="indices"):
            backend.embed_texts(["first", "second"], dimensions=1024)
