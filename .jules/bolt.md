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

## $(date +%Y-%m-%d) - Eliminate Redundant LOWER() calls in SQLite LIKE queries

**Learning:** By default, SQLite's `LIKE` operator is already case-insensitive for ASCII characters. Furthermore, SQLite's built-in `LOWER()` function also only operates on ASCII characters. Therefore, applying `LOWER()` to both sides of a `LIKE` operator is strictly redundant and causes unnecessary per-row function evaluation overhead during table scans.
**Action:** When writing `LIKE` queries in SQLite where case-insensitive ASCII comparison is sufficient, do not wrap the operands in `LOWER()`. This eliminates per-row evaluation overhead and optimizes the table scan speed.
