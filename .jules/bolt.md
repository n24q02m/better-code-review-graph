# Performance Learnings

## Node Map Optimization in Tool Handlers

In `src/better_code_review_graph/tools.py`, several handler functions (`_handle_callers_of`, `_handle_callees_of`, `_handle_children_of`, `_handle_tests_for`, `_handle_inheritors_of`) followed a pattern of:
1. Fetching nodes by qualified names.
2. Creating a `node_map` from the result.
3. Iterating over the original list of qualified names and looking them up in the map.

While the map creation is necessary to preserve the input order and handle duplicates correctly (as expected by some performance tests), the manual loop for appending to `results` can be refactored into a more idiomatic generator expression using `results.extend()`.

Refactored from:
```python
node_map = {n.qualified_name: n for n in nodes}
for qn_src in qns:
    if qn_src in node_map:
        results.append(node_to_dict(node_map[qn_src]))
```

To:
```python
node_map = {n.qualified_name: n for n in nodes}
results.extend(node_to_dict(node_map[qn]) for qn in qns if qn in node_map)
```

This refinement maintains the correct ordering and duplication behavior while following Python best practices for list extension.
