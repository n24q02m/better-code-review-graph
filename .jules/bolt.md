# Bolt: N+1 Query Fixes via Batched Resolution

## Discovery
Discovered a severe N+1 query issue in `src/better_code_review_graph/tools.py` where graph node resolution loops were hitting SQLite individually for each edge (e.g., `store.get_node` inside a loop).

## Fix
Implemented `GraphStore.get_nodes_by_qualified_names` to fetch multiple nodes in batches (size 450 to stay under `SQLITE_MAX_VARIABLE_NUMBER`).
Refactored `children_of`, `callers_of`, `callees_of`, `tests_for`, and `inheritors_of` to use list comprehensions to gather all required qualified names and issue a single batched query, mapping results efficiently.

## Measurement
Using a 50k node/edge graph setup:
- **Baseline (N+1)**: ~0.72s to resolve node children.
- **Optimized (Batched)**: ~0.16s to resolve node children.
- **Improvement**: ~4.5x faster lookup execution.
