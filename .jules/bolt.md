## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.

## 2026-04-10 - N+1 Query in Impact Radius
**Learning:** The `get_impact_radius` method performed an N+1 query pattern by calling `get_nodes_by_file` in a loop for each changed file.
**Action:** Implemented a batch-fetching method `get_nodes_by_files` in `GraphStore` using SQLite's `json_each` and used it to retrieve all seed nodes in a single query.
