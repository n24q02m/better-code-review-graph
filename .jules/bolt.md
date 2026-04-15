## 2026-04-10 - [SQL Query Optimization for IN Clauses]
**Learning:** Using SQLite's `json_each(?)` function for variable-length IN clauses is not only more secure but also more performant as it allows for a single prepared statement, reducing query parsing overhead.
**Action:** Always prefer `json_each` for batch lookups in SQLite.
## 2025-04-15 - [Batch File Query Optimization using json_each]
**Learning:** SQLite's built-in `json_each` function provides a highly efficient way to implement batch-fetching queries without hitting parameter limits or dynamically formatting large `IN (?, ?, ?)` clauses. This is particularly useful in graph traversal and embedding algorithms where an N+1 query problem commonly occurs when looping through files sequentially.
**Action:** Always look for `for file in files:` loops that trigger separate DB queries (like `get_nodes_by_file`). Replace them with a batched alternative like `get_nodes_by_files` that uses `IN (SELECT value FROM json_each(?))` with a single JSON string parameter. Ensure chunking is still applied (e.g., chunk size 450) to keep memory usage bounded and adhere to standard batch size patterns.
