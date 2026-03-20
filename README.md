# better-code-review-graph

mcp-name: io.github.n24q02m/better-code-review-graph

**Knowledge graph for token-efficient code reviews -- fixed search, configurable embeddings, qualified call resolution.**

[![CI](https://github.com/n24q02m/better-code-review-graph/actions/workflows/ci.yml/badge.svg)](https://github.com/n24q02m/better-code-review-graph/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/n24q02m/better-code-review-graph/graph/badge.svg)](https://codecov.io/gh/n24q02m/better-code-review-graph)
[![PyPI](https://img.shields.io/pypi/v/better-code-review-graph?logo=pypi&logoColor=white)](https://pypi.org/project/better-code-review-graph/)
[![Docker](https://img.shields.io/docker/v/n24q02m/better-code-review-graph?label=docker&logo=docker&logoColor=white&sort=semver)](https://hub.docker.com/r/n24q02m/better-code-review-graph)
[![License: MIT](https://img.shields.io/github/license/n24q02m/better-code-review-graph)](LICENSE)

[![Python](https://img.shields.io/badge/Python_3.13-3776AB?logo=python&logoColor=white)](#)
[![MCP](https://img.shields.io/badge/MCP-000000?logo=anthropic&logoColor=white)](#)
[![semantic-release](https://img.shields.io/badge/semantic--release-e10079?logo=semantic-release&logoColor=white)](https://github.com/python-semantic-release/python-semantic-release)
[![Renovate](https://img.shields.io/badge/renovate-enabled-1A1F6C?logo=renovatebot&logoColor=white)](https://developer.mend.io/)

Fork of [code-review-graph](https://github.com/tirth8205/code-review-graph) with critical bug fixes, configurable embeddings, and production CI/CD. Parses your codebase with [Tree-sitter](https://tree-sitter.github.io/tree-sitter/), builds a structural graph of functions/classes/imports, and gives Claude (or any MCP client) precise context so it reads only what matters.

---

## Why Better

| Feature | code-review-graph | better-code-review-graph |
|:--------|:------------------|:-------------------------|
| Multi-word search | Broken (literal substring match) | AND-logic word splitting (`"firebase auth"` matches both `verify_firebase_token` and `FirebaseAuth`) |
| callers_of accuracy | Empty results (bare name targets) | Qualified name resolution -- same-file calls resolved to `file::name` |
| Embedding model | all-MiniLM-L6-v2 + torch (1.1 GB) | qwen3-embed ONNX + LiteLLM (200 MB) |
| Output size | Unbounded (500K+ chars possible) | Paginated (default 500 nodes, truncation metadata) |
| Plugin hooks | Invalid PostEdit/PostGit events | Valid PostToolUse (Write, Edit, Bash) |
| Plugin MCP | Duplicate registration (.mcp.json + plugin.json) | Single source (plugin.json only) |
| Python version | 3.10+ | 3.13 (pinned) |
| CI/CD | GitHub Actions basic | PSR + Docker multi-arch + MCP Registry |
| Test coverage | Unknown | 95%+ enforced |

All fixes are submitted upstream as standalone PRs (see [Upstream PRs](#upstream-prs)). If all are merged, this repo will be archived.

---

## Quick Start

### Prerequisites

- **Python 3.13** (required -- `requires-python = "==3.13.*"`)

### Option 1: uvx (Recommended)

```jsonc
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph", "serve"],
      "env": {
        // -- optional: cloud embeddings via LiteLLM
        // "API_KEYS": "GOOGLE_API_KEY:AIza...",
        // -- optional: LiteLLM Proxy (selfhosted gateway)
        // "LITELLM_PROXY_URL": "http://10.0.0.20:4000",
        // "LITELLM_PROXY_KEY": "sk-your-virtual-key"
        // -- without API_KEYS, uses built-in local qwen3-embed ONNX (zero-config)
      }
    }
  }
}
```

### Option 2: pip

```bash
pip install better-code-review-graph
better-code-review-graph install   # creates .mcp.json in project root
```

### Option 3: Docker

```jsonc
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "crg-data:/data",
        "-e", "API_KEYS",
        "n24q02m/better-code-review-graph:latest"
      ],
      "env": {
        // -- optional: cloud embeddings
        // "API_KEYS": "GOOGLE_API_KEY:AIza..."
      }
    }
  }
}
```

### Option 4: Claude Code Plugin

```bash
claude plugin install n24q02m/better-code-review-graph@better-code-review-graph
```

Then open your project and tell Claude:

```
Build the code review graph for this project
```

---

## MCP Tools

Claude uses these automatically once the graph is built.

| Tool | Description |
|:-----|:------------|
| `build_or_update_graph_tool` | Build or incrementally update the graph. Default: incremental (changed files only). |
| `get_impact_radius_tool` | Blast radius of changed files. Shows which functions, classes, files are affected. Paginated with `max_results`. |
| `get_review_context_tool` | Token-optimized review context with structural summary, source snippets, and review guidance. |
| `query_graph_tool` | Predefined queries: callers_of, callees_of, imports_of, importers_of, children_of, tests_for, inheritors_of, file_summary. |
| `semantic_search_nodes_tool` | Search code entities by name/keyword or semantic similarity (requires embeddings). |
| `embed_graph_tool` | Compute vector embeddings for semantic search. Uses dual-mode backend. |
| `list_graph_stats_tool` | Graph size, languages, node/edge breakdown, embedding count. |
| `get_docs_section_tool` | Retrieve specific documentation sections for minimal token usage. |
| `find_large_functions_tool` | Find functions/classes exceeding a line-count threshold for decomposition audits. |

---

## Embedding Backends

Embeddings enable semantic search (vector similarity instead of keyword matching). Two backends are available:

| Backend | Config | Size | Description |
|:--------|:-------|:-----|:------------|
| **local** (default) | Nothing needed | ~570 MB (first use) | qwen3-embed ONNX. Zero-config. Downloaded on first `embed_graph_tool` call. |
| **litellm** | `API_KEYS` or `LITELLM_PROXY_URL` | 0 MB | Cloud providers via LiteLLM (Gemini, OpenAI, Cohere, etc.). |

- **Auto-detection**: If `API_KEYS` or `LITELLM_PROXY_URL` is set, uses LiteLLM. Otherwise, uses local ONNX.
- **Override**: Set `EMBEDDING_BACKEND=local` or `EMBEDDING_BACKEND=litellm` explicitly.
- **Fixed 768-dim storage**: All embeddings stored at 768 dimensions via MRL truncation. Switching backends does NOT invalidate existing vectors.
- **Lazy loading**: Model downloads on first embed call, not on server start.

---

## CLI Reference

```bash
better-code-review-graph install     # Register MCP server with Claude Code (creates .mcp.json)
better-code-review-graph init        # Alias for install
better-code-review-graph build       # Full graph build (parse all files)
better-code-review-graph update      # Incremental update (changed files only)
better-code-review-graph watch       # Auto-update on file changes
better-code-review-graph status      # Show graph statistics
better-code-review-graph serve       # Start MCP server (stdio transport)
```

---

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `EMBEDDING_BACKEND` | (auto-detect) | `local` (qwen3-embed ONNX) or `litellm` (cloud API). Auto: API_KEYS/proxy -> litellm, else local. |
| `EMBEDDING_MODEL` | `gemini/gemini-embedding-001` | LiteLLM embedding model (only used when backend=litellm). |
| `API_KEYS` | - | LLM API keys for SDK mode (format: `ENV_VAR:key,...`). Enables LiteLLM backend. |
| `LITELLM_PROXY_URL` | - | LiteLLM Proxy URL. Enables LiteLLM backend via proxy. |
| `LITELLM_PROXY_KEY` | - | LiteLLM Proxy virtual key. |

### Ignore files

Create `.code-review-graphignore` in your project root to exclude paths:

```
generated/**
*.generated.ts
vendor/**
node_modules/**
```

---

## Supported Languages

Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++

Each language has full Tree-sitter grammar support for functions, classes, imports, call sites, inheritance, and test detection.

---

## Cross-Agent Compatibility

| Feature | Claude Code | Copilot CLI | Codex | Gemini CLI | Antigravity | OpenCode | Cursor | Windsurf | Cline | Amp |
|:--------|:-----------:|:-----------:|:-----:|:----------:|:-----------:|:--------:|:------:|:--------:|:-----:|:---:|
| MCP tools (9 tools) | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| CLAUDE.md / AGENTS.md | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | -- | -- |
| Skills (slash commands) | Yes | Yes | Yes | Yes | -- | Yes | -- | -- | -- | -- |
| Hooks (PostToolUse) | Yes | -- | Yes | Yes | -- | -- | -- | -- | -- | -- |
| Plugin (marketplace) | Yes | Yes | -- | -- | -- | -- | -- | -- | -- | -- |

---

## Upstream PRs

All fixes in this fork are submitted as standalone PRs to the original [code-review-graph](https://github.com/tirth8205/code-review-graph):

- Multi-word search AND logic
- Parser call target resolution (ref: issue #20)
- Impact radius output pagination

**If all upstream PRs are merged, this repository will be archived.**

---

## Build from Source

```bash
git clone https://github.com/n24q02m/better-code-review-graph
cd better-code-review-graph
uv sync --group dev
uv run pytest
uv run better-code-review-graph serve
```

**Requirements:** Python 3.13 (not 3.14+), [uv](https://docs.astral.sh/uv/)

---

## Compatible With

[![Claude Desktop](https://img.shields.io/badge/Claude_Desktop-F9DC7C?logo=anthropic&logoColor=black)](#quick-start)
[![Claude Code](https://img.shields.io/badge/Claude_Code-000000?logo=anthropic&logoColor=white)](#quick-start)
[![Cursor](https://img.shields.io/badge/Cursor-000000?logo=cursor&logoColor=white)](#quick-start)
[![VS Code Copilot](https://img.shields.io/badge/VS_Code_Copilot-007ACC?logo=visualstudiocode&logoColor=white)](#quick-start)
[![Antigravity](https://img.shields.io/badge/Antigravity-4285F4?logo=google&logoColor=white)](#quick-start)
[![Gemini CLI](https://img.shields.io/badge/Gemini_CLI-8E75B2?logo=googlegemini&logoColor=white)](#quick-start)
[![OpenAI Codex](https://img.shields.io/badge/Codex-412991?logo=openai&logoColor=white)](#quick-start)
[![OpenCode](https://img.shields.io/badge/OpenCode-F7DF1E?logoColor=black)](#quick-start)

## Also by n24q02m

| Server | Description | Install |
|--------|-------------|---------|
| [wet-mcp](https://github.com/n24q02m/wet-mcp) | Web search, content extraction, library docs | `uvx --python 3.13 wet-mcp@latest` |
| [mnemo-mcp](https://github.com/n24q02m/mnemo-mcp) | Persistent AI memory with hybrid search | `uvx mnemo-mcp@latest` |
| [better-notion-mcp](https://github.com/n24q02m/better-notion-mcp) | Notion API for AI agents | `npx -y @n24q02m/better-notion-mcp@latest` |
| [better-email-mcp](https://github.com/n24q02m/better-email-mcp) | Email (IMAP/SMTP) for AI agents | `npx -y @n24q02m/better-email-mcp@latest` |
| [better-godot-mcp](https://github.com/n24q02m/better-godot-mcp) | Godot Engine for AI agents | `npx -y @n24q02m/better-godot-mcp@latest` |
| [better-telegram-mcp](https://github.com/n24q02m/better-telegram-mcp) | Telegram Bot API + MTProto for AI agents | `uvx --python 3.13 better-telegram-mcp@latest` |

## License

MIT - See [LICENSE](LICENSE)
