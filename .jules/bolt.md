## 2026-04-10 - [SQL Query Optimization for IN Clauses]
**Learning:** Using SQLite's `json_each(?)` function for variable-length IN clauses is not only more secure but also more performant as it allows for a single prepared statement, reducing query parsing overhead.
**Action:** Always prefer `json_each` for batch lookups in SQLite.

## 2026-04-10 - [Pushing large IN clauses down to SQLite using json_each]
**Learning:** SQLite's `SQLITE_MAX_VARIABLE_NUMBER` limit (default 999) requires chunking standard `IN (?, ?, ?)` parameterized queries. However, by using the pattern `IN (SELECT value FROM json_each(?))` and passing a single JSON array string as the parameter (`json.dumps(list_of_values)`), the limit is bypassed entirely because it's only one parameter. Additionally, pushing large lists of target attributes (e.g. `target_qualified` sets) to SQLite avoids transferring massive amounts of irrelevant rows to Python for in-memory filtering.
**Action:** Use `json_each(?)` for both source and target constraints when fetching subsets from large database tables, allowing large sets to be processed in a single query execution.
