## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.

## 2024-05-25 - Semantic Search Brute-Force Scan Optimization
**Learning:** In brute-force vector similarity scans across databases, recalculating the query vector's Euclidean norm inside the scan loop is redundant and costly.
**Action:** When performing brute-force operations in loops (like cosine similarity against a database of vectors), always precalculate query-level invariants (like the query vector's math.hypot norm) outside the loop.
