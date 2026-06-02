"""Phase 1 v1.6.x: graph(action='export') MCP wiring tests."""

from __future__ import annotations

from unittest.mock import patch

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import export_graph_dispatch


def _populate_store(store: GraphStore) -> None:
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="alpha",
            file_path="src/x.py",
            line_start=1,
            line_end=2,
            language="python",
        ),
        file_hash="h",
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="beta",
            file_path="src/x.py",
            line_start=4,
            line_end=5,
            language="python",
        ),
        file_hash="h",
    )
    store.upsert_edge(
        EdgeInfo(
            kind="CALLS",
            source="src/x.py::alpha",
            target="src/x.py::beta",
            file_path="src/x.py",
            line=1,
        )
    )


def test_dispatch_unknown_format_returns_error(tmp_path):
    """Unknown format should be caught + returned as status='error' with helpful message."""
    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        try:
            mock_get_store.return_value = (store, tmp_path)
            result = export_graph_dispatch(repo_root=str(tmp_path), format="rdf-xml")
        finally:
            store.close()
    assert result["status"] == "error"
    assert "Unknown export format" in result["error"]


def test_dispatch_inline_returns_payload(tmp_path):
    """output_path=None → returns inline payload + bytes count."""
    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        try:
            _populate_store(store)
            mock_get_store.return_value = (store, tmp_path)
            result = export_graph_dispatch(repo_root=str(tmp_path), format="json-ld")
        finally:
            store.close()
    assert result["status"] == "ok"
    assert result["format"] == "json-ld"
    assert result["bytes"] > 0
    assert "payload" in result
    assert "alpha" in result["payload"]
    assert "output_path" not in result


def test_dispatch_output_path_traversal_blocked(tmp_path):
    """output_path outside repository root should return an error."""
    out_file = tmp_path.parent / "out.graphml"
    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        try:
            _populate_store(store)
            mock_get_store.return_value = (store, tmp_path)
            result = export_graph_dispatch(
                repo_root=str(tmp_path),
                format="graphml",
                output_path=str(out_file),
            )
        finally:
            store.close()
    assert result["status"] == "error"
    assert "within the repository root" in result["error"]


def test_dispatch_with_output_path_writes_file(tmp_path):
    """output_path provided → writes file, returns metadata only (no inline payload)."""
    out_file = tmp_path / "out.graphml"
    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        try:
            _populate_store(store)
            mock_get_store.return_value = (store, tmp_path)
            result = export_graph_dispatch(
                repo_root=str(tmp_path),
                format="graphml",
                output_path=str(out_file),
            )
        finally:
            store.close()
    assert result["status"] == "ok"
    assert result["format"] == "graphml"
    assert result["output_path"] == str(out_file)
    assert result["bytes"] > 0
    assert "payload" not in result
    assert "summary" in result
    assert str(out_file) in result["summary"]
    # Verify the file actually exists + has the expected content shape
    written = out_file.read_text(encoding="utf-8")
    assert "<graphml" in written
    assert "alpha" in written


def test_dispatch_format_alias_jsonld_works(tmp_path):
    """'jsonld' (no hyphen) should be normalized + dispatched same as 'json-ld'."""
    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        try:
            _populate_store(store)
            mock_get_store.return_value = (store, tmp_path)
            result = export_graph_dispatch(repo_root=str(tmp_path), format="jsonld")
        finally:
            store.close()
    assert result["status"] == "ok"
    assert "payload" in result
