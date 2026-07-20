## 2024-05-26 - Replace fetchall() with direct cursor iteration

**Learning:** Using `.fetchall()` on SQLite cursors materializes large intermediate lists in memory. This is particularly problematic for queries that return many rows or rows with large text columns, leading to significant peak memory overhead.

**Action:** Globally replace `rows = cursor.fetchall()` and `for row in rows` with direct iteration over the cursor object `for row in cursor` to process results as they are yielded, significantly reducing peak memory consumption. When iterating directly, `fetchone()` is used to peek at the result where necessary, keeping in mind that it advances the cursor.

## 2026-05-28 - Isolated Mocking for Edge Case Testing

**Learning:** When testing edge cases in environments with missing heavy dependencies (like `networkx` or `tree-sitter`), using `sys.modules` to mock these dependencies *before* importing the target module allows for reliable unit testing without triggering `ModuleNotFoundError`.

**Action:** For specialized coverage tests, implement a `MockModule` that uses `__getattr__` to return `MagicMock()` and patch `sys.modules` prior to tool imports. This ensures that even deeply nested or lazy imports within the target module are safely handled during test execution.

## 2024-06-25 - Use str.translate over generator expressions for fast sanitization
**Learning:** In hot serialization loops (like returning large JSON responses containing node metadata), using a generator expression with `"".join(...)` to filter string characters is a significant performance bottleneck in Python.
**Action:** When filtering known character sets (like removing control characters), always define a pre-compiled mapping module constant (e.g., `_MAP = {i: None for i in range(32)}`) and use `str.translate()`, which pushes the iteration into optimized C code, yielding roughly 7.5x performance improvements.

## 2026-06-23 - Eliminate N+1 Query Patterns in Batch Operations

**Learning:** Direct SQL execution within a loop structure causes N+1 query patterns, leading to significant performance degradation as the data set grows. In SQLite, this is especially impactful during write-heavy operations like temporal closing.

**Action:** Refactor row-by-row updates into batch operations using `UPDATE ... WHERE ... IN (SELECT value FROM json_each(?))`. This pushes the filtering logic into the database engine and reduces the overhead of multiple `execute()` calls and potential transaction management. Always use `cursor.rowcount` to track affected rows when removing the manual loop counter.

## 2024-07-17 - Prevent N+1 queries when traversing graphs from multiple source nodes
**Learning:** Resolving targets (e.g. callees, imports, children, inheritors) for graph visualization/traversal previously resulted in N+1 database roundtrips. When expanding multiple edges, executing `get_edges_by_source` or `get_edges_by_target` per original node generated excessive SQLite overhead, especially for dense repositories.
**Action:** Replace looped individual lookups with batched SQLite queries utilizing `search_edges_by_source_names` or `search_edges_by_target_names` which process multiple node identifiers in a single roundtrip via `json_each`.

## 2024-11-20 - Optimize array length computation in SQLite correlated subqueries
**Learning:** Using a correlated scalar subquery `(SELECT COUNT(*) FROM json_each(?))` solely to compute the length of a JSON array bound as a parameter causes the database engine to parse and evaluate the array in O(N) time for every row during a full table scan, degrading performance.
**Action:** Replace the scalar subquery with a bound integer parameter computed externally in Python (e.g., `len(words)`). This shifts the work from an O(N) per-row database evaluation to a single O(1) Python evaluation, significantly speeding up query execution for full-table scans.
