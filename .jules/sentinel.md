## 2023-10-24 - [Path Traversal in tools.py and incremental.py]
**Vulnerability:** Found Path Traversal vulnerability where user input (file paths) was concatenated to paths (`root / rel_path`) without ensuring they don't escape the project root directory.
**Learning:** Concatenating path components using `/` without checking for bounds allows reading or modifying unauthorized system files.
**Prevention:** To prevent this, always build paths using `(base_path / user_path).resolve()` and explicitly verify boundaries using `if not resolved_path.is_relative_to(base_path.resolve()): continue`.

## 2026-04-08 - [Command Injection (Bandit B607) in subprocess calls]
**Vulnerability:** Found `subprocess.run` calls that relied on partial executable names (like `"git"`) without an absolute path, which creates a command injection risk (Bandit B607) if the environment's `PATH` variable is manipulated to point to a malicious binary.
**Learning:** `subprocess.run` searches the `PATH` environment variable when `shell=False` and a relative path is provided, making it susceptible to hijacking.
**Prevention:** Always resolve the absolute path to system executables using `shutil.which("executable_name")` and raise an error if not found before passing it to `subprocess.run`.

## 2026-04-10 - [Fixed Dynamic SQL IN Clause Generation]
**Vulnerability:** Found dynamic SQL IN clause generation where placeholders were constructed using f-strings and `",".join("?")`, triggering Bandit B608 and creating a SQL injection risk.
**Learning:** Constructing SQL queries by joining placeholders based on list length is a common but risky pattern that often triggers security scanners and can lead to vulnerabilities if not handled with absolute care.
**Prevention:** Use SQLite's `json_each(?)` function in combination with `json.dumps(list)` to handle variable-length IN clauses with a single, static query string and a single bind parameter.
