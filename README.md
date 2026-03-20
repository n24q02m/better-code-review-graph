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
| Multi-word search | Broken (literal substring) | AND-logic word splitting |
| callers_of/callees_of | Empty results (bare name targets) | Qualified name resolution + bare fallback |
| Embedding | sentence-transformers + torch (1.1 GB) | qwen3-embed ONNX + LiteLLM (200 MB), dual-mode |
| Output size | Unbounded (500K+ chars) | Paginated (max_results, truncated flag) |
| Tool design | 9 individual tools | 3-tier: graph (mega) + config + help |
| Plugin hooks | Invalid PostEdit/PostGit | Valid PostToolUse |

All fixes are submitted upstream as standalone PRs (see [Upstream PRs](#upstream-prs)). If all are merged, this repo will be archived.

---

## Installation

### Claude Code

```bash
claude mcp add better-code-review-graph -- uvx --python 3.13 better-code-review-graph serve
```

### Claude Code Plugin

```bash
claude plugin install n24q02m/better-code-review-graph@better-code-review-graph
```

### Cursor (~/.cursor/mcp.json)

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph", "serve"]
    }
  }
}
```

### Codex (~/.codex/config.toml)

```toml
[mcp_servers.better-code-review-graph]
command = "uvx"
args = ["--python", "3.13", "better-code-review-graph", "serve"]
```

### Gemini CLI (~/.gemini/settings.json)

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph", "serve"]
    }
  }
}
```

### OpenCode (~/.opencode.json)

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph", "serve"]
    }
  }
}
```

### Windsurf (~/.codeium/windsurf/mcp_config.json)

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph", "serve"]
    }
  }
}
```

### Cline (cline_mcp_settings.json)

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph", "serve"]
    }
  }
}
```

### Amp (~/.config/amp/settings.json)

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph", "serve"]
    }
  }
}
```

### Docker

```bash
docker run -i --rm n24q02m/better-code-review-graph
```

### pip

```bash
pip install better-code-review-graph
better-code-review-graph serve
```

---

## Tools

### `graph` -- Knowledge graph operations

Actions: `build` | `update` | `query` | `search` | `impact` | `review` | `embed` | `stats` | `large_functions`

| Action | Description |
|:-------|:------------|
| `build` | Full or incremental graph build. Set `full_rebuild=true` to re-parse all files. |
| `update` | Alias for `build` with `full_rebuild=false` (incremental). |
| `query` | Run predefined queries: `callers_of`, `callees_of`, `imports_of`, `importers_of`, `children_of`, `tests_for`, `inheritors_of`, `file_summary`. |
| `search` | Search code entities by name/keyword or semantic similarity. |
| `impact` | Blast radius of changed files. Auto-detects from git diff. Paginated with `max_results`. |
| `review` | Token-optimized review context with structural summary, source snippets, and review guidance. |
| `embed` | Compute vector embeddings for semantic search. Dual-mode: local ONNX or cloud LiteLLM. |
| `stats` | Graph size, languages, node/edge breakdown, embedding count. |
| `large_functions` | Find functions/classes exceeding a line-count threshold. |

### `config` -- Server configuration

Actions: `status` | `set` | `cache_clear`

| Action | Description |
|:-------|:------------|
| `status` | Server info: version, graph path, node/edge counts, embedding backend. |
| `set` | Update runtime settings (e.g., `log_level`). |
| `cache_clear` | Remove all computed embeddings. |

### `help` -- Full documentation

Topics: `graph` | `config`

Returns complete documentation for each tool. Use when the compressed descriptions above are insufficient.

---

## Embedding Backends

| Backend | Config | Size | Description |
|:--------|:-------|:-----|:------------|
| **local** (default) | Nothing needed | ~570 MB (first use) | qwen3-embed ONNX. Zero-config. |
| **litellm** | `API_KEYS` or `LITELLM_PROXY_URL` | 0 MB | Cloud providers via LiteLLM. |

- **Auto-detection**: `API_KEYS` or `LITELLM_PROXY_URL` set -> LiteLLM. Otherwise -> local ONNX.
- **Override**: `EMBEDDING_BACKEND=local` or `EMBEDDING_BACKEND=litellm`.
- **Fixed 768-dim storage**: Switching backends does NOT invalidate existing vectors.

---

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `EMBEDDING_BACKEND` | (auto-detect) | `local` or `litellm` |
| `EMBEDDING_MODEL` | `gemini/gemini-embedding-001` | LiteLLM model (when backend=litellm) |
| `API_KEYS` | - | LLM API keys (format: `ENV_VAR:key,...`). Enables LiteLLM. |
| `LITELLM_PROXY_URL` | - | LiteLLM Proxy URL. Enables LiteLLM via proxy. |
| `LITELLM_PROXY_KEY` | - | LiteLLM Proxy virtual key. |

### Ignore files

Create `.code-review-graphignore` in your project root:

```
generated/**
*.generated.ts
vendor/**
node_modules/**
```

---

## Supported Languages

Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++

---

## Upstream PRs

All fixes are submitted to [code-review-graph](https://github.com/tirth8205/code-review-graph):

- [#37](https://github.com/tirth8205/code-review-graph/pull/37) -- Multi-word search AND logic
- [#38](https://github.com/tirth8205/code-review-graph/pull/38) -- Parser call target resolution (fixes [#20](https://github.com/tirth8205/code-review-graph/issues/20))
- [#39](https://github.com/tirth8205/code-review-graph/pull/39) -- Impact radius output pagination

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

**Requirements:** Python 3.13, [uv](https://docs.astral.sh/uv/)

---

## Compatible With

[![Claude Desktop](https://img.shields.io/badge/Claude_Desktop-F9DC7C?logo=anthropic&logoColor=black)](#installation)
[![Claude Code](https://img.shields.io/badge/Claude_Code-000000?logo=anthropic&logoColor=white)](#installation)
[![Cursor](https://img.shields.io/badge/Cursor-000000?logo=cursor&logoColor=white)](#installation)
[![VS Code Copilot](https://img.shields.io/badge/VS_Code_Copilot-007ACC?logo=visualstudiocode&logoColor=white)](#installation)
[![Antigravity](https://img.shields.io/badge/Antigravity-4285F4?logo=google&logoColor=white)](#installation)
[![Gemini CLI](https://img.shields.io/badge/Gemini_CLI-8E75B2?logo=googlegemini&logoColor=white)](#installation)
[![OpenAI Codex](https://img.shields.io/badge/Codex-412991?logo=openai&logoColor=white)](#installation)
[![OpenCode](https://img.shields.io/badge/OpenCode-F7DF1E?logoColor=black)](#installation)

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
