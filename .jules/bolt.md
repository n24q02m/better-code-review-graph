## 2024-05-19 - GraphStore N+1 Query Resolution
**Learning:** Resolving nodes in `tools.py` during relationship queries (e.g., `callers_of`, `callees_of`, `children_of`) triggers N+1 SQL queries because it iterates over the fetched edges and calls `store.get_node()` individually.
**Action:** Establish `get_nodes_by_qualified_names` in `GraphStore` that does batch resolution. The query execution in `tools.py` should first collect all unique target qualified names from edges, then query `get_nodes_by_qualified_names`, to prevent bottleneck.
