"""Phase 1 v1.6.x: graph export formats."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

import pytest

from better_code_review_graph.exporter import (
    export_crg,
    export_cypher,
    export_dot,
    export_graph,
    export_graphml,
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
            line_end=3,
            language="python",
        ),
        file_hash="hash1",
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="bar",
            file_path="src/x.py",
            line_start=5,
            line_end=7,
            language="python",
        ),
        file_hash="hash1",
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


def test_export_graphml_emits_well_formed_xml(populated_store):
    out = export_graphml(populated_store)
    assert out.startswith("<?xml")
    root = ET.fromstring(out)
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    nodes = root.findall(".//g:node", ns)
    edges = root.findall(".//g:edge", ns)
    assert {n.get("id") for n in nodes} == {"src/x.py::foo", "src/x.py::bar"}
    assert len(edges) == 1
    assert edges[0].get("source") == "src/x.py::foo"
    assert edges[0].get("target") == "src/x.py::bar"


def test_export_graphml_includes_node_metadata(populated_store):
    out = export_graphml(populated_store)
    assert '<data key="kind">Function</data>' in out
    assert '<data key="language">python</data>' in out
    assert '<data key="line_start">1</data>' in out


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
    out = export_graph(populated_store, format="graphml")
    assert "<graphml" in out
    out = export_graph(populated_store, format="json-ld")
    assert json.loads(out)["nodes"]
    out = export_graph(populated_store, format="JSONLD")  # case-insensitive alias
    assert json.loads(out)["nodes"]
    out = export_graph(populated_store, format="crg")
    assert json.loads(out)["schema_version"] == 1


def test_export_crg_emits_schema_version_and_repo_id(populated_store):
    payload = json.loads(export_crg(populated_store))
    assert payload["schema_version"] == 1
    assert isinstance(payload["repo_id"], str)
    assert payload["repo_id"] != ""
    assert {n["qualified_name"] for n in payload["nodes"]} == {
        "src/x.py::foo",
        "src/x.py::bar",
    }
    assert len(payload["edges"]) == 1
    assert payload["edges"][0]["source_qualified"] == "src/x.py::foo"
    assert payload["edges"][0]["target_qualified"] == "src/x.py::bar"


def test_export_crg_is_stable_across_repeated_exports(populated_store):
    """Same store -> same repo_id every time (importer relies on this)."""
    first = json.loads(export_crg(populated_store))
    second = json.loads(export_crg(populated_store))
    assert first["repo_id"] == second["repo_id"]


def test_export_crg_includes_source_text(tmp_path):
    db_path = tmp_path / "with_source.db"
    store = GraphStore(str(db_path))
    try:
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="python",
                source_text="def f():\n    pass\n",
            ),
            file_hash="h",
        )
        payload = json.loads(export_crg(store))
        assert payload["nodes"][0]["source_text"] == "def f():\n    pass\n"
    finally:
        store.close()


def test_export_graph_unknown_format_raises(populated_store):
    with pytest.raises(ValueError, match="Unknown export format"):
        export_graph(populated_store, format="rdf-xml")


def test_export_graphml_handles_empty_graph(tmp_path):
    db_path = tmp_path / "empty.db"
    store = GraphStore(str(db_path))
    try:
        out = export_graphml(store)
        root = ET.fromstring(out)
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        assert root.findall(".//g:node", ns) == []
        assert root.findall(".//g:edge", ns) == []
    finally:
        store.close()


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


def test_export_graphml_skips_empty_string_attributes(tmp_path):
    """GraphML exporter must omit data elements when value is empty string (not just None)."""
    store = GraphStore(str(tmp_path / "test.db"))
    try:
        # NodeInfo with language="" — should be skipped in graphml output
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="",
            ),
            file_hash="h",
        )
        out = export_graphml(store)
        # The empty-string language data element should NOT appear
        assert '<data key="language">' not in out
        # But other attributes should still be present
        assert '<data key="kind">Function</data>' in out
    finally:
        store.close()


def test_export_graphml_skips_none_line_attrs(tmp_path):
    """GraphML node loop must skip line_start/line_end when None (line 111 branch)."""
    store = GraphStore(str(tmp_path / "test.db"))
    try:
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=None,
                line_end=None,
                language="python",
            ),
            file_hash="h",
        )
        out = export_graphml(store)
        # None line_start/line_end → no data element emitted
        assert '<data key="line_start">' not in out
        assert '<data key="line_end">' not in out
        # But kind/language still emitted
        assert '<data key="kind">Function</data>' in out
        assert '<data key="language">python</data>' in out
    finally:
        store.close()


def test_export_graphml_skips_empty_edge_attrs(tmp_path):
    """GraphML edge loop must skip edge_file when empty (line 123 branch)."""
    store = GraphStore(str(tmp_path / "test.db"))
    try:
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="a",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="h",
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="b",
                file_path="x.py",
                line_start=4,
                line_end=5,
                language="python",
            ),
            file_hash="h",
        )
        # Edge with empty file_path → graphml must skip the edge_file data element
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="x.py::a",
                target="x.py::b",
                file_path="",
                line=1,
            )
        )
        out = export_graphml(store)
        # Empty edge_file must be skipped
        assert '<data key="edge_file">' not in out
        # But edge_kind still emitted
        assert '<data key="edge_kind">CALLS</data>' in out
    finally:
        store.close()
