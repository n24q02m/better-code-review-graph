## 2024-05-26 - Replace fetchall() with direct cursor iteration

**Learning:** Using `.fetchall()` on SQLite cursors materializes large intermediate lists in memory. This is particularly problematic for queries that return many rows or rows with large text columns, leading to significant peak memory overhead.

**Action:** Globally replace `rows = cursor.fetchall()` and `for row in rows` with direct iteration over the cursor object `for row in cursor` to process results as they are yielded, significantly reducing peak memory consumption. When iterating directly, `fetchone()` is used to peek at the result where necessary, keeping in mind that it advances the cursor.

## 2026-05-28 - Isolated Mocking for Edge Case Testing

**Learning:** When testing edge cases in environments with missing heavy dependencies (like `networkx` or `tree-sitter`), using `sys.modules` to mock these dependencies *before* importing the target module allows for reliable unit testing without triggering `ModuleNotFoundError`.

**Action:** For specialized coverage tests, implement a `MockModule` that uses `__getattr__` to return `MagicMock()` and patch `sys.modules` prior to tool imports. This ensures that even deeply nested or lazy imports within the target module are safely handled during test execution.
## 2024-06-09 - Safe SQLite Iteration vs. The Halloween Problem

**Learning:** Replacing `.fetchall()` with direct cursor iteration (`for row in cursor:`) is a great memory optimization for reading data, but it is dangerous if the processing loop mutates the same database table or performs slow, blocking operations (like external API calls). Keeping the read cursor open during mutations can cause unpredictable iteration behavior (the "Halloween problem") or lock contention (`OperationalError`), as seen in `summarizer.py` and `temporal.py`.

**Action:** Only use direct cursor iteration for read-only, fast-processing loops. Retain `.fetchall()` when the loop modifies the database, updates the same table being queried, or holds the lock open for a long time due to external I/O.
