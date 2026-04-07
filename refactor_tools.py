import sys
import os

path = "src/better_code_review_graph/tools.py"
with open(path, "r") as f:
    lines = f.readlines()

insertion_idx = -1
for i, line in enumerate(lines):
    if line.startswith("def query_graph("):
        insertion_idx = i
        break

if insertion_idx == -1:
    print("Could not find query_graph")
    sys.exit(1)

helpers = """
def _resolve_query_target(
    store: GraphStore, target: str, root: Path
) -> tuple[Any | None, str, dict[str, Any] | None]:
    \"\"\"Resolve target to a node or path, or return ambiguity error.\"\"\"
    node = store.get_node(target)
    if not node:
        full_target_raw = root / target
        try:
            full_target = full_target_raw.resolve()
            if (
                full_target.is_relative_to(root.resolve())
                and not full_target_raw.is_symlink()
                and not full_target.is_symlink()
            ):
                abs_target = str(full_target)
                node = store.get_node(abs_target)
        except (OSError, ValueError):
            pass

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
    return node, target, None


def _fetch_nodes_to_dicts(store: GraphStore, qns: list[str]) -> list[dict[str, Any]]:
    \"\"\"Batch fetch nodes by qualified names and convert to dicts.\"\"\"
    if not qns:
        return []
    nodes = store.get_nodes_by_qualified_names(qns)
    node_map = {n.qualified_name: n for n in nodes}
    results = []
    for qn in qns:
        if qn in node_map:
            results.append(node_to_dict(node_map[qn]))
    return results


def _handle_callers_of(
    store: GraphStore, qn: str, node: Any | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    \"\"\"Logic for callers_of pattern.\"\"\"
    results: list[dict[str, Any]] = []
    edges_out: list[dict[str, Any]] = []
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
        results = _fetch_nodes_to_dicts(store, qns)
    return results, edges_out


def _handle_callees_of(
    store: GraphStore, qn: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    \"\"\"Logic for callees_of pattern.\"\"\"
    results: list[dict[str, Any]] = []
    edges_out: list[dict[str, Any]] = []
    qns = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "CALLS":
            qns.append(e.target_qualified)
            edges_out.append(edge_to_dict(e))
    if qns:
        results = _fetch_nodes_to_dicts(store, qns)
    return results, edges_out


def _handle_imports_of(
    store: GraphStore, qn: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    \"\"\"Logic for imports_of pattern.\"\"\"
    results: list[dict[str, Any]] = []
    edges_out: list[dict[str, Any]] = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "IMPORTS_FROM":
            results.append({"import_target": e.target_qualified})
            edges_out.append(edge_to_dict(e))
    return results, edges_out


def _handle_importers_of(
    store: GraphStore, target: str, node: Any | None, root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    \"\"\"Logic for importers_of pattern.\"\"\"
    results: list[dict[str, Any]] = []
    edges_out: list[dict[str, Any]] = []
    if node is not None:
        abs_target = node.file_path
    else:
        full_target_raw = root / target
        try:
            full_target = full_target_raw.resolve()
            if (
                not full_target.is_relative_to(root.resolve())
                or full_target_raw.is_symlink()
                or full_target.is_symlink()
            ):
                return [], [], {"status": "error", "summary": "Invalid target path"}
            abs_target = str(full_target)
        except (OSError, ValueError):
            return [], [], {"status": "error", "summary": "Invalid target path"}

    for e in store.get_edges_by_target(abs_target):
        if e.kind == "IMPORTS_FROM":
            results.append({"importer": e.source_qualified, "file": e.file_path})
            edges_out.append(edge_to_dict(e))
    return results, edges_out, None


def _handle_children_of(
    store: GraphStore, qn: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    \"\"\"Logic for children_of pattern.\"\"\"
    results: list[dict[str, Any]] = []
    edges_out: list[dict[str, Any]] = []
    qns = []
    for e in store.get_edges_by_source(qn):
        if e.kind == "CONTAINS":
            qns.append(e.target_qualified)
    if qns:
        results = _fetch_nodes_to_dicts(store, qns)
    return results, edges_out


def _handle_tests_for(
    store: GraphStore, qn: str, node: Any | None, target: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    \"\"\"Logic for tests_for pattern.\"\"\"
    results: list[dict[str, Any]] = []
    edges_out: list[dict[str, Any]] = []
    qns = []
    for e in store.get_edges_by_target(qn):
        if e.kind == "TESTED_BY":
            qns.append(e.source_qualified)
    if qns:
        results = _fetch_nodes_to_dicts(store, qns)

    # Also search by naming convention
    name = node.name if node else target
    test_nodes = store.search_nodes(f"test_{name}", limit=10)
    test_nodes += store.search_nodes(f"Test{name}", limit=10)
    seen = {r.get("qualified_name") for r in results}
    for t in test_nodes:
        if t.qualified_name not in seen and t.is_test:
            results.append(node_to_dict(t))
    return results, edges_out


def _handle_inheritors_of(
    store: GraphStore, qn: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    \"\"\"Logic for inheritors_of pattern.\"\"\"
    results: list[dict[str, Any]] = []
    edges_out: list[dict[str, Any]] = []
    qns = []
    for e in store.get_edges_by_target(qn):
        if e.kind in ("INHERITS", "IMPLEMENTS"):
            qns.append(e.source_qualified)
            edges_out.append(edge_to_dict(e))
    if qns:
        results = _fetch_nodes_to_dicts(store, qns)
    return results, edges_out


def _handle_file_summary(
    store: GraphStore, target: str, root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    \"\"\"Logic for file_summary pattern.\"\"\"
    results: list[dict[str, Any]] = []
    edges_out: list[dict[str, Any]] = []
    full_target_raw = root / target
    try:
        full_target = full_target_raw.resolve()
        if (
            not full_target.is_relative_to(root.resolve())
            or full_target_raw.is_symlink()
            or full_target.is_symlink()
        ):
            return [], [], {"status": "error", "summary": "Invalid target path"}
        abs_path = str(full_target)
    except (OSError, ValueError):
        return [], [], {"status": "error", "summary": "Invalid target path"}

    file_nodes = store.get_nodes_by_file(abs_path)
    for n in file_nodes:
        results.append(node_to_dict(n))
    return results, edges_out, None

"""

with open(path, "w") as f:
    f.writelines(lines[:insertion_idx] + [helpers + "\n"] + lines[insertion_idx:])
