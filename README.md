# better-code-review-graph

mcp-name: io.github.n24q02m/better-code-review-graph

**Knowledge graph for token-efficient code reviews -- fixed search, configurable embeddings, qualified call resolution.**

<!-- Badge Row 1: Status -->
[![CI](https://github.com/n24q02m/better-code-review-graph/actions/workflows/ci.yml/badge.svg)](https://github.com/n24q02m/better-code-review-graph/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/n24q02m/better-code-review-graph/graph/badge.svg)](https://codecov.io/gh/n24q02m/better-code-review-graph)
[![PyPI](https://img.shields.io/pypi/v/better-code-review-graph?logo=pypi&logoColor=white)](https://pypi.org/project/better-code-review-graph/)
[![Docker](https://img.shields.io/docker/v/n24q02m/better-code-review-graph?label=docker&logo=docker&logoColor=white&sort=semver)](https://hub.docker.com/r/n24q02m/better-code-review-graph)
[![License: MIT](https://img.shields.io/github/license/n24q02m/better-code-review-graph)](LICENSE)

<!-- Badge Row 2: Tech -->
[![Python](https://img.shields.io/badge/Python_3.13-3776AB?logo=python&logoColor=white)](#)
[![MCP](https://img.shields.io/badge/MCP-000000?logo=anthropic&logoColor=white)](#)
[![semantic-release](https://img.shields.io/badge/semantic--release-e10079?logo=semantic-release&logoColor=white)](https://github.com/python-semantic-release/python-semantic-release)
[![Renovate](https://img.shields.io/badge/renovate-enabled-1A1F6C?logo=renovatebot&logoColor=white)](https://developer.mend.io/)

<!-- Glama badge -->
<a href="https://glama.ai/mcp/servers/n24q02m/better-code-review-graph">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/n24q02m/better-code-review-graph/badge" alt="better-code-review-graph MCP server" />
</a>

Fork of [code-review-graph](https://github.com/tirth8205/code-review-graph) with critical bug fixes, configurable embeddings, and production CI/CD. Parses your codebase with [Tree-sitter](https://tree-sitter.github.io/tree-sitter/), builds a structural graph of functions/classes/imports, and gives Claude (or any MCP client) precise context so it reads only what matters.

## Features

| Feature | code-review-graph | better-code-review-graph |
|:--------|:------------------|:-------------------------|
| Multi-word search | Broken (literal substring) | AND-logic word splitting |
| callers_of/callees_of | Empty results (bare name targets) | Qualified name resolution + bare fallback |
| Embedding | sentence-transformers + torch (1.1 GB) | qwen3-embed ONNX + LiteLLM (200 MB), dual-mode |
| Output size | Unbounded (500K+ chars) | Paginated (max_results, truncated flag) |
| Tool design | 9 individual tools | 5 tools: graph + query + review + config + help |
| Plugin hooks | Invalid PostEdit/PostGit | Valid PostToolUse |

All fixes are submitted upstream as standalone PRs (see [Upstream PRs](#upstream-prs)). If all are merged, this repo will be archived.

## Quick Start

### Claude Code Plugin (Recommended)

```bash
claude plugin add n24q02m/better-code-review-graph
```

Includes MCP server, hooks (SessionStart auto-build, PostToolUse auto-update), and skills (build-graph, review-delta, review-pr).

### MCP Server

#### Option 1: uvx

```bash
claude mcp add better-code-review-graph -- uvx --python 3.13 better-code-review-graph
```

<details>
<summary>Other MCP clients (Cursor, Codex, Gemini CLI, Windsurf, Cline, Amp, OpenCode)</summary>

```jsonc
// Cursor (~/.cursor/mcp.json)
// Windsurf (~/.codeium/windsurf/mcp_config.json)
// Cline (cline_mcp_settings.json)
// Amp (~/.config/amp/settings.json)
// OpenCode (~/.opencode.json)
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph"]
    }
  }
}
```

```toml
# Codex (~/.codex/config.toml)
[mcp_servers.better-code-review-graph]
command = "uvx"
args = ["--python", "3.13", "better-code-review-graph"]
```

```jsonc
// Gemini CLI (~/.gemini/settings.json)
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph"]
    }
  }
}
```

</details>

#### Option 2: Docker

```bash
docker run -i --rm n24q02m/better-code-review-graph
```

#### Option 3: pip

```bash
pip install better-code-review-graph
better-code-review-graph
```

### Claude Code Plugin Details

When installed as a plugin, you get:

**Hooks:**

- **SessionStart**: Auto-builds the code graph when a conversation starts
- **PostToolUse**: Auto-updates the graph after file modifications (Write, Edit, Bash)

**Skills:**

- **build-graph**: Build or rebuild the knowledge graph for the current project
- **review-delta**: Review uncommitted changes using graph context
- **review-pr**: Review a pull request with structural analysis

## Tools

### `graph` -- Graph lifecycle

Actions: `build` | `update` | `stats` | `embed`

| Action | Description |
|:-------|:------------|
| `build` | Full or incremental graph build. Set `full_rebuild=true` to re-parse all files. |
| `update` | Alias for `build` with `full_rebuild=false` (incremental). |
| `stats` | Graph size, languages, node/edge breakdown, embedding count. |
| `embed` | Compute vector embeddings for semantic search. Dual-mode: local ONNX or cloud LiteLLM. |

### `query` -- Graph queries

Actions: `query` | `search` | `impact` | `large_functions`

| Action | Description |
|:-------|:------------|
| `query` | Predefined pattern queries: `callers_of`, `callees_of`, `imports_of`, `importers_of`, `children_of`, `tests_for`, `inheritors_of`, `file_summary`. |
| `search` | Search code entities by name/keyword or semantic similarity. |
| `impact` | Blast radius of changed files. Auto-detects from git diff. Paginated with `max_results`. |
| `large_functions` | Find functions/classes exceeding a line-count threshold. |

### `review` -- Code review context

Token-optimized review context with structural summary, source snippets, and review guidance. Auto-detects changed files from git diff.

### `config` -- Server configuration

Actions: `status` | `set` | `cache_clear`

| Action | Description |
|:-------|:------------|
| `status` | Server info: version, graph path, node/edge counts, embedding backend. |
| `set` | Update runtime settings (e.g., `log_level`). |
| `cache_clear` | Remove all computed embeddings. |

### `help` -- Full documentation

Topics: `graph` | `query` | `review` | `config`

Returns complete documentation for each tool. Use when the compressed descriptions above are insufficient.

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `EMBEDDING_BACKEND` | (auto-detect) | `local` or `litellm` |
| `EMBEDDING_MODEL` | `gemini/gemini-embedding-001` | LiteLLM model (when backend=litellm) |
| `API_KEYS` | - | LLM API keys (format: `ENV_VAR:key,...`). Enables LiteLLM. |
| `LITELLM_PROXY_URL` | - | LiteLLM Proxy URL. Enables LiteLLM via proxy. |
| `LITELLM_PROXY_KEY` | - | LiteLLM Proxy virtual key. |

### Embedding Backends

| Backend | Config | Size | Description |
|:--------|:-------|:-----|:------------|
| **local** (default) | Nothing needed | ~570 MB (first use) | qwen3-embed ONNX. Zero-config. |
| **litellm** | `API_KEYS` or `LITELLM_PROXY_URL` | 0 MB | Cloud providers via LiteLLM. |

- **Auto-detection**: `API_KEYS` or `LITELLM_PROXY_URL` set -> LiteLLM. Otherwise -> local ONNX.
- **Override**: `EMBEDDING_BACKEND=local` or `EMBEDDING_BACKEND=litellm`.
- **Fixed 768-dim storage**: Switching backends does NOT invalidate existing vectors.

### Supported Languages

Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++, Solidity

### Ignore Files

Create `.code-review-graphignore` in your project root:

```
generated/**
*.generated.ts
vendor/**
node_modules/**
```

## Build from Source

```bash
git clone https://github.com/n24q02m/better-code-review-graph
cd better-code-review-graph
uv sync --group dev
uv run pytest
uv run better-code-review-graph
```

**Requirements:** Python 3.13, [uv](https://docs.astral.sh/uv/)

## Compatible With

[![Claude Code](https://img.shields.io/badge/Claude_Code-black?logo=anthropic)](https://docs.anthropic.com/en/docs/claude-code)
[![Claude Desktop](https://img.shields.io/badge/Claude_Desktop-black?logo=anthropic)](https://claude.ai/download)
[![Cursor](https://img.shields.io/badge/Cursor-black?logo=cursor)](https://cursor.com/)
[![Windsurf](https://img.shields.io/badge/Windsurf-black?logo=codeium)](https://codeium.com/windsurf)
[![VS Code](https://img.shields.io/badge/VS_Code-black?logo=visual-studio-code)](https://code.visualstudio.com/)

## Also by n24q02m

| Server | Description |
|--------|-------------|
| [wet-mcp](https://github.com/n24q02m/wet-mcp) | Web search, content extraction, and documentation indexing |
| [mnemo-mcp](https://github.com/n24q02m/mnemo-mcp) | Persistent AI memory with hybrid search and cross-machine sync |
| [better-notion-mcp](https://github.com/n24q02m/better-notion-mcp) | Markdown-first Notion API with 9 composite tools |
| [better-email-mcp](https://github.com/n24q02m/better-email-mcp) | Email (IMAP/SMTP) with multi-account and auto-discovery |
| [better-godot-mcp](https://github.com/n24q02m/better-godot-mcp) | Godot Engine 4.x with 18 tools for scenes, scripts, and shaders |
| [better-telegram-mcp](https://github.com/n24q02m/better-telegram-mcp) | Telegram dual-mode (Bot API + MTProto) with 6 composite tools |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

### Upstream PRs

All fixes are submitted to [code-review-graph](https://github.com/tirth8205/code-review-graph):

- [#37](https://github.com/tirth8205/code-review-graph/pull/37) -- Multi-word search AND logic
- [#38](https://github.com/tirth8205/code-review-graph/pull/38) -- Parser call target resolution (fixes [#20](https://github.com/tirth8205/code-review-graph/issues/20))
- [#39](https://github.com/tirth8205/code-review-graph/pull/39) -- Impact radius output pagination

**If all upstream PRs are merged, this repository will be archived.**

## License

MIT -- See [LICENSE](LICENSE).
