## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.

## 2024-05-24 - N+1 Queries Bottleneck When Finding Nodes by Files
**Learning:** Functions like `embed_all_nodes` and `get_impact_radius` call `get_nodes_by_file` iteratively for each file in a list, resulting in N+1 queries.
**Action:** Implement `get_nodes_by_files` to batch fetch nodes by their file paths using SQLite's `json_each` to eliminate N+1 queries when querying for multiple files.
