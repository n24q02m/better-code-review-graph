"""Graph export formatters — Phase 1 v1.6.x feature.

Emits the SQLite-backed knowledge graph in interoperable formats for use by
external tools (Gephi, Cytoscape, Neo4j, JSON-LD consumers).

Formats:
    - graphml: XML, supported by Gephi + Cytoscape + NetworkX read_graphml
    - json-ld: JSON, supported by JSON-LD consumers + arbitrary JSON tooling
    - dot: Graphviz DOT, supported by Graphviz + dot2tex + xdot
    - cypher: Neo4j Cypher CREATE statements, replay-able into a Neo4j database

Streaming uses iter helpers on the GraphStore. Output is a single string
return value; callers wanting file output write the string to disk.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import GraphStore

GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns"

JSONLD_CONTEXT = {
    "@vocab": "https://better-code-review-graph.n24q02m.dev/schema#",
    "kind": "@type",
    "name": "name",
    "filePath": "filePath",
    "language": "language",
    "lineStart": "lineStart",
    "lineEnd": "lineEnd",
}


def _safe_label(value: object) -> str:
    """Quote-escape a value for inclusion in a DOT label string."""
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _cypher_props(props: dict[str, object]) -> str:
    """Format a property dict into Cypher map syntax."""
    parts = []
    for k, v in props.items():
        if v is None:
            continue
        if isinstance(v, (int, float, bool)):
            parts.append(f"{k}: {v}")
        else:
            escaped = str(v).replace("\\", "\\\\").replace("'", "\\'")
            parts.append(f"{k}: '{escaped}'")
    return ", ".join(parts)


def _cypher_var(node_id: str) -> str:
    """Return a Cypher-safe variable name derived from node id."""
    safe = "".join(c if c.isalnum() else "_" for c in node_id)
    return f"n_{safe}"


def export_graphml(store: GraphStore) -> str:
    """Emit GraphML XML for the entire graph.

    Compatible with Gephi import, Cytoscape import, and ``networkx.read_graphml``.
    """
    ET.register_namespace("", GRAPHML_NS)
    root = ET.Element(f"{{{GRAPHML_NS}}}graphml")

    keys = [
        ("kind", "node", "string"),
        ("name", "node", "string"),
        ("qualified_name", "node", "string"),
        ("file_path", "node", "string"),
        ("language", "node", "string"),
        ("line_start", "node", "int"),
        ("line_end", "node", "int"),
        ("edge_kind", "edge", "string"),
        ("edge_file", "edge", "string"),
        ("edge_line", "edge", "int"),
    ]
    for key_id, scope, attr_type in keys:
        ET.SubElement(
            root,
            f"{{{GRAPHML_NS}}}key",
            {"id": key_id, "for": scope, "attr.name": key_id, "attr.type": attr_type},
        )

    graph = ET.SubElement(
        root, f"{{{GRAPHML_NS}}}graph", {"id": "G", "edgedefault": "directed"}
    )

    for node in store.get_all_nodes():
        n_el = ET.SubElement(
            graph, f"{{{GRAPHML_NS}}}node", {"id": node.qualified_name}
        )
        for k, v in (
            ("kind", node.kind),
            ("name", node.name),
            ("qualified_name", node.qualified_name),
            ("file_path", node.file_path),
            ("language", node.language),
        ):
            if v is None or v == "":
                continue
            d = ET.SubElement(n_el, f"{{{GRAPHML_NS}}}data", {"key": k})
            d.text = str(v)
        for k, v in (("line_start", node.line_start), ("line_end", node.line_end)):
            if v is None:
                continue
            d = ET.SubElement(n_el, f"{{{GRAPHML_NS}}}data", {"key": k})
            d.text = str(v)

    for edge in store.get_all_edges():
        e_el = ET.SubElement(
            graph,
            f"{{{GRAPHML_NS}}}edge",
            {"source": edge.source_qualified, "target": edge.target_qualified},
        )
        for k, v in (("edge_kind", edge.kind), ("edge_file", edge.file_path)):
            if v is None or v == "":
                continue
            d = ET.SubElement(e_el, f"{{{GRAPHML_NS}}}data", {"key": k})
            d.text = str(v)
        if edge.line is not None:
            d = ET.SubElement(e_el, f"{{{GRAPHML_NS}}}data", {"key": "edge_line"})
            d.text = str(edge.line)

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def export_jsonld(store: GraphStore) -> str:
    """Emit JSON-LD with @context + nodes + edges arrays."""
    nodes = []
    for node in store.get_all_nodes():
        n = {
            "@id": node.qualified_name,
            "@type": node.kind,
            "name": node.name,
            "filePath": node.file_path,
            "language": node.language,
        }
        if node.line_start is not None:
            n["lineStart"] = node.line_start
        if node.line_end is not None:
            n["lineEnd"] = node.line_end
        nodes.append(n)
    edges = []
    for edge in store.get_all_edges():
        e = {
            "source": edge.source_qualified,
            "target": edge.target_qualified,
            "kind": edge.kind,
        }
        if edge.file_path:
            e["filePath"] = edge.file_path
        if edge.line is not None:
            e["line"] = edge.line
        edges.append(e)
    return json.dumps(
        {"@context": JSONLD_CONTEXT, "nodes": nodes, "edges": edges}, indent=2
    )


def export_dot(store: GraphStore) -> str:
    """Emit Graphviz DOT format (digraph)."""
    lines = ["digraph G {"]
    for node in store.get_all_nodes():
        label = _safe_label(node.name or node.qualified_name)
        lines.append(f'  "{node.qualified_name}" [label="{label}"];')
    for edge in store.get_all_edges():
        kind = _safe_label(edge.kind)
        lines.append(
            f'  "{edge.source_qualified}" -> "{edge.target_qualified}" [label="{kind}"];'
        )
    lines.append("}")
    return "\n".join(lines)


def export_cypher(store: GraphStore) -> str:
    """Emit Neo4j Cypher CREATE statements that recreate the graph."""
    parts = []
    for node in store.get_all_nodes():
        kind_label = node.kind or "Node"
        var = _cypher_var(node.qualified_name)
        props = {
            "id": node.qualified_name,
            "name": node.name,
            "file_path": node.file_path,
            "language": node.language,
            "line_start": node.line_start,
            "line_end": node.line_end,
        }
        parts.append(f"CREATE ({var}:{kind_label} {{{_cypher_props(props)}}});")
    for edge in store.get_all_edges():
        kind = (edge.kind or "RELATED").upper().replace("-", "_")
        src_escaped = edge.source_qualified.replace("'", "\\'")
        tgt_escaped = edge.target_qualified.replace("'", "\\'")
        parts.append(
            f"MATCH (a {{id: '{src_escaped}'}}), (b {{id: '{tgt_escaped}'}}) "
            f"CREATE (a)-[:{kind}]->(b);"
        )
    return "\n".join(parts)


_FORMATTERS = {
    "graphml": export_graphml,
    "json-ld": export_jsonld,
    "jsonld": export_jsonld,
    "dot": export_dot,
    "cypher": export_cypher,
}


def export_graph(store: GraphStore, format: str = "graphml") -> str:
    """Dispatch to the per-format formatter. Raises ValueError on unknown format."""
    fmt = format.lower()
    if fmt not in _FORMATTERS:
        valid = sorted({"graphml", "json-ld", "dot", "cypher"})
        raise ValueError(f"Unknown export format '{format}'. Valid: {valid}")
    return _FORMATTERS[fmt](store)
