# Performance Learnings

## Node Map Optimization in Tool Handlers

In `src/better_code_review_graph/tools.py`, several handler functions (`_handle_callers_of`, `_handle_callees_of`, `_handle_children_of`, `_handle_tests_for`, `_handle_inheritors_of`) followed a pattern of:
1. Fetching nodes by qualified names.
2. Creating a `node_map` from the result.
3. Iterating over the original list of qualified names and looking them up in the map to maintain order/handle duplicates.

However, `store.get_nodes_by_qualified_names` already returns the matching `GraphNode` objects. Since the goal in these handlers was simply to populate the `results` list with `node_to_dict(n)` for all found nodes, the `node_map` and the second loop were redundant if the exact input order or duplicate handling (beyond what `get_nodes_by_qualified_names` does) wasn't strictly required by the API contract.

Optimizing this to `results.extend(node_to_dict(n) for n in nodes)` simplifies the code and avoids unnecessary dictionary creation and lookups.
