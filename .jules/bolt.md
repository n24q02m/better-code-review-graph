## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.
## 2026-04-10 - N+1 Embedding Metadata Lookups
**Learning:** Checking for existing embeddings one-by-one in `embed_nodes` created an N+1 query bottleneck during large-scale re-indexing.
**Action:** Use `batch_size` to chunk node lists and batch-fetch existing metadata using SQLite's `json_each` function to significantly improve performance.
