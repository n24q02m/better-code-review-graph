## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.
## 2026-04-03 - [Refactoring and N+1 Query Fix]
**Learning:** Large monolithic functions like query_graph benefit greatly from modular refactoring into private handlers. Batched node fetching via get_nodes_by_qualified_names is the standard pattern for avoiding N+1 queries in this repository.
**Action:** Always look for opportunities to modularize complex logic and use batch fetchers for graph nodes.
