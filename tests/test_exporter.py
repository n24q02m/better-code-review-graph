"""Phase 1 v1.6.x: graph export formats."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

import pytest

from better_code_review_graph.exporter import (
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
