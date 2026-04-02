## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.

## 2025-05-15 - [Batch fetch optimization in semantic_search]
**Learning:** Iteratively fetching nodes by qualified name in a loop (N+1 pattern) creates significant database overhead, especially for vector search results where the limit might be high.
**Action:** Always collect target identifiers first and use batch fetching methods like `get_nodes_by_qualified_names` to retrieve all required data in a single query. Use a mapping dictionary to re-associate metadata (like similarity scores) and preserve the original result order.
