# better-code-review-graph

Fork of code-review-graph with fixed multi-word search, qualified call resolution,
dual-mode embedding (ONNX local + cloud chain via `EMBEDDING_MODELS`), and output pagination.
See `AGENTS.md` va `README.md` de hieu architecture va configuration.

## Cau truc

- `src/better_code_review_graph/` -- Package chinh (src layout)
  - `server.py` -- FastMCP server, 7 tools: graph + query + review (3 main) + config (incl. setup_*) + security + help + config__open_relay (mcp-core relay helper)
  - `tools.py` -- MCP tool implementations (build, query, impact, review, search, embed, stats, docs, large functions)
  - `parser.py` -- Tree-sitter parsing (14 langs) + call target resolution
  - `graph.py` -- SQLite GraphStore, search, impact radius, NetworkX cache
  - `incremental.py` -- Git integration, file watching, incremental updates
  - `embeddings.py` -- Dual-mode embedding: ONNX local (qwen3-embed) + cloud chain (`EMBEDDING_MODELS`) via litellm passthrough (`mcp_core.llm`)
  - `relay_setup.py` -- `apply_config` env-applier used by the OAuth setup form (live setup UX = OAuth-AS browser form at `<PUBLIC_URL>/authorize`; the `ensure_config` create-session/poll path is legacy/unused)
  - `relay_schema.py` -- Relay form schema (embedding provider fields)
  - `docs/` -- Help tool documentation (graph.md, query.md, review.md, config.md, recipes.md, security.md)
  - `cli.py` -- CLI: starts MCP server (pure entry point)
  - `__init__.py` -- Version export
  - `__main__.py` -- `python -m` entry (calls cli.main)
  - `py.typed` -- PEP 561 marker
- `tests/` -- Mirror source modules
- `skills/` -- Claude Code skills (impact-audit, onboard-repo, refactor-check, review-delta, review-pr, security-sweep)
- `hooks/` -- SessionStart + UserPromptSubmit + PostToolUse hooks
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
                                     FastMCP server --> 7 tools (graph + query + review + config + security + help + config__open_relay)
```

- **Parser** (parser.py): Tree-sitter extracts nodes (File, Class, Function, Type, Test) and edges (CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON). Resolves same-file bare call targets to qualified names.
- **Graph** (graph.py): SQLite with WAL mode. Multi-word AND-logic search. GraphNode/GraphEdge dataclasses.
- **Incremental** (incremental.py): Git diff detection, file hash tracking, re-parses only changed files.
- **Embeddings** (embeddings.py): Dual-mode -- local ONNX (qwen3-embed, default, zero-config) or cloud via the `EMBEDDING_MODELS` chain (litellm passthrough, `mcp_core.llm`; order = fallback, empty = local). Fixed 768-dim storage.
- **Tools** (tools.py): Implementation layer for all graph operations. Output pagination via max_results.
- **Server** (server.py): 7 tools — graph (build/update/stats/embed/export/summarize), query (query/search/impact/large_functions/spot_check/renamed_in_diff/diff), review, config (status/set/cache_clear + setup_status/setup_start/setup_skip/setup_reset/setup_complete), security (scan/report/suppress/rule_list), help, config__open_relay (mcp-core relay helper). Returns JSON strings.

## Embedding + LLM backends

Embedding (cloud backend) + the LLM summarizer dispatch through `mcp_core.llm`
(litellm passthrough, `n24q02m-mcp-core[llm]`). No native provider SDKs are
imported directly.

Per-task model chains, CSV `provider/model,provider/model`, order = litellm fallback. Provider is inferred from the model prefix.

- `EMBEDDING_MODELS` -- chain embedding. Empty = local ONNX (qwen3-embed).
- `SUMMARY_MODELS` -- chain summarizer (graph `summarize` action). Empty = summaries disabled.
- **Local (default)**: `qwen3-embed` ONNX -- zero-config, ~570MB download on first use, 768-dim MRL truncation
- API key theo convention litellm `<PROVIDER>_API_KEY`. 7 provider servers goi y:

  | model prefix | key env var | get it at |
  |---|---|---|
  | `gemini/` | `GEMINI_API_KEY` | aistudio.google.com/apikey |
  | `openai/` (or bare) | `OPENAI_API_KEY` | platform.openai.com |
  | `jina_ai/` | `JINA_AI_API_KEY` | jina.ai/api-key |
  | `cohere/` | `COHERE_API_KEY` | dashboard.cohere.com |
  | `xai/` | `XAI_API_KEY` | console.x.ai |
  | `anthropic/` | `ANTHROPIC_API_KEY` | console.anthropic.com |
  | `vertex_express/` | `GOOGLE_VERTEX_EXPRESS_API_KEY` | cloud.google.com/vertex-ai/generative-ai/docs/start/express-mode/overview |

  For any other litellm provider (used via env passthrough), see https://docs.litellm.ai/docs/providers/<provider> for its `<PROVIDER>_API_KEY` name. Summarizer providers must expose a chat-completion API (Jina/Cohere do not).
- Custom endpoint (SSRF-guarded): `EMBEDDING_API_BASE` (embedding), `LLM_API_BASE` (summarizer)
- `DISABLE_LOCAL_EMBED` -- skip local ONNX download; `resolve_backend` returns `unavailable` (not local) when no cloud chain is configured
- Fixed 768-dim storage keeps the table schema valid across providers. Switching embedding MODEL changes the vector space; embeddings are tagged per provider and the cosine search restricts to the active provider, so a provider switch re-embeds rather than mixing incomparable vectors.
- Deprecated (honored one release voi warning): singular `EMBEDDING_MODEL`/`SUMMARY_MODEL` + `EMBEDDING_BACKEND` (backend gio suy ra tu chain rong hay khong). Router auto-detect cu "Jina > Gemini > OpenAI > Cohere" da bo.

### Manual config example

```json
{
  "mcpServers": {
    "crg": {
      "command": "uvx", "args": ["better-code-review-graph"],
      "env": {
        "EMBEDDING_MODELS": "jina_ai/jina-embeddings-v5-text-small,gemini/gemini-embedding-001",
        "SUMMARY_MODELS": "gemini/gemini-2.5-flash",
        "JINA_AI_API_KEY": "jina_xxx",
        "GEMINI_API_KEY": "AIza_xxx"
      }
    }
  }
}
```

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

## Secrets (skret + AWS SSM)

- skret SSM namespace: `/better-code-review-graph/prod` (region `ap-southeast-1`)
- CI: `skret env -e prod --path=/better-code-review-graph/prod --format=dotenv >> $GITHUB_ENV`
- Local dev: `skret run -e prod -- <cmd>` (uses AWS credential chain)

## Luu y quan trong

- Lazy imports cho heavy deps (tree-sitter, qwen3-embed, litellm via `mcp_core.llm`) -- tranh startup cost
- MCP tools return error strings (`return "Error: ..."`) -- KHONG raise exceptions
- GraphStore.upsert_edge takes EdgeInfo (fields: source, target), GraphEdge uses source_qualified/target_qualified
- `_make_qualified()` builds qualified names as `file_path::name` or `file_path::parent.name`
- Supported languages: Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++, Solidity

## E2E

Driven by `mcp-core/scripts/e2e/` (matrix-locked, 15 configs). Run a single config from this repo via `make e2e` (proxy) or directly:

```
cd ../mcp-core && uv run --project scripts/e2e python -m e2e.driver <config-id>
```

Configs for this repo: `crg`.

t2-non-interaction: paste optional cloud LLM keys (Jina/Gemini/OpenAI/Cohere).

Tier policy:

- **T0** (precommit + CI on PR / main push) - runs without upstream identity. Skret keys not required.
- **T2 non-interaction** (`make e2e-config CONFIG=<id>` locally) - driver pre-fills relay form from skret AWS SSM `/better-code-review-graph/prod` (`ap-southeast-1`). No user gate.
- **T2 interaction** - driver fills relay form, then prints upstream user-gate URL; user signs in / types OTP at provider. Driver enforces per-flow timeouts (device-code 900s, oauth-redirect 300s, browser-form 600s) and emits `[poll] elapsed=Xs remaining=Ys status=<body>` every 30s. On timeout, container logs + last `setup-status` are saved to `<tmp>/e2e-diag/` BEFORE teardown for post-mortem.

Multi-user remote mode (deployment property; not a separate config) requires `MCP_DCR_SERVER_SECRET` in the same skret namespace - driver refuses to start the container without it when `PUBLIC_URL` is set.

References: `mcp-core/scripts/e2e/matrix.yaml`, `~/.claude/skills/mcp-dev/references/e2e-full-matrix.md` (harness-readiness gate), `~/.claude/skills/mcp-dev/references/secrets-skret.md` (per-server credential layout), `~/.claude/skills/mcp-dev/references/multi-user-pattern.md` (per-JWT-sub isolation).
