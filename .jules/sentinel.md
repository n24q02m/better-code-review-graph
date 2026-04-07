## 2026-04-07 - [SECURITY] Dynamic SQL IN Clause Generation

**Vulnerability:** Dynamic SQL string construction (CWE-89/B608) using f-strings or string concatenation to generate variable numbers of placeholders in SQL `IN` clauses.

**Learning:** Even when using bind variables for the values themselves, generating the placeholder string (`?,?,?`) dynamically triggers security warnings (Bandit B608) and can be less efficient than static queries.

**Prevention:** Use SQLite's `json_each(?)` function with `json.dumps(list)` to handle variable-length `IN` clauses with a fully static SQL string. For optional filters, use the `(? IS NULL OR field = ?)` pattern to keep the query structure fixed regardless of whether the filter is applied.
