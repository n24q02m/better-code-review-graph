## 2025-05-15 - [Standalone Test Mocking]

**Learning:** Standalone testing in this repository often requires mocking heavy dependencies (networkx, tree_sitter, alembic) using sys.modules before importing the target module to avoid environment-specific failures.
**Action:** Use a prefix of sys.modules mocks in new test files when standard pytest discovery fails due to missing optional or local-path dependencies.

## 2025-05-15 - [CI Failure: Import Errors and Mocking]

**Vulnerability:** CI failures due to E402 (import position) and ModuleNotFoundError in conftest.
**Learning:** When mocking dependencies via sys.modules in tests, ensure all standard library imports are at the very top. Use # noqa: E402 for codebase imports that must follow the mocking logic. Also, explicitly mock submodules (e.g., mcp.types) if they are imported individually in the codebase to prevent pytest discovery failures.
**Prevention:** Include a comprehensive modules_to_mock list and verify with both isolated python execution and pytest.
