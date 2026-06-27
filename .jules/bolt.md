## 2024-05-26 - Replace fetchall() with direct cursor iteration

**Learning:** Using `.fetchall()` on SQLite cursors materializes large intermediate lists in memory. This is particularly problematic for queries that return many rows or rows with large text columns, leading to significant peak memory overhead.

**Action:** Globally replace `rows = cursor.fetchall()` and `for row in rows` with direct iteration over the cursor object `for row in cursor` to process results as they are yielded, significantly reducing peak memory consumption. When iterating directly, `fetchone()` is used to peek at the result where necessary, keeping in mind that it advances the cursor.

## 2026-05-28 - Isolated Mocking for Edge Case Testing

**Learning:** When testing edge cases in environments with missing heavy dependencies (like `networkx` or `tree-sitter`), using `sys.modules` to mock these dependencies *before* importing the target module allows for reliable unit testing without triggering `ModuleNotFoundError`.

**Action:** For specialized coverage tests, implement a `MockModule` that uses `__getattr__` to return `MagicMock()` and patch `sys.modules` prior to tool imports. This ensures that even deeply nested or lazy imports within the target module are safely handled during test execution.

## 2024-06-25 - Use str.translate over generator expressions for fast sanitization
**Learning:** In hot serialization loops (like returning large JSON responses containing node metadata), using a generator expression with `"".join(...)` to filter string characters is a significant performance bottleneck in Python.
**Action:** When filtering known character sets (like removing control characters), always define a pre-compiled mapping module constant (e.g., `_MAP = {i: None for i in range(32)}`) and use `str.translate()`, which pushes the iteration into optimized C code, yielding roughly 7.5x performance improvements.

## 2024-06-27 - SQLite initialization bottleneck optimization
**Learning:** Sequential `_conn.execute()` calls for individual `ALTER TABLE` or schema setups impose a measurable N+1 overhead loop when setting up new database connections.
**Action:** Bundle these operations into a cohesive SQL string list and apply them using a single `_conn.executescript()` call to eliminate round-trip overhead during instantiation.
