## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.

## 2024-05-27 - [Brute-force Cosine Similarity Scan]
**Learning:** Brute-force cosine similarity scans in Python can be a significant bottleneck when searching large embedding stores. The cost of redundant `math.hypot` calls and Python generator overhead in dot product calculations adds up.
**Action:** Precalculate query-level invariants (like the query vector norm) outside the similarity loop. Leverage NumPy for vectorized batch calculations if available, as it provides a major performance boost (over 10x for the math portion). For pure Python fallbacks, use `struct.unpack` to avoid unnecessary list conversions and `map`/`operator.mul` for efficient dot products.
