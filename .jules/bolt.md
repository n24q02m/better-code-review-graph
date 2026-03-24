
## Performance Optimization: Batching Inheritor Lookups

*   **Date:** $(date -I)
*   **Component:** `query_graph` -> `inheritors_of` (`src/better_code_review_graph/tools.py`)
*   **Issue:** N+1 Query in Inheritor Resolution. Resolving inheritors involved looping through all `INHERITS`/`IMPLEMENTS` edges and calling `store.get_node` individually for each source.
*   **Optimization:** Replaced the loop of individual queries with a single, batched lookup using a new `get_nodes_by_qualified_names` method on `GraphStore` (in `src/better_code_review_graph/graph.py`). This method uses an `IN` clause batched at 450 items to stay safely under SQLite's variable limit.
*   **Impact:** Measured ~16% speedup (from 0.076s to 0.064s) per resolution on a simulated dataset of 2000 inheritor nodes in a single flat hierarchy, while preserving precise output ordering and reducing overall DB roundtrips significantly.
