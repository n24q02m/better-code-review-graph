## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.
## 2026-04-12 - Prevent N+1 Query in file node fetching
**Learning:** Functions that look up multiple files sequentially (like `get_impact_radius` and `embed_all_nodes`) suffer from N+1 query performance hits when executing `get_nodes_by_file` iteratively.
**Action:** Use batch operations `get_nodes_by_files` leveraging SQLite's `json_each` to fetch nodes by a list of files in a single robust query. Avoid modifying the environment's `pyproject.toml` unless explicitly requested.
