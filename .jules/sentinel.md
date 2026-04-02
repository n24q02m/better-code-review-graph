## 2023-10-24 - [Path Traversal in tools.py and incremental.py]
**Vulnerability:** Found Path Traversal vulnerability where user input (file paths) was concatenated to paths (`root / rel_path`) without ensuring they don't escape the project root directory.
**Learning:** Concatenating path components using `/` without checking for bounds allows reading or modifying unauthorized system files.
**Prevention:** To prevent this, always build paths using `(base_path / user_path).resolve()` and explicitly verify boundaries using `if not resolved_path.is_relative_to(base_path.resolve()): continue`.

## 2024-04-02 - [Structural SQL Injection in Find Large Nodes]
**Vulnerability:** A structural dynamic SQL query was built using f-strings for optional WHERE clauses, which is a risk pattern even if parameters are correctly bound.
**Learning:** Structural dynamic SQL (dynamically appending clauses) can be harder to audit and potentially vulnerable if clause logic itself is influenced by input.
**Prevention:** Use a fully parameterized static SQL query with  pattern for all optional filters. This ensures the query structure remains constant and is fully handled by the database driver's parameter binding.

## 2024-04-02 - [Structural SQL Injection in Find Large Nodes]
**Vulnerability:** A structural dynamic SQL query was built using f-strings for optional WHERE clauses, which is a risk pattern even if parameters are correctly bound.
**Learning:** Structural dynamic SQL (dynamically appending clauses) can be handled safely but is often flagged and can be brittle.
**Prevention:** Use a fully parameterized static SQL query with `(? IS NULL OR column = ?)` pattern for all optional filters. This ensures the query structure remains constant and follows best practices for parameterized queries.
