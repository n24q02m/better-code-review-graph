## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.

## 2024-05-25 - N+1 File Node Queries Bottleneck
**Learning:** Functions that process many files simultaneously (like `get_impact_radius` expanding seed files, and `embed_all_nodes` scanning the full codebase) suffered from N+1 query bottlenecks due to sequentially calling `get_nodes_by_file(f)` in a loop over files. This became exceptionally slow on larger codebases.
**Action:** Implemented `get_nodes_by_files` which leverages SQLite's `json_each` to fetch all nodes for a list of file paths in a single batched query, eliminating the N+1 loop and drastically improving performance for file-oriented batch operations.
