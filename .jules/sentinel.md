## 2023-10-24 - [Path Traversal in tools.py and incremental.py]
**Vulnerability:** Found Path Traversal vulnerability where user input (file paths) was concatenated to paths (`root / rel_path`) without ensuring they don't escape the project root directory.
**Learning:** Concatenating path components using `/` without checking for bounds allows reading or modifying unauthorized system files.
**Prevention:** To prevent this, always build paths using `(base_path / user_path).resolve()` and explicitly verify boundaries using `if not resolved_path.is_relative_to(base_path.resolve()): continue`.
## 2025-04-04 - Fix Partial Path Execution and Command Injection in git invocations
**Vulnerability:** External process execution `subprocess.run(["git", "diff", ...])` was vulnerable to partial path execution (Bandit B607) and unsanitized command argument injection via the `base` parameter.
**Learning:** `git` diff paths could allow local PATH manipulation since the full path wasn't used, and an unchecked git ref (`base`) allowed argument injection even if not using `shell=True`.
**Prevention:** Resolve system binaries safely using `shutil.which` and use strict regex allowlists (e.g., `^[a-zA-Z0-9_./\^~:-]+$`) to validate all externally supplied command parameters before invocation.
