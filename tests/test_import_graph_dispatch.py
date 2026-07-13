"""Task 6: graph(action='import') MCP wiring tests."""

from __future__ import annotations

import json
from unittest.mock import patch

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import export_graph_dispatch, import_graph_dispatch


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


def test_import_dispatch_missing_import_path_returns_error(tmp_path):
    result = import_graph_dispatch(repo_root=str(tmp_path), import_path=None)
    assert result["status"] == "error"
    assert "import_path is required" in result["error"]


def test_import_dispatch_reads_export_file_and_merges(tmp_path):
    """Full round trip through the dispatch layer: export to a file, import it."""
    export_file = tmp_path / "export.json"

    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        source_store = GraphStore(str(tmp_path / "source.db"))
        try:
            _populate_store(source_store)
            mock_get_store.return_value = (source_store, tmp_path)
            export_result = export_graph_dispatch(
                repo_root=str(tmp_path), format="crg", output_path=str(export_file)
            )
        finally:
            source_store.close()
    assert export_result["status"] == "ok"

    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        target_store = GraphStore(str(tmp_path / "target.db"))
        try:
            mock_get_store.return_value = (target_store, tmp_path)
            result = import_graph_dispatch(
                repo_root=str(tmp_path), import_path=str(export_file)
            )
        finally:
            target_store.close()

    assert result["status"] == "ok"
    assert result["nodes_added"] == 2
    assert result["nodes_updated"] == 0
    assert result["edges_added"] == 1
    assert "repo_id" in result
    assert "Imported 2 new node" in result["summary"]


def test_import_dispatch_malformed_json_returns_error(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json", encoding="utf-8")

    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        try:
            mock_get_store.return_value = (store, tmp_path)
            result = import_graph_dispatch(
                repo_root=str(tmp_path), import_path=str(bad_file)
            )
        finally:
            store.close()

    assert result["status"] == "error"
    assert "Malformed import payload" in result["error"]


def test_import_dispatch_bad_schema_version_returns_error(tmp_path):
    payload_file = tmp_path / "bad_schema.json"
    payload_file.write_text(
        json.dumps({"schema_version": 99, "repo_id": "x", "nodes": [], "edges": []}),
        encoding="utf-8",
    )

    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        try:
            mock_get_store.return_value = (store, tmp_path)
            result = import_graph_dispatch(
                repo_root=str(tmp_path), import_path=str(payload_file)
            )
        finally:
            store.close()

    assert result["status"] == "error"
    assert "schema_version" in result["error"]


def test_import_dispatch_path_traversal_blocked(
    tmp_path, _allow_temporal_migration_without_git
):
    (tmp_path / ".code-review-graph").mkdir()
    outside_file = tmp_path.parent / "outside_import.json"
    outside_file.write_text(
        json.dumps({"schema_version": 1, "repo_id": "x", "nodes": [], "edges": []}),
        encoding="utf-8",
    )
    import_path = str(tmp_path / "../outside_import.json")

    result = import_graph_dispatch(repo_root=str(tmp_path), import_path=import_path)

    assert result["status"] == "error"
    assert "must be relative to repo root" in result["error"]
