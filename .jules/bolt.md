## 2024-05-26 - Replace fetchall() with direct cursor iteration

**Learning:** Using `.fetchall()` on SQLite cursors materializes large intermediate lists in memory. This is particularly problematic for queries that return many rows or rows with large text columns, leading to significant peak memory overhead.

**Action:** Globally replace `rows = cursor.fetchall()` and `for row in rows` with direct iteration over the cursor object `for row in cursor` to process results as they are yielded, significantly reducing peak memory consumption. When iterating directly, `fetchone()` is used to peek at the result where necessary, keeping in mind that it advances the cursor.

## 2026-05-28 - Isolated Mocking for Edge Case Testing

**Learning:** When testing edge cases in environments with missing heavy dependencies (like `networkx` or `tree-sitter`), using `sys.modules` to mock these dependencies *before* importing the target module allows for reliable unit testing without triggering `ModuleNotFoundError`.

**Action:** For specialized coverage tests, implement a `MockModule` that uses `__getattr__` to return `MagicMock()` and patch `sys.modules` prior to tool imports. This ensures that even deeply nested or lazy imports within the target module are safely handled during test execution.

## 2024-05-29 - Use native set operations for Breadth-First Search (BFS) graph traversals
**Learning:** During BFS graph traversals, especially on dense graphs like NetworkX directional graphs, using Python `for` loops to iterate through neighbors and predecessors is slow.
**Action:** Replace `for` loops with native C-level `set()` operations (e.g., `update`, `difference_update`, `intersection_update`) to efficiently filter out already-visited nodes and compute the next frontier, significantly improving traversal performance. Add the entire frontier to the visited set upfront to avoid redundant processing within the same tier.
