## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.

## 2026-04-05 - [PERF] Optimized Semantic Search with Vector Normalization
**Learning:** Brute-force cosine similarity scans can be significantly accelerated without external dependencies by:
1. Pre-normalizing embedding vectors during storage.
2. Using `array.array('f', blob)` for faster binary decoding than `struct.unpack`.
3. Calculating dot products with `math.sumprod` (Python 3.12+), which is equivalent to cosine similarity for normalized vectors.
4. Using `heapq.nlargest` for top-k selection instead of full list sorting.
**Action:** Always pre-normalize vectors if cosine similarity is the primary distance metric, and leverage `math.sumprod` and `array.array` for hot loops in vector operations.
