## 2024-05-26 - Replace fetchall() with direct cursor iteration

**Learning:** Using `.fetchall()` on SQLite cursors materializes large intermediate lists in memory. This is particularly problematic for queries that return many rows or rows with large text columns, leading to significant peak memory overhead.

**Action:** Globally replace `rows = cursor.fetchall()` and `for row in rows` with direct iteration over the cursor object `for row in cursor` to process results as they are yielded, significantly reducing peak memory consumption. When iterating directly, `fetchone()` is used to peek at the result where necessary, keeping in mind that it advances the cursor.

## 2026-05-28 - Isolated Mocking for Edge Case Testing

**Learning:** When testing edge cases in environments with missing heavy dependencies (like `networkx` or `tree-sitter`), using `sys.modules` to mock these dependencies *before* importing the target module allows for reliable unit testing without triggering `ModuleNotFoundError`.

**Action:** For specialized coverage tests, implement a `MockModule` that uses `__getattr__` to return `MagicMock()` and patch `sys.modules` prior to tool imports. This ensures that even deeply nested or lazy imports within the target module are safely handled during test execution.
## 2026-06-04 - [Performance] Batching edge searches in _handle_callees_of
**Learning:** Found an N+1 query pattern in `_handle_callees_of` where only the qualified name was searched for callees, while the system supports bare name edges. Searching for both sequentially would be N=2, but using a batched IN clause is more efficient and consistent with `_handle_callers_of`.
**Action:** Implemented `GraphStore.search_edges_by_source_names` to support batched source searches and updated `_handle_callees_of` to use it.
