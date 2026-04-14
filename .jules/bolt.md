## 2026-04-14 - Eliminate N+1 Queries with get_nodes_by_files
**Learning:** Found N+1 anti-pattern in `get_impact_radius` (`graph.py`) and `embed_all_nodes` (`embeddings.py`), where nodes were fetched individually by file path in loops.
**Action:** Implemented a new `get_nodes_by_files` method in `GraphStore` utilizing SQLite `json_each` and batched execution (size 450) to efficiently fetch nodes by multiple file paths in a single query. Used it to resolve the bottlenecks.
