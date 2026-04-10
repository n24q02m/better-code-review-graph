## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.
## 2024-05-24 - N+1 Graph Queries Bottleneck (Files to Nodes)
**Learning:** `get_nodes_by_file` calls placed inside loops (such as iterating over `all_files` in `embed_all_nodes` or `changed_files` in `get_impact_radius`) cause severe N+1 query performance degradation (taking ~17s for 5000 files vs ~0.2s when batched).
**Action:** When multiple files need their nodes retrieved, use the batched `get_nodes_by_files` method which uses SQLite `json_each` to fetch them in one query.
