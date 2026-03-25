# Better Code Review Graph

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
| Embedding | sentence-transformers + torch (1.1 GB) | qwen3-embed ONNX + Cohere cloud (200 MB), dual-mode |
| Output size | Unbounded (500K+ chars) | Paginated (max_results, truncated flag) |
| Tool design | 9 individual tools | 5 tools: graph + query + review + config + help |
| Plugin hooks | Invalid PostEdit/PostGit | Valid PostToolUse |

## Quick Start

### Claude Code Plugin (Recommended)

Via marketplace (includes skills: /refactor-check, /review-delta, /review-pr + hooks):

```bash
/plugin marketplace add n24q02m/claude-plugins
/plugin install better-code-review-graph@claude-plugins
```

Or install this plugin only:

```bash
/plugin marketplace add n24q02m/better-code-review-graph
/plugin install better-code-review-graph
```

Includes hooks (SessionStart auto-build, PostToolUse auto-update). Configure env vars in `~/.claude/settings.local.json` or shell profile.

### MCP Server

#### Option 1: uvx

```jsonc
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph"]
    }
  }
}
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

```jsonc
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", ".:/repo:ro", "n24q02m/better-code-review-graph:latest"]
    }
  }
}
```

### Claude Code Plugin Details

When installed as a plugin, you get:

**Hooks:**

- **SessionStart**: Auto-builds the code graph when a conversation starts
- **PostToolUse**: Auto-updates the graph after file modifications (Write, Edit, Bash)

**Skills:**

- **refactor-check**: Safety analysis before refactoring -- dependency graph, blast radius
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
| `embed` | Compute vector embeddings for semantic search. Dual-mode: local ONNX or Cohere cloud. |

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
| `EMBEDDING_BACKEND` | (auto-detect) | `local` or `cloud`. Auto-detects from available API keys. |
| `EMBEDDING_MODEL` | (provider default) | Override cloud model name. Provider auto-detected from model prefix. |
| `JINA_AI_API_KEY` | - | Jina AI API key (embedding, highest priority). |
| `GEMINI_API_KEY` | - | Google Gemini API key (embedding). Also accepts `GOOGLE_API_KEY`. |
| `OPENAI_API_KEY` | - | OpenAI API key (embedding). |
| `COHERE_API_KEY` | - | Cohere API key (embedding). Also accepts `CO_API_KEY`. |

### Embedding Backends

| Backend | Config | Size | Description |
|:--------|:-------|:-----|:------------|
| **local** (default) | Nothing needed | ~570 MB (first use) | qwen3-embed ONNX. Zero-config. |
| **cloud** | Any supported API key | 0 MB | Multi-provider: Jina AI, Gemini, OpenAI, Cohere (priority order). |

- **Auto-detection**: Any supported API key set -> cloud (priority: Jina > Gemini > OpenAI > Cohere). Otherwise -> local ONNX.
- **Override**: `EMBEDDING_BACKEND=local` or `EMBEDDING_BACKEND=cloud`.
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

### Security

- **Graceful fallbacks** -- Cloud embedding failure falls back to local ONNX
- **Error handling** -- Tools return error strings with fix suggestions, never crash
- **Read-only mount** -- Docker mode mounts repo as `:ro` (read-only)

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

[![Claude Code](https://img.shields.io/badge/Claude_Code-000000?logo=anthropic&logoColor=white)](#quick-start)
[![Claude Desktop](https://img.shields.io/badge/Claude_Desktop-F9DC7C?logo=anthropic&logoColor=black)](#quick-start)
[![Cursor](https://img.shields.io/badge/Cursor-000000?logo=cursor&logoColor=white)](#quick-start)
[![VS Code Copilot](https://img.shields.io/badge/VS_Code_Copilot-007ACC?logo=visualstudiocode&logoColor=white)](#quick-start)
[![Antigravity](https://img.shields.io/badge/Antigravity-4285F4?logo=google&logoColor=white)](#quick-start)
[![Gemini CLI](https://img.shields.io/badge/Gemini_CLI-8E75B2?logo=googlegemini&logoColor=white)](#quick-start)
[![OpenAI Codex](https://img.shields.io/badge/Codex-412991?logo=openai&logoColor=white)](#quick-start)
[![OpenCode](https://img.shields.io/badge/OpenCode-F7DF1E?logoColor=black)](#quick-start)

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

## License

MIT -- See [LICENSE](LICENSE).
