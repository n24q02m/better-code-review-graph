# better-code-review-graph

Fork of code-review-graph with fixed multi-word search, qualified call resolution,
dual-mode embedding (ONNX local + Cohere cloud), and output pagination.
See `AGENTS.md` va `README.md` de hieu architecture va configuration.

## Cau truc

- `src/better_code_review_graph/` -- Package chinh (src layout)
  - `server.py` -- FastMCP server, 5 tools: graph + query + review (3 main) + config (incl. setup_*) + help
  - `tools.py` -- MCP tool implementations (build, query, impact, review, search, embed, stats, docs, large functions)
  - `parser.py` -- Tree-sitter parsing (13 langs) + call target resolution
  - `graph.py` -- SQLite GraphStore, search, impact radius, NetworkX cache
  - `incremental.py` -- Git integration, file watching, incremental updates
  - `embeddings.py` -- Dual-mode embedding: ONNX local (qwen3-embed) + cloud (Jina/Gemini/OpenAI/Cohere)
  - `relay_setup.py` -- Zero-config relay: create session, poll for config
  - `relay_schema.py` -- Relay form schema (embedding provider fields)
  - `docs/` -- Help tool documentation (graph.md, query.md, review.md, config.md)
  - `cli.py` -- CLI: starts MCP server (pure entry point)
  - `__init__.py` -- Version export
  - `__main__.py` -- `python -m` entry (calls cli.main)
  - `py.typed` -- PEP 561 marker
- `tests/` -- Mirror source modules
- `skills/` -- Claude Code skills (build-graph, review-delta, review-pr)
- `hooks/` -- SessionStart + PostToolUse hooks
- `.claude-plugin/` -- Plugin manifest + marketplace metadata

## Lenh thuong dung

```bash
uv sync --group dev                # Cai dependencies
uv run pytest                      # Test tat ca
uv run pytest tests/test_graph.py::test_function_name -v  # Test don le
uv run ruff check .                # Lint
uv run ruff format .               # Format
uv run ruff check --fix . && uv run ruff format .  # Fix
uv run ty check                    # Type check (ty lenient config)
uv run better-code-review-graph        # Chay MCP server (stdio, default)
```

## Cau hinh quan trong

- **Python 3.13 bat buoc** -- `requires-python = "==3.13.*"`
- Ruff: line-length 88, target py313, rules E/F/W/I/UP/B/C4, ignore E501
- ty: lenient (unresolved-import, unresolved-attribute, possibly-missing-attribute all "ignore")

## Architecture

```
Source files --> Tree-sitter parser --> SQLite graph (nodes + edges)
                                          |
                                     NetworkX BFS --> Impact radius
                                          |
                                     Embedding store --> Semantic search
                                          |
                                     FastMCP server --> 5 tools (graph + query + review + config + help)
```

- **Parser** (parser.py): Tree-sitter extracts nodes (File, Class, Function, Type, Test) and edges (CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON). Resolves same-file bare call targets to qualified names.
- **Graph** (graph.py): SQLite with WAL mode. Multi-word AND-logic search. GraphNode/GraphEdge dataclasses.
- **Incremental** (incremental.py): Git diff detection, file hash tracking, re-parses only changed files.
- **Embeddings** (embeddings.py): Dual-mode -- local ONNX (qwen3-embed, default, zero-config) or cloud multi-provider (Jina > Gemini > OpenAI > Cohere, auto-detected from env vars). Fixed 768-dim storage.
- **Tools** (tools.py): Implementation layer for all graph operations. Output pagination via max_results.
- **Server** (server.py): 5 tools — graph (build/update/stats/embed), query (query/search/impact/large_functions), review, config (status/set/cache_clear + setup_status/setup_start/setup_skip/setup_reset/setup_complete), help. Returns JSON strings.

## Embedding backends

- **Local (default)**: `qwen3-embed` ONNX -- zero-config, ~570MB download on first use, 768-dim MRL truncation
- **Cloud (multi-provider)**: Auto-detected from env vars, priority: Jina > Gemini > OpenAI > Cohere
  - `JINA_AI_API_KEY` -- Jina AI (httpx REST)
  - `GEMINI_API_KEY` / `GOOGLE_API_KEY` -- Google Gemini (google-genai SDK)
  - `OPENAI_API_KEY` -- OpenAI (openai SDK)
  - `COHERE_API_KEY` / `CO_API_KEY` -- Cohere (cohere ClientV2)
- **Explicit**: Set `EMBEDDING_BACKEND=local|cloud` to override auto-detection
- `EMBEDDING_MODEL` -- override model name (provider auto-detected from model prefix)
- Fixed 768-dim storage -- switching backend does NOT invalidate existing vectors

## Pytest

- `asyncio_mode = "auto"` -- KHONG can `@pytest.mark.asyncio`
- Default timeout: 30 seconds per test
- `addopts = "--tb=short -q"`
- Coverage: 95%+ enforced

## Release & Deploy

- Conventional Commits. Tag format: `v{version}`
- CD: PSR v10 -> PyPI (uv publish) -> Docker multi-arch (amd64 + arm64) -> MCP Registry
- Docker images: `n24q02m/better-code-review-graph`

## Pre-commit hooks

1. Ruff lint (`--fix --target-version=py313`) + format
2. ty type check
3. pytest (`--tb=short -q --timeout=30`)
4. Commit message: enforce Conventional Commits

## Infisical

- Project: `e40d27b4-b8c5-4b53-ad56-97c15b3057d7`

## Luu y quan trong

- Lazy imports cho heavy deps (tree-sitter, qwen3-embed, cohere) -- tranh startup cost
- MCP tools return error strings (`return "Error: ..."`) -- KHONG raise exceptions
- GraphStore.upsert_edge takes EdgeInfo (fields: source, target), GraphEdge uses source_qualified/target_qualified
- `_make_qualified()` builds qualified names as `file_path::name` or `file_path::parent.name`
- Supported languages: Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++, Solidity
