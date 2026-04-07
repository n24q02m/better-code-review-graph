## 2023-10-24 - [Path Traversal in tools.py and incremental.py]
**Vulnerability:** Found Path Traversal vulnerability where user input (file paths) was concatenated to paths (`root / rel_path`) without ensuring they don't escape the project root directory.
**Learning:** Concatenating path components using `/` without checking for bounds allows reading or modifying unauthorized system files.
**Prevention:** To prevent this, always build paths using `(base_path / user_path).resolve()` and explicitly verify boundaries using `if not resolved_path.is_relative_to(base_path.resolve()): continue`.

## 2026-04-07 - [Prevent structural dynamic SQL in graph queries]
**Vulnerability:** Structural dynamic SQL construction (string concatenation) in `search_nodes` was used to handle optional filters.
**Learning:** Building SQL queries by concatenating strings is a risk pattern that can lead to structural vulnerabilities and makes security audits difficult.
**Prevention:** Use fully static SQL query strings with the `(? IS NULL OR field = ?)` pattern for optional filters and parameterized `LIMIT` clauses to ensure structural integrity and rely entirely on safe parameter binding.
