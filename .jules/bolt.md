## 2026-04-10 - [SQL Query Optimization for IN Clauses]
**Learning:** Using SQLite's `json_each(?)` function for variable-length IN clauses is not only more secure but also more performant as it allows for a single prepared statement, reducing query parsing overhead.
**Action:** Always prefer `json_each` for batch lookups in SQLite.

## 2026-04-14 - [Eliminate N+1 Queries with json_each Batch Fetching]
**Learning:** In graph traversal algorithms (like `get_impact_radius`) and bulk operations (like `embed_all_nodes`), retrieving nodes file-by-file creates an N+1 bottleneck. SQLite's `json_each` function provides a highly performant way to batch-fetch records by a common attribute (e.g., `file_path`) using a single query, significantly reducing database overhead.
**Action:** Always implement and utilize batch-fetching methods (e.g., `get_nodes_by_files`) using `json_each` and chunked parameter passing (e.g., batch size 450) when multiple database records need to be retrieved from a list of identifiers.
