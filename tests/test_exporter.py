"""Phase 1 v1.6.x: graph export formats."""

from __future__ import annotations

import json
import re

import pytest

from better_code_review_graph.exporter import (
    export_cypher,
    export_dot,
    export_graph,
    export_jsonld,
)
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo


@pytest.fixture
def populated_store(tmp_path):
    """A small graph: 2 functions in 1 file, with one CALLS edge."""
    db_path = tmp_path / "test.db"
    store = GraphStore(str(db_path))

    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="foo",
            file_path="src/x.py",
            line_start=1,
            line_end=10,
            language="python",
        ),
        file_hash="h1",
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="bar",
            file_path="src/x.py",
            line_start=12,
            line_end=20,
            language="python",
        ),
        file_hash="h1",
    )
    store.upsert_edge(
        EdgeInfo(
            kind="CALLS",
            source="src/x.py::foo",
            target="src/x.py::bar",
            file_path="src/x.py",
            line=2,
        )
    )
    yield store
    store.close()


def test_export_jsonld_emits_node_link_format(populated_store):
    out = export_jsonld(populated_store)
    parsed = json.loads(out)
    assert parsed["@context"]["@vocab"].startswith("https://")
    assert {n["@id"] for n in parsed["nodes"]} == {"src/x.py::foo", "src/x.py::bar"}
    assert len(parsed["edges"]) == 1
    e = parsed["edges"][0]
    assert e["source"] == "src/x.py::foo"
    assert e["target"] == "src/x.py::bar"
    assert e["kind"] == "CALLS"


def test_export_dot_emits_digraph_with_quoted_ids(populated_store):
    out = export_dot(populated_store)
    assert out.startswith("digraph G {")
    assert out.rstrip().endswith("}")
    assert '"src/x.py::foo" -> "src/x.py::bar"' in out
    assert 'label="CALLS"' in out


def test_export_cypher_emits_create_and_match_statements(populated_store):
    out = export_cypher(populated_store)
    # node creation
    assert re.search(
        r"CREATE \(n_src_x_py__foo:Function \{[^\}]*name: 'foo'[^\}]*\}\);", out
    )
    # edge creation via MATCH..CREATE
    assert (
        "MATCH (a {id: 'src/x.py::foo'}), (b {id: 'src/x.py::bar'}) "
        "CREATE (a)-[:CALLS]->(b);" in out
    )


def test_export_graph_dispatch_routes_to_formatter(populated_store):
    out = export_graph(populated_store, format="json-ld")
    assert json.loads(out)["nodes"]
    out = export_graph(populated_store, format="JSONLD")  # case-insensitive alias
    assert json.loads(out)["nodes"]


def test_export_graph_unknown_format_raises(populated_store):
    with pytest.raises(ValueError, match="Unknown export format"):
        export_graph(populated_store, format="rdf-xml")


def test_export_dot_escapes_quotes_in_labels(tmp_path):
    db_path = tmp_path / "edge.db"
    store = GraphStore(str(db_path))
    try:
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name='say"hi"',
                file_path="src/x.py",
                line_start=1,
                line_end=3,
                language="python",
            ),
            file_hash="h",
        )
        out = export_dot(store)
        assert 'label="say\\"hi\\""' in out
    finally:
        store.close()


def test_export_cypher_handles_numeric_props(tmp_path):
    """Cypher exporter must format int/float/bool props without quotes."""
    store = GraphStore(str(tmp_path / "test.db"))
    try:
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=42,
                line_end=99,
                language="python",
            ),
            file_hash="h",
        )
        out = export_cypher(store)
        # Numeric line_start/line_end should appear unquoted
        assert "line_start: 42" in out
        assert "line_end: 99" in out
    finally:
        store.close()


def test_export_cypher_skips_none_props(tmp_path):
    """_cypher_props must skip None values (line 48 branch)."""
    store = GraphStore(str(tmp_path / "test.db"))
    try:
        # line_start/line_end = None → cypher must skip them
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="nulls",
                file_path="x.py",
                line_start=None,
                line_end=None,
                language="python",
            ),
            file_hash="h",
        )
        out = export_cypher(store)
        # None props must NOT be emitted (no `line_start: None` or `line_start: `)
        assert "line_start" not in out
        assert "line_end" not in out
        # But the remaining string props still appear
        assert "name: 'nulls'" in out
        assert "language: 'python'" in out
    finally:
        store.close()
