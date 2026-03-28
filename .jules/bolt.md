## 2025-02-18 - [Optimize node relationship resolution with batch fetching]
**Learning:** Resolving relationships node by node using `get_node()` inside graph queries like `callers_of` or `children_of` creates an N+1 query bottleneck against SQLite.
**Action:** Always collect target/source qualified names first, deduplicate into a set, and batch fetch nodes using `get_nodes_by_qualified_names()` with batched `IN` clauses to maintain high performance across large codebases.
