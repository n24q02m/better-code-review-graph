## 2023-10-24 - [Path Traversal in tools.py and incremental.py]
**Vulnerability:** Found Path Traversal vulnerability where user input (file paths) was concatenated to paths (`root / rel_path`) without ensuring they don't escape the project root directory.
**Learning:** Concatenating path components using `/` without checking for bounds allows reading or modifying unauthorized system files.
**Prevention:** To prevent this, always build paths using `(base_path / user_path).resolve()` and explicitly verify boundaries using `if not resolved_path.is_relative_to(base_path.resolve()): continue`.
## 2025-05-22 - Database connection leak in get_docs_section
**Vulnerability:** Resource leak (unclosed database connection).
**Learning:** Tools that call _get_store must ensure that the returned GraphStore is closed, even if they only use it to get the project root.
**Prevention:** Always use try-finally or context managers when dealing with GraphStore instances.
