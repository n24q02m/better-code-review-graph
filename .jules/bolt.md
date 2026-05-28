## 2025-05-15 - [Standalone Test Mocking]

**Learning:** Standalone testing in this repository often requires mocking heavy dependencies (networkx, tree_sitter, alembic) using sys.modules before importing the target module to avoid environment-specific failures.
**Action:** Use a prefix of sys.modules mocks in new test files when standard pytest discovery fails due to missing optional or local-path dependencies.
