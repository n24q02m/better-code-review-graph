[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/n24q02m-better-code-review-graph-badge.png)](https://mseep.ai/app/n24q02m-better-code-review-graph)

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
| Embedding | sentence-transformers + torch (1.1 GB) | qwen3-embed ONNX + cloud (200 MB), dual-mode |
| Output size | Unbounded (500K+ chars) | Paginated (max_results, truncated flag) |
| Tool design | 9 individual tools | 6 tools: graph + query + review + config + setup + help |
| Plugin hooks | Invalid PostEdit/PostGit | Valid PostToolUse |

## Setup

**With AI Agent** -- copy and send this to your AI agent:

> Please set up better-code-review-graph for me. Follow this guide:
> https://raw.githubusercontent.com/n24q02m/better-code-review-graph/main/docs/setup-with-agent.md

**Manual Setup** -- follow [docs/setup-manual.md](docs/setup-manual.md)

## Tools

### `graph` -- Graph lifecycle

Actions: `build` | `update` | `stats` | `embed`

| Action | Description |
|:-------|:------------|
| `build` | Full or incremental graph build. Set `full_rebuild=true` to re-parse all files. |
| `update` | Alias for `build` with `full_rebuild=false` (incremental). |
| `stats` | Graph size, languages, node/edge breakdown, embedding count. |
| `embed` | Compute vector embeddings for semantic search. Dual-mode: local ONNX or cloud. |

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

### `setup` -- Credential setup

Actions: `status` | `start` | `skip` | `reset` | `complete`

| Action | Description |
|:-------|:------------|
| `status` | Show current credential state and setup URL. |
| `start` | Start relay setup to configure API keys via browser. |
| `skip` | Set local mode (skip relay permanently, use ONNX only). |
| `reset` | Clear credentials and reset state. |
| `complete` | Re-resolve credentials from environment variables. |

### `help` -- Full documentation

Topics: `graph` | `query` | `review` | `config`

Returns complete documentation for each tool. Use when the compressed descriptions above are insufficient.

## Security

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

## License

MIT -- See [LICENSE](LICENSE).
