## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.
## 2025-05-22 - Optimized callees_of N+1 query bottleneck
**Learning:** The `callees_of` pattern was performing a database fetch for every edge found, similar to the previously fixed `callers_of` issue. Batching these fetches using `get_nodes_by_qualified_names` significantly improves performance for dense call graphs.
**Action:** Always check for `get_node` calls inside loops when implementing or refactoring graph traversal patterns in `tools.py`.
