## 2023-10-24 - [Path Traversal in tools.py and incremental.py]
**Vulnerability:** Found Path Traversal vulnerability where user input (file paths) was concatenated to paths (`root / rel_path`) without ensuring they don't escape the project root directory.
**Learning:** Concatenating path components using `/` without checking for bounds allows reading or modifying unauthorized system files.
**Prevention:** To prevent this, always build paths using `(base_path / user_path).resolve()` and explicitly verify boundaries using `if not resolved_path.is_relative_to(base_path.resolve()): continue`.
## 2025-02-23 - Prevent Resource Exhaustion via Search Tools Length Limits
**Vulnerability:** The MCP tools `semantic_search_nodes` and `query_graph` accepted arbitrarily long strings for `query` and `target` respectively, passing them directly to the SQLite backend and potentially cloud embedding backends, creating a vector for Denial of Service (DoS) attacks through resource exhaustion.
**Learning:** Tools exposed via an MCP server can receive excessively large inputs from clients, and relying entirely on backend database checks or API limits isn't enough; input length limits are required at the function boundary.
**Prevention:** Always validate and clamp input string lengths (e.g. max 1000 chars) on any tool parameter that will be used in a database search query or sent to an external embedding API.
