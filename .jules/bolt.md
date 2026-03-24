## Performance Optimizations

### SQLite Query Batching (N+1 Problem Elimination)
- **Problem**: When resolving graph relationships (e.g., `callers_of`, `callees_of`), querying the `nodes` table individually for each associated edge target/source results in an N+1 query bottleneck.
- **Solution**: Implemented a `get_nodes_by_qualified_names` method in `GraphStore` that accepts a list of qualified names and executes a batched `IN` query.
- **Implementation Details**:
  - The SQLite default maximum variable number (`SQLITE_MAX_VARIABLE_NUMBER`) is often 999.
  - To safely batch queries without hitting this limit, deduplicate the input list and chunk the query into batch sizes well under the limit (e.g., `450`).
  - When replacing individual lookup loops, use a two-pass approach:
    1. Collect all necessary qualified names from edges.
    2. Execute the batch lookup and construct a mapping (dictionary) from qualified name to node.
    3. Iterate over the edges again, resolving the node reference via the dictionary lookup.
- **Impact**: In a localized benchmark with 5,000 edges resolving to various nodes, query time decreased from ~0.12s to ~0.09s (a ~1.3x speedup). This benefit scales with the size of the graph and the number of relationships returned, significantly improving perceived latency for large repositories.
