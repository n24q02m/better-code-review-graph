## 2026-06-08 - Fixed setup_status accuracy by ensuring state refresh
**Learning:** The `setup_status` tool was returning stale module-level `_state` because it didn't call `resolve_credential_state()` which updates the global state. Additionally, `PerPluginStore` is only consulted in HTTP mode to avoid cross-process leaks in stdio mode.
**Action:** Always call `resolve_credential_state()` in tools that report credential status, and ensure tests use `MCP_TRANSPORT=http` when verifying store-dependent behavior.
