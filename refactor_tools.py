import sys
import os
import re

file_path = 'src/better_code_review_graph/tools.py'
with open(file_path, 'r') as f:
    content = f.read()

replacement = r'''
def _resolve_query_target(
    target: str, store: GraphStore, root: Path
) -> tuple[GraphNode | None, str]:
    """Resolve query target to a node or qualified name."""
    node = store.get_node(target)
    if not node:
        full_target_raw = root / target
        full_target = full_target_raw.resolve()
        if (
            full_target.is_relative_to(root.resolve())
            and not full_target_raw.is_symlink()
            and not full_target.is_symlink()
        ):
            abs_target = str(full_target)
            node = store.get_node(abs_target)
    if not node:
        # Search by name
        candidates = store.search_nodes(target, limit=5)
        if len(candidates) == 1:
            node = candidates[0]
            target = node.qualified_name
        elif len(candidates) > 1:
            # Return a sentinel for ambiguous
            return None, "ambiguous"

    qn = node.qualified_name if node else target
    return node, qn


def _handle_callers_of(
    qn: str, node: GraphNode | None, store: GraphStore, edges_out: list[dict]
) -> list[dict]:
    qns = []
    for e in store.get_edges_by_target(qn):
        if e.kind == "CALLS":
            qns.append(e.source_qualified)
            edges_out.append(edge_to_dict(e))

    # Fallback: CALLS edges store unqualified target names
    if not qns and node:
        for e in store.search_edges_by_target_name(node.name):
            qns.append(e.source_qualified)
            edges_out.append(edge_to_dict(e))

    results = []
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))
    return results


def _handle_callees_of(qn: str, store: GraphStore, edges_out: list[dict]) -> list[dict]:
    qns = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "CALLS":
            qns.append(e.target_qualified)
            edges_out.append(edge_to_dict(e))
    results = []
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_tgt in qns:
            if qn_tgt in node_map:
                results.append(node_to_dict(node_map[qn_tgt]))
    return results


def _handle_imports_of(qn: str, store: GraphStore, edges_out: list[dict]) -> list[dict]:
    # Optimization: fetch full node info for imports
    qns = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "IMPORTS_FROM":
            qns.append(e.target_qualified)
            edges_out.append(edge_to_dict(e))
    results = []
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_tgt in qns:
            if qn_tgt in node_map:
                results.append(node_to_dict(node_map[qn_tgt]))
            else:
                # Fallback for external imports not in graph
                results.append({"import_target": qn_tgt})
    return results


def _handle_importers_of(
    qn: str, node: GraphNode | None, store: GraphStore, root: Path, edges_out: list[dict]
) -> list[dict]:
    # Find edges where target matches this file
    if node is not None:
        abs_target = node.file_path
    else:
        full_target_raw = root / qn
        full_target = full_target_raw.resolve()
        if (
            not full_target.is_relative_to(root.resolve())
            or full_target_raw.is_symlink()
            or full_target.is_symlink()
        ):
            return []
        abs_target = str(full_target)

    qns = []
    edge_map = {}
    for e in store.get_edges_by_target(abs_target):
        if e.kind == "IMPORTS_FROM":
            qns.append(e.source_qualified)
            edge_map[e.source_qualified] = e

    results = []
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))
                edges_out.append(edge_to_dict(edge_map[qn_src]))
            else:
                results.append(
                    {"importer": qn_src, "file": edge_map[qn_src].file_path}
                )
                edges_out.append(edge_to_dict(edge_map[qn_src]))
    return results


def _handle_children_of(qn: str, store: GraphStore) -> list[dict]:
    qns = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "CONTAINS":
            qns.append(e.target_qualified)
    results = []
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_tgt in qns:
            if qn_tgt in node_map:
                results.append(node_to_dict(node_map[qn_tgt]))
    return results


def _handle_tests_for(
    qn: str, node: GraphNode | None, target: str, store: GraphStore
) -> list[dict]:
    qns = []
    for e in store.get_edges_by_target(qn):
        if e.kind == "TESTED_BY":
            qns.append(e.source_qualified)
    results = []
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))

    # Also search by naming convention
    name = node.name if node else target
    test_nodes = store.search_nodes(f"test_{name}", limit=10)
    test_nodes += store.search_nodes(f"Test{name}", limit=10)
    seen = {r.get("qualified_name") for r in results}
    for t in test_nodes:
        if t.qualified_name not in seen and t.is_test:
            results.append(node_to_dict(t))
            seen.add(t.qualified_name)
    return results


def _handle_inheritors_of(
    qn: str, store: GraphStore, edges_out: list[dict]
) -> list[dict]:
    qns = []
    for e in store.get_edges_by_target(qn):
        if e.kind in ("INHERITS", "IMPLEMENTS"):
            qns.append(e.source_qualified)
            edges_out.append(edge_to_dict(e))
    results = []
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))
    return results


def _handle_file_summary(target: str, store: GraphStore, root: Path) -> list[dict]:
    full_target_raw = root / target
    full_target = full_target_raw.resolve()
    if (
        not full_target.is_relative_to(root.resolve())
        or full_target_raw.is_symlink()
        or full_target.is_symlink()
    ):
        return []
    abs_path = str(full_target)
    file_nodes = store.get_nodes_by_file(abs_path)
    return [node_to_dict(n) for n in file_nodes]


def query_graph(
    pattern: str,
    target: str,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Run a predefined graph query.

    Args:
        pattern: Query pattern. One of: callers_of, callees_of, imports_of,
                 importers_of, children_of, tests_for, inheritors_of, file_summary.
        target: The node name, qualified name, or file path to query about.
        repo_root: Repository root path. Auto-detected if omitted.

    Returns:
        Matching nodes and edges for the query.
    """
    if len(target) > 1000:
        return {
            "status": "error",
            "error": "Target too long (exceeds 1000 characters).",
        }

    store, root = _get_store(repo_root)
    try:
        if pattern not in _QUERY_PATTERNS:
            return {
                "status": "error",
                "error": f"Unknown pattern '{pattern}'. Available: {list(_QUERY_PATTERNS.keys())}",
            }

        # For callers_of, skip common builtins early (bare names only)
        if (
            pattern == "callers_of"
            and target in _BUILTIN_CALL_NAMES
            and "::" not in target
        ):
            return {
                "status": "ok",
                "pattern": pattern,
                "target": target,
                "description": _QUERY_PATTERNS[pattern],
                "summary": f"'{target}' is a common builtin — callers_of skipped to avoid noise.",
                "results": [],
                "edges": [],
            }

        node, qn = _resolve_query_target(target, store, root)
        if qn == "ambiguous":
            candidates = store.search_nodes(target, limit=5)
            return {
                "status": "ambiguous",
                "summary": f"Multiple matches for '{target}'. Please use a qualified name.",
                "candidates": [node_to_dict(c) for c in candidates],
            }

        if not node and pattern != "file_summary":
            return {
                "status": "not_found",
                "summary": f"No node found matching '{target}'.",
            }

        results: list[dict] = []
        edges_out: list[dict] = []

        if pattern == "callers_of":
            results = _handle_callers_of(qn, node, store, edges_out)
        elif pattern == "callees_of":
            results = _handle_callees_of(qn, store, edges_out)
        elif pattern == "imports_of":
            results = _handle_imports_of(qn, store, edges_out)
        elif pattern == "importers_of":
            results = _handle_importers_of(qn, node, store, root, edges_out)
            if not results and not node:
                 # Check for invalid target path return
                 full_target_raw = root / target
                 full_target = full_target_raw.resolve()
                 if not full_target.is_relative_to(root.resolve()) or full_target_raw.is_symlink() or full_target.is_symlink():
                      return {"status": "error", "summary": "Invalid target path"}
        elif pattern == "children_of":
            results = _handle_children_of(qn, store)
        elif pattern == "tests_for":
            results = _handle_tests_for(qn, node, target, store)
        elif pattern == "inheritors_of":
            results = _handle_inheritors_of(qn, store, edges_out)
        elif pattern == "file_summary":
            results = _handle_file_summary(target, store, root)
            if not results:
                 full_target_raw = root / target
                 full_target = full_target_raw.resolve()
                 if not full_target.is_relative_to(root.resolve()) or full_target_raw.is_symlink() or full_target.is_symlink():
                      return {"status": "error", "summary": "Invalid target path"}

        return {
            "status": "ok",
            "pattern": pattern,
            "target": target,
            "description": _QUERY_PATTERNS[pattern],
            "summary": f"Found {len(results)} result(s) for {pattern}('{target}')",
            "results": results,
            "edges": edges_out,
        }
    finally:
        store.close()
'''

start_marker = r'def query_graph\('
end_marker = r'# ---------------------------------------------------------------------------'

match_start = re.search(start_marker, content)
if not match_start:
    print("Could not find query_graph start")
    sys.exit(1)

# Find the next tool marker after query_graph
match_end = re.search(end_marker, content[match_start.start():])
if not match_end:
    print("Could not find next tool marker")
    sys.exit(1)

total_end_index = match_start.start() + match_end.start()

new_content = content[:match_start.start()] + replacement.strip() + "\n\n\n" + content[total_end_index:]

with open(file_path, 'w') as f:
    f.write(new_content)

print("Refactoring complete.")
