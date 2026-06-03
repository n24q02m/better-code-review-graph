## 2024-05-26 - Replace fetchall() with direct cursor iteration

**Learning:** Using `.fetchall()` on SQLite cursors materializes large intermediate lists in memory. This is particularly problematic for queries that return many rows or rows with large text columns, leading to significant peak memory overhead.

**Action:** Globally replace `rows = cursor.fetchall()` and `for row in rows` with direct iteration over the cursor object `for row in cursor` to process results as they are yielded, significantly reducing peak memory consumption. When iterating directly, `fetchone()` is used to peek at the result where necessary, keeping in mind that it advances the cursor.

## 2026-05-28 - Isolated Mocking for Edge Case Testing

**Learning:** When testing edge cases in environments with missing heavy dependencies (like `networkx` or `tree-sitter`), using `sys.modules` to mock these dependencies *before* importing the target module allows for reliable unit testing without triggering `ModuleNotFoundError`.

**Action:** For specialized coverage tests, implement a `MockModule` that uses `__getattr__` to return `MagicMock()` and patch `sys.modules` prior to tool imports. This ensures that even deeply nested or lazy imports within the target module are safely handled during test execution.

## 2026-06-03 - Native set operations in Breadth-First Search

**Learning:** When performing Breadth-First Search (BFS) over `networkx` directed graphs, explicitly iterating over `nxg.neighbors()` and `nxg.predecessors()` with Python `for` loops and `if` conditions adds significant overhead, especially on dense graphs.

**Action:** Replace nested `for` loops in BFS frontiers with native C-level `set()` operations (`intersection_update`, `difference_update`, `update`). Adding the entire frontier to the visited set upfront (`visited.update(frontier)`) also simplifies the logic and reduces iterations. This reduces Python execution overhead and measurably improves performance for large-scale graph traversals.
