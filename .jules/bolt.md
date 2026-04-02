## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.

## 2025-05-24 - N+1 Query in Impact Radius Resolution
**Learning:** `get_impact_radius` in `graph.py` previously performed N+1 `get_node` calls to resolve seed and impacted nodes into full objects after BFS traversal.
**Action:** Use `get_nodes_by_qualified_names` to batch fetch nodes by their qualified names in a single query after the BFS frontier expansion is complete.
