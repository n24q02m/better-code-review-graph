## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.

## 2024-05-24 - N+1 Query Bottleneck in Edge Traversal
**Learning:** `find_dependents` had an N+1 query bottleneck because it was fetching nodes by file and then repeatedly calling `get_edges_by_target` for each node's qualified name individually.
**Action:** Created `get_edges_by_targets` in `GraphStore` to accept a list of targets and used SQLite's `json_each` to batch fetch the edges. Used this batch method in `find_dependents` to reduce DB calls.
