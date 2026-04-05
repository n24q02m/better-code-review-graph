## 2023-10-24 - [Path Traversal in tools.py and incremental.py]
**Vulnerability:** Found Path Traversal vulnerability where user input (file paths) was concatenated to paths (`root / rel_path`) without ensuring they don't escape the project root directory.
**Learning:** Concatenating path components using `/` without checking for bounds allows reading or modifying unauthorized system files.
**Prevention:** To prevent this, always build paths using `(base_path / user_path).resolve()` and explicitly verify boundaries using `if not resolved_path.is_relative_to(base_path.resolve()): continue`.

## 2026-04-05 - SQL Injection in Search Nodes
**Vulnerability:** Potential SQL Injection in `search_nodes` due to dynamic SQL construction with f-strings and string concatenation for optional filters and limit clauses.
**Learning:** Using f-strings or string concatenation for SQL queries, even if some parts are parameterized, can lead to vulnerabilities and trigger SAST alerts (B608).
**Prevention:** Always use a single static SQL literal with parameterized placeholders. For optional filters, the `(? IS NULL OR column = ?)` pattern allows the query structure to remain constant. Parameterize the `LIMIT` clause directly instead of concatenating it.
