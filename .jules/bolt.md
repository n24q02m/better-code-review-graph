## 2024-05-24 - N+1 Graph Queries Bottleneck
**Learning:** SQLite backend graph traversal functions in `tools.py` suffer from N+1 query bottlenecks when resolving target node objects one-by-one from edges.
**Action:** When resolving node relationships, collect target qualified names first and batch fetch using `get_nodes_by_qualified_names` to retrieve nodes, preventing N+1 queries. Note that `imports_of` and `importers_of` only return dictionaries of qualified names or file paths, not full node objects, and thus do not require this optimization.
## 2024-05-24 - N+1 Query Fix in Embeddings
**Learning:** `EmbeddingStore.embed_nodes` had a significant N+1 query problem because it executed a `SELECT` statement in a loop to check for existing hashes node by node.
**Action:** When iterating over nodes to check existing database state, pre-fetch all necessary records outside the loop using a batched `SELECT ... WHERE qualified_name IN (SELECT value FROM json_each(?))` with a serialized JSON list to completely eliminate N+1 query bottlenecks.
