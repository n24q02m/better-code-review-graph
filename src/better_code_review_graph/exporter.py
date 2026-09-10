"""Graph export formatters — Phase 1 v1.6.x feature.

Emits the SQLite-backed knowledge graph in interoperable formats for use by
external tools (Gephi, Cytoscape, Neo4j, JSON-LD consumers).

Formats:
    - graphml: XML, supported by Gephi + Cytoscape + NetworkX read_graphml
    - json-ld: JSON, supported by JSON-LD consumers + arbitrary JSON tooling
    - dot: Graphviz DOT, supported by Graphviz + dot2tex + xdot
    - cypher: Neo4j Cypher CREATE statements, replay-able into a Neo4j database
    - crg: JSON, the only format that round-trips back into a GraphStore via
      ``better_code_review_graph.importer.import_graph`` (see Task 6)

Streaming uses iter helpers on the GraphStore. Output is a single string
return value; callers wanting file output write the string to disk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
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


_CYPHER_VAR_PATTERN = re.compile(r"\W")


def _cypher_var(node_id: str) -> str:
    """Return a Cypher-safe variable name derived from node id.

    Uses a pre-compiled `\\W` regular expression (non-alphanumeric,
    non-underscore) rather than a generator expression with `"".join(...)`,
    which keeps the string traversal in C for large graph serializations.
    """
    safe = _CYPHER_VAR_PATTERN.sub("_", node_id)
    return f"n_{safe}"


def export_graphml(store: GraphStore) -> str:
    """Emit GraphML XML for the entire graph.

    Compatible with Gephi import, Cytoscape import, and ``networkx.read_graphml``.
    """
    import xml.etree.ElementTree as standard_ET

    standard_ET.register_namespace("", GRAPHML_NS)
    root = standard_ET.Element(f"{{{GRAPHML_NS}}}graphml")

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
        standard_ET.SubElement(
            root,
            f"{{{GRAPHML_NS}}}key",
            {"id": key_id, "for": scope, "attr.name": key_id, "attr.type": attr_type},
        )

    graph = standard_ET.SubElement(
        root, f"{{{GRAPHML_NS}}}graph", {"id": "G", "edgedefault": "directed"}
    )

    # Bolt optimization: iterate directly over sqlite3.Cursor to avoid peak memory overhead from full GraphNode materialization
    for row in store.iter_raw_nodes():
        n_el = standard_ET.SubElement(
            graph, f"{{{GRAPHML_NS}}}node", {"id": row["qualified_name"]}
        )
        for k, v in (
            ("kind", row["kind"]),
            ("name", row["name"]),
            ("qualified_name", row["qualified_name"]),
            ("file_path", row["file_path"]),
            ("language", row["language"]),
        ):
            if v is None or v == "":
                continue
            d = standard_ET.SubElement(n_el, f"{{{GRAPHML_NS}}}data", {"key": k})
            d.text = str(v)
        for k, v in (("line_start", row["line_start"]), ("line_end", row["line_end"])):
            if v is None:
                continue
            d = standard_ET.SubElement(n_el, f"{{{GRAPHML_NS}}}data", {"key": k})
            d.text = str(v)

    # Bolt optimization: iterate directly over sqlite3.Cursor to avoid peak memory overhead from full GraphEdge materialization
    for row in store.iter_raw_edges():
        e_el = standard_ET.SubElement(
            graph,
            f"{{{GRAPHML_NS}}}edge",
            {"source": row["source_qualified"], "target": row["target_qualified"]},
        )
        for k, v in (("edge_kind", row["kind"]), ("edge_file", row["file_path"])):
            if v is None or v == "":
                continue
            d = standard_ET.SubElement(e_el, f"{{{GRAPHML_NS}}}data", {"key": k})
            d.text = str(v)
        if row["line"] is not None:
            d = standard_ET.SubElement(
                e_el, f"{{{GRAPHML_NS}}}data", {"key": "edge_line"}
            )
            d.text = str(row["line"])

    return standard_ET.tostring(root, encoding="unicode", xml_declaration=True)


def export_jsonld(store: GraphStore) -> str:
    """Emit JSON-LD with @context + nodes + edges arrays."""
    nodes = []
    # Bolt optimization: iterate directly over sqlite3.Cursor to avoid full object materialization overhead
    for row in store.iter_raw_nodes():
        n: dict[str, object] = {
            "@id": row["qualified_name"],
            "@type": row["kind"],
            "name": row["name"],
            "filePath": row["file_path"],
            "language": row["language"],
        }
        if row["line_start"] is not None:
            n["lineStart"] = row["line_start"]
        if row["line_end"] is not None:
            n["lineEnd"] = row["line_end"]
        nodes.append(n)
    edges = []
    for row in store.iter_raw_edges():
        e: dict[str, object] = {
            "source": row["source_qualified"],
            "target": row["target_qualified"],
            "kind": row["kind"],
        }
        if row["file_path"]:
            e["filePath"] = row["file_path"]
        if row["line"] is not None:
            e["line"] = row["line"]
        edges.append(e)
    return json.dumps(
        {"@context": JSONLD_CONTEXT, "nodes": nodes, "edges": edges}, indent=2
    )


def export_dot(store: GraphStore) -> str:
    """Emit Graphviz DOT format (digraph)."""
    lines = ["digraph G {"]
    # Bolt optimization: iterate over sqlite3.Cursor directly
    for row in store.iter_raw_nodes():
        label = _safe_label(row["name"] or row["qualified_name"])
        lines.append(f'  "{row["qualified_name"]}" [label="{label}"];')
    for row in store.iter_raw_edges():
        kind = _safe_label(row["kind"])
        lines.append(
            f'  "{row["source_qualified"]}" -> "{row["target_qualified"]}" [label="{kind}"];'
        )
    lines.append("}")
    return "\n".join(lines)


def export_cypher(store: GraphStore) -> str:
    """Emit Neo4j Cypher CREATE statements that recreate the graph."""
    parts = []
    # Bolt optimization: iterate over sqlite3.Cursor directly
    for row in store.iter_raw_nodes():
        kind_label = row["kind"] or "Node"
        var = _cypher_var(row["qualified_name"])
        props: dict[str, object] = {
            "id": row["qualified_name"],
            "name": row["name"],
            "file_path": row["file_path"],
            "language": row["language"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
        }
        parts.append(f"CREATE ({var}:{kind_label} {{{_cypher_props(props)}}});")
    for row in store.iter_raw_edges():
        kind = (row["kind"] or "RELATED").upper().replace("-", "_")
        src_escaped = row["source_qualified"].replace("'", "\\'")
        tgt_escaped = row["target_qualified"].replace("'", "\\'")
        parts.append(
            f"MATCH (a {{id: '{src_escaped}'}}), (b {{id: '{tgt_escaped}'}}) "
            f"CREATE (a)-[:{kind}]->(b);"
        )
    return "\n".join(parts)


def export_crg(store: GraphStore, root: Path | None = None) -> str:
    """Emit the full graph as round-trippable JSON (Task 6).

    Unlike the other formats (one-way interop with external tools), ``crg``
    dumps every column of the ``nodes`` / ``edges`` tables verbatim --
    including ``source_text``, the summarizer columns, and the temporal
    ``valid_from_sha``/``valid_to_sha`` columns -- so
    :func:`better_code_review_graph.importer.import_graph` can reconstruct
    an equivalent subgraph in a different store (e.g. built on a CI runner,
    imported on a laptop; the crg format is not used by the CF-hosted
    deployment).

    ``repo_id`` identifies the exporting graph and becomes the namespace
    prefix an importer uses to keep re-imported ids from colliding with
    locally-parsed nodes. It is derived via
    :func:`better_code_review_graph.federation.derive_repo_id` from ``root``
    when the caller supplies it (``export_graph_dispatch`` always does,
    since it already resolves the repo root) -- this is the same id a
    federated ``graph(action='build', roots=[...])`` would register for
    that same root, so repo-scoped queries agree after either path. When
    ``root`` is omitted (e.g. calling this function directly against a
    store that isn't backed by a real repo checkout), falls back to the
    store's own db directory so the id stays deterministic per store; note
    that fallback is *not* guaranteed to match a federated id for a real
    root, since ``store.db_path`` normally lives at
    ``<root>/.code-review-graph/graph.db`` -- one directory below ``root``.
    """
    from .federation import derive_repo_id

    repo_id = derive_repo_id(root if root is not None else store.db_path.parent)
    nodes = [dict(row) for row in store.iter_raw_nodes()]
    edges = [dict(row) for row in store.iter_raw_edges()]
    return json.dumps(
        {"schema_version": 1, "repo_id": repo_id, "nodes": nodes, "edges": edges},
        indent=2,
    )


_FORMATTERS = {
    "graphml": export_graphml,
    "json-ld": export_jsonld,
    "jsonld": export_jsonld,
    "dot": export_dot,
    "cypher": export_cypher,
}


def export_graph(
    store: GraphStore, format: str = "graphml", root: Path | None = None
) -> str:
    """Dispatch to the per-format formatter. Raises ValueError on unknown format.

    ``root`` is only consumed by the ``crg`` format (see :func:`export_crg`);
    the other formatters ignore it.
    """
    fmt = format.lower()
    if fmt == "crg":
        return export_crg(store, root=root)
    if fmt not in _FORMATTERS:
        valid = sorted({"graphml", "json-ld", "dot", "cypher", "crg"})
        raise ValueError(f"Unknown export format '{format}'. Valid: {valid}")
    return _FORMATTERS[fmt](store)
