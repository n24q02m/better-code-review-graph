## 2023-10-24 - [Path Traversal in tools.py and incremental.py]
**Vulnerability:** Found Path Traversal vulnerability where user input (file paths) was concatenated to paths (`root / rel_path`) without ensuring they don't escape the project root directory.
**Learning:** Concatenating path components using `/` without checking for bounds allows reading or modifying unauthorized system files.
**Prevention:** To prevent this, always build paths using `(base_path / user_path).resolve()` and explicitly verify boundaries using `if not resolved_path.is_relative_to(base_path.resolve()): continue`.
## 2026-04-06 - Fix S603/S607 Git Command Injection Vulnerabilities
**Vulnerability:** The `get_changed_files` function passed unvalidated, user-controlled input (`base`) directly to `subprocess.run` for executing git diff, creating a command/flag injection risk (S603). Additionally, executing `git` using an unresolved partial path (S607) posed a potential PATH spoofing risk.
**Learning:** Security linters (Bandit) identified critical shell execution risks. Fixing them required carefully balancing regex strictness with git's actual syntax to avoid functional regressions (e.g., branch names with slashes, advanced refs like `HEAD^{commit}`), and ensuring tests accommodate the resolved absolute executable path.
**Prevention:** Always resolve external executables via `shutil.which('cmd')`. For user-provided input passed to subprocesses, enforce a strict regex allowlist (e.g., `^[a-zA-Z0-9_.~^/@{}-]+$`) and explicitly block leading hyphens (`startswith('-')`) to prevent option injection.
