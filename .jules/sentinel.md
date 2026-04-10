## 2023-10-24 - [Path Traversal in tools.py and incremental.py]
**Vulnerability:** Found Path Traversal vulnerability where user input (file paths) was concatenated to paths (`root / rel_path`) without ensuring they don't escape the project root directory.
**Learning:** Concatenating path components using `/` without checking for bounds allows reading or modifying unauthorized system files.
**Prevention:** To prevent this, always build paths using `(base_path / user_path).resolve()` and explicitly verify boundaries using `if not resolved_path.is_relative_to(base_path.resolve()): continue`.

## 2026-04-08 - [Command Injection (Bandit B607) in subprocess calls]
**Vulnerability:** Found `subprocess.run` calls that relied on partial executable names (like `"git"`) without an absolute path, which creates a command injection risk (Bandit B607) if the environment's `PATH` variable is manipulated to point to a malicious binary.
**Learning:** `subprocess.run` searches the `PATH` environment variable when `shell=False` and a relative path is provided, making it susceptible to hijacking.
**Prevention:** Always resolve the absolute path to system executables using `shutil.which("executable_name")` and raise an error if not found before passing it to `subprocess.run`.

## 2026-04-10 - [SQL Injection in Search Nodes]
**Vulnerability:** SQL statement in `search_nodes` was constructed dynamically using f-strings and string concatenation for the `WHERE` clause, even though parameterized values were used for inputs. This triggered B608 security flags.
**Learning:** Dynamic SQL construction, even with parameters, can be flagged by security tools and potentially lead to vulnerabilities if parts of the SQL structure itself (like table or column names) are influenced by input.
**Prevention:** Use static SQL literals passed directly to `execute()` calls. Handle optional filters using the `(? IS NULL OR column = ?)` pattern to keep the query structure constant regardless of parameters.
