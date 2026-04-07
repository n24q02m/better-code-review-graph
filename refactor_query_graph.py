import sys
import os

path = "src/better_code_review_graph/tools.py"
with open(path, "r") as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if line.startswith("def query_graph("):
        start_idx = i
    if start_idx != -1 and line.startswith("def get_review_context("):
        end_idx = i
        break

if start_idx == -1 or end_idx == -1:
    print(f"Could not find query_graph range: {start_idx} to {end_idx}")
    sys.exit(1)

# Back up a bit from end_idx to find the end of query_graph (it ends before get_review_context)
# query_graph ends with store.close() and Tool 4 comment.
while end_idx > start_idx and not lines[end_idx].startswith("# Tool 4"):
    end_idx -= 1

new_query_graph = """
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
        node, target, err = _resolve_query_target(store, target, root)
        if err:
            return err

        if not node and pattern != "file_summary":
            return {
                "status": "not_found",
                "summary": f"No node found matching '{target}'.",
            }

        qn = node.qualified_name if node else target
        results: list[dict[str, Any]] = []
        edges_out: list[dict[str, Any]] = []

        # Dispatch to pattern handlers
        if pattern == "callers_of":
            results, edges_out = _handle_callers_of(store, qn, node)
        elif pattern == "callees_of":
            results, edges_out = _handle_callees_of(store, qn)
        elif pattern == "imports_of":
            results, edges_out = _handle_imports_of(store, qn)
        elif pattern == "importers_of":
            results, edges_out, err = _handle_importers_of(store, target, node, root)
            if err:
                return err
        elif pattern == "children_of":
            results, edges_out = _handle_children_of(store, qn)
        elif pattern == "tests_for":
            results, edges_out = _handle_tests_for(store, qn, node, target)
        elif pattern == "inheritors_of":
            results, edges_out = _handle_inheritors_of(store, qn)
        elif pattern == "file_summary":
            results, edges_out, err = _handle_file_summary(store, target, root)
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

with open(path, "w") as f:
    f.writelines(lines[:start_idx] + [new_query_graph] + lines[end_idx:])
