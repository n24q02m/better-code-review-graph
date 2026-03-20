# Style Guide - better-code-review-graph

## Architecture
Knowledge graph MCP server for token-efficient code reviews. Python, single-package repo.

## Python
- Formatter/Linter: Ruff (default config)
- Type checker: ty
- Test: pytest + pytest-asyncio
- Package manager: uv
- SDK: fastmcp
- Core deps: tree-sitter, networkx, SQLite, qwen3-embed (ONNX), litellm

## Code Patterns
- Tree-sitter parsing for 12 languages
- SQLite graph storage with NetworkX BFS for impact analysis
- Dual-mode embedding: local ONNX (qwen3-embed) + LiteLLM cloud
- Incremental updates via git diff and file watching
- Call target resolution: bare names resolved to qualified names

## Commits
Conventional Commits (feat:, fix:, chore:, docs:, refactor:, test:).

## Security
Validate file paths. Bound graph traversal depth. Prevent unbounded output via pagination.
