import sys


def refactor():
    filepath = 'src/better_code_review_graph/tools.py'
    with open(filepath) as f:
        content = f.read()

    # Define new functions
    new_functions = """
def _resolve_query_target(
    store,
    root: Path,
    target: str,
    pattern: str,
):
    \"\"\"Helper to resolve query target node.

    Returns:
        (resolved_node, resolved_target_name, error_response)
    \"\"\"
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
            return (
                None,
                target,
                {
                    "status": "ambiguous",
                    "summary": f"Multiple matches for '{target}'. Please use a qualified name.",
                    "candidates": [node_to_dict(c) for c in candidates],
                },
            )

    if not node and pattern != "file_summary":
        return (
            None,
            target,
            {
                "status": "not_found",
                "summary": f"No node found matching '{target}'.",
            },
        )

    return node, target, None


def _handle_callers_of(store, qn: str, node):
    results = []
    edges_out = []
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

    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))
    return results, edges_out


def _handle_callees_of(store, qn: str):
    results = []
    edges_out = []
    qns = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "CALLS":
            qns.append(e.target_qualified)
            edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_tgt in qns:
            if qn_tgt in node_map:
                results.append(node_to_dict(node_map[qn_tgt]))
    return results, edges_out


def _handle_imports_of(store, qn: str):
    results = []
    edges_out = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "IMPORTS_FROM":
            results.append({"import_target": e.target_qualified})
            edges_out.append(edge_to_dict(e))
    return results, edges_out


def _handle_importers_of(store, root: Path, target: str, node):
    results = []
    edges_out = []
    # Find edges where target matches this file
    if node is not None:
        abs_target = node.file_path
    else:
        full_target_raw = root / target
        full_target = full_target_raw.resolve()
        if (
            not full_target.is_relative_to(root.resolve())
            or full_target_raw.is_symlink()
            or full_target.is_symlink()
        ):
            return (
                [],
                [],
                {
                    "status": "error",
                    "summary": "Invalid target path",
                },
            )
        abs_target = str(full_target)
    for e in store.get_edges_by_target(abs_target):
        if e.kind == "IMPORTS_FROM":
            results.append({"importer": e.source_qualified, "file": e.file_path})
            edges_out.append(edge_to_dict(e))
    return results, edges_out, None


def _handle_children_of(store, qn: str):
    results = []
    edges_out = []
    qns = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "CONTAINS":
            qns.append(e.target_qualified)
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_tgt in qns:
            if qn_tgt in node_map:
                results.append(node_to_dict(node_map[qn_tgt]))
    return results, edges_out


def _handle_tests_for(store, qn: str, target: str, node):
    results = []
    edges_out = []
    qns = []
    for e in store.get_edges_by_target(qn):
        if e.kind == "TESTED_BY":
            qns.append(e.source_qualified)
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
    return results, edges_out


def _handle_inheritors_of(store, qn: str):
    results = []
    edges_out = []
    qns = []
    for e in store.get_edges_by_target(qn):
        if e.kind in ("INHERITS", "IMPLEMENTS"):
            qns.append(e.source_qualified)
            edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))
    return results, edges_out


def _handle_file_summary(store, root: Path, target: str):
    results = []
    edges_out = []
    full_target_raw = root / target
    full_target = full_target_raw.resolve()
    if (
        not full_target.is_relative_to(root.resolve())
        or full_target_raw.is_symlink()
        or full_target.is_symlink()
    ):
        return (
            [],
            [],
            {
                "status": "error",
                "summary": "Invalid target path",
            },
        )
    abs_path = str(full_target)
    file_nodes = store.get_nodes_by_file(abs_path)
    for n in file_nodes:
        results.append(node_to_dict(n))
    return results, edges_out, None
"""

    # Define refactored query_graph
    refactored_query_graph = """
def query_graph(
    pattern: str,
    target: str,
    repo_root: str | None = None,
) -> dict[str, Any]:
    \"\"\"Run a predefined graph query.

    Args:
        pattern: Query pattern. One of: callers_of, callees_of, imports_of,
                 importers_of, children_of, tests_for, inheritors_of, file_summary.
        target: The node name, qualified name, or file path to query about.
        repo_root: Repository root path. Auto-detected if omitted.

    Returns:
        Matching nodes and edges for the query.
    \"\"\"
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
        # "Who calls .map()?" returns hundreds of useless hits.
        # Qualified names (e.g. "utils.py::map") bypass this filter.
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

        # Resolve target
        node, resolved_target, error_resp = _resolve_query_target(
            store, root, target, pattern
        )
        if error_resp:
            return error_resp
        target = resolved_target

        qn = node.qualified_name if node else target
        results: list[dict] = []
        edges_out: list[dict] = []

        if pattern == "callers_of":
            results, edges_out = _handle_callers_of(store, qn, node)
        elif pattern == "callees_of":
            results, edges_out = _handle_callees_of(store, qn)
        elif pattern == "imports_of":
            results, edges_out = _handle_imports_of(store, qn)
        elif pattern == "importers_of":
            results, edges_out, err = _handle_importers_of(store, root, target, node)
            if err:
                return err
        elif pattern == "children_of":
            results, edges_out = _handle_children_of(store, qn)
        elif pattern == "tests_for":
            results, edges_out = _handle_tests_for(store, qn, target, node)
        elif pattern == "inheritors_of":
            results, edges_out = _handle_inheritors_of(store, qn)
        elif pattern == "file_summary":
            results, edges_out, err = _handle_file_summary(store, root, target)
            if err:
                return err

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
"""

    # We need to find the query_graph function and replace it.
    # It starts at 'def query_graph(' and ends before 'def get_review_context('.

    import re
    start_pattern = r'def query_graph\('
    end_pattern = r'def get_review_context\('

    start_match = re.search(start_pattern, content)
    end_match = re.search(end_pattern, content)

    if not start_match or not end_match:
        print("Could not find start or end of query_graph")
        sys.exit(1)

    # Insert new functions before query_graph
    new_content = content[:start_match.start()] + new_functions + refactored_query_graph + content[end_match.start():]

    with open(filepath, 'w') as f:
        f.write(new_content)

if __name__ == "__main__":
    refactor()
