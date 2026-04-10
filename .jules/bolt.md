## 2026-04-10 - [SQL Query Optimization for IN Clauses]
**Learning:** Using SQLite's `json_each(?)` function for variable-length IN clauses is not only more secure but also more performant as it allows for a single prepared statement, reducing query parsing overhead.
**Action:** Always prefer `json_each` for batch lookups in SQLite.
