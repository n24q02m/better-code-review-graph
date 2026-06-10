with open("src/better_code_review_graph/tools.py") as f:
    content = f.read()

# Update _handle_importers_of
old_importers = """def _handle_importers_of(
    store: Any,
    abs_target: str,
    results: list[dict],
    edges_out: list[dict],
    *,
    as_of: str = "",
) -> None:
    for e in store.get_edges_by_target(
        abs_target, kind="IMPORTS_FROM", as_of=as_of, fallback=False
    ):
        results.append({"importer": e.source_qualified, "file": e.file_path})
        edges_out.append(edge_to_dict(e))"""

new_importers = """def _handle_importers_of(
    store: Any,
    node: Any,
    abs_target: str,
    results: list[dict],
    edges_out: list[dict],
    *,
    as_of: str = "",
) -> None:
    search_targets = [abs_target]
    if node and node.name and node.name != abs_target:
        search_targets.append(node.name)

    edges = store.search_edges_by_target_names(
        search_targets, kind="IMPORTS_FROM", as_of=as_of
    )
    for e in edges:
        results.append({"importer": e.source_qualified, "file": e.file_path})
        edges_out.append(edge_to_dict(e))"""

content = content.replace(old_importers, new_importers)

# Update _handle_tests_for
old_tests = """def _handle_tests_for(
    store: Any,
    node: Any,
    target: str,
    qn: str,
    results: list[dict],
    *,
    as_of: str = "",
) -> None:
    qns = []
    for e in store.get_edges_by_target(
        qn, kind="TESTED_BY", as_of=as_of, fallback=False
    ):
        qns.append(e.source_qualified)
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))"""

new_tests = """def _handle_tests_for(
    store: Any,
    node: Any,
    target: str,
    qn: str,
    results: list[dict],
    *,
    as_of: str = "",
) -> None:
    search_targets = [qn]
    if node and node.name and node.name != qn:
        search_targets.append(node.name)
    elif target and target != qn:
        search_targets.append(target)

    edges = store.search_edges_by_target_names(
        search_targets, kind="TESTED_BY", as_of=as_of
    )
    qns = [e.source_qualified for e in edges]
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))"""

content = content.replace(old_tests, new_tests)

# Update _handle_inheritors_of
old_inheritors = """def _handle_inheritors_of(
    store: Any,
    qn: str,
    results: list[dict],
    edges_out: list[dict],
    *,
    as_of: str = "",
) -> None:
    qns = []
    for e in store.get_edges_by_target(
        qn, kind=("INHERITS", "IMPLEMENTS"), as_of=as_of, fallback=False
    ):
        qns.append(e.source_qualified)
        edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))"""

new_inheritors = """def _handle_inheritors_of(
    store: Any,
    node: Any,
    qn: str,
    results: list[dict],
    edges_out: list[dict],
    *,
    as_of: str = "",
) -> None:
    search_targets = [qn]
    if node and node.name and node.name != qn:
        search_targets.append(node.name)

    edges = store.search_edges_by_target_names(
        search_targets, kind=("INHERITS", "IMPLEMENTS"), as_of=as_of
    )
    qns = []
    for e in edges:
        qns.append(e.source_qualified)
        edges_out.append(edge_to_dict(e))
    if qns:
        nodes = store.get_nodes_by_qualified_names(qns, as_of=as_of)
        node_map = {n.qualified_name: n for n in nodes}
        for qn_src in qns:
            if qn_src in node_map:
                results.append(node_to_dict(node_map[qn_src]))"""

content = content.replace(old_inheritors, new_inheritors)

# Update dispatcher calls
content = content.replace(
    "            _handle_importers_of(\n                store, resolved_qn_or_path, results, edges_out, as_of=as_of\n            )",
    "            _handle_importers_of(\n                store, node, resolved_qn_or_path, results, edges_out, as_of=as_of\n            )",
)
content = content.replace(
    "            _handle_inheritors_of(\n                store, resolved_qn_or_path, results, edges_out, as_of=as_of\n            )",
    "            _handle_inheritors_of(\n                store, node, resolved_qn_or_path, results, edges_out, as_of=as_of\n            )",
)

with open("src/better_code_review_graph/tools.py", "w") as f:
    f.write(content)
