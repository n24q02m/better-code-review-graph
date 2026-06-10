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

<!-- BEGIN: AUTO-GENERATED-CROSS-PROMO -->
<details>
  <summary><strong>Sister projects from n24q02m</strong> (click to expand)</summary>

| Project | Tagline | Tag |
|---|---|---|
| [better-code-review-graph](https://github.com/n24q02m/better-code-review-graph) | Knowledge graph for token-efficient code reviews -- fixed search, configurabl... | MCP |
| [better-email-mcp](https://github.com/n24q02m/better-email-mcp) | IMAP/SMTP email server for AI agents -- 6 composite tools with multi-account ... | MCP |
| [better-godot-mcp](https://github.com/n24q02m/better-godot-mcp) | Composite MCP server for Godot Engine -- 17 mega-tools for AI-assisted game d... | MCP |
| [better-notion-mcp](https://github.com/n24q02m/better-notion-mcp) | Markdown-first Notion API server for AI agents -- 10 composite tools replacin... | MCP |
| [better-telegram-mcp](https://github.com/n24q02m/better-telegram-mcp) | MCP server for Telegram with dual-mode support: Bot API (httpx) for quick bot... | MCP |
| [claude-plugins](https://github.com/n24q02m/claude-plugins) | Full documentation: mcp.n24q02m.com — unified docs for all 8 servers + the mc... | Marketplace |
| [imagine-mcp](https://github.com/n24q02m/imagine-mcp) | Production-grade MCP server for image and video understanding + generation ac... | MCP |
| [jules-task-archiver](https://github.com/n24q02m/jules-task-archiver) | Chrome Extension for bulk operations on Jules tasks via batchexecute API -- a... | Tooling |
| [mcp-core](https://github.com/n24q02m/mcp-core) | Unified MCP Streamable HTTP 2025-11-25 transport, OAuth 2.1 Authorization Ser... | MCP |
| [mnemo-mcp](https://github.com/n24q02m/mnemo-mcp) | Persistent AI memory with hybrid search and embedded sync. Open, free, unlimi... | MCP |
| [qwen3-embed](https://github.com/n24q02m/qwen3-embed) | Lightweight Qwen3 text embedding and reranking via ONNX Runtime and GGUF | Library |
| [skret](https://github.com/n24q02m/skret) | Secrets without the server. | CLI |
| [web-core](https://github.com/n24q02m/web-core) | Shared web infrastructure package for search, scraping, HTTP security, and st... | Library |
| [wet-mcp](https://github.com/n24q02m/wet-mcp) | Open-source MCP Server for web search, content extraction, library docs & mul... | MCP |

</details>
<!-- END: AUTO-GENERATED-CROSS-PROMO -->

## Table of contents

- [Features](#features)
- [Status](#status)
- [Documentation](#documentation)
- [Tools](#tools)
- [Comparison](#comparison)
- [Security](#security)
- [Build from Source](#build-from-source)
- [Trust Model](#trust-model)
- [License](#license)



<!-- Glama badge -->
<a href="https://glama.ai/mcp/servers/n24q02m/better-code-review-graph">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/n24q02m/better-code-review-graph/badge" alt="better-code-review-graph MCP server" />
</a>

Fork of [code-review-graph](https://github.com/tirth8205/code-review-graph) with critical bug fixes, configurable embeddings, and production CI/CD. Parses your codebase with [Tree-sitter](https://tree-sitter.github.io/tree-sitter/), builds a structural graph of functions/classes/imports, and gives Claude (or any MCP client) precise context so it reads only what matters.

## v2.0 migration (BREAKING)

See [BREAKING_CHANGES.md](BREAKING_CHANGES.md) for the full
schema-change list, behavior-change summary, environment
requirements, and rollback procedure.

This release adds **temporal columns** (`valid_from_sha` /
`valid_to_sha` on every node + edge) and an opt-in **security
scanner**. The schema migration is auto-applied on first
`GraphStore` open, and a backup of the pre-2.0 DB is saved to
`<graph_db>.pre-2.0.bak` so you can roll back if needed.

To downgrade and restore the pre-2.0 backup:

```sh
CRG_DOWNGRADE_TO_1_X=1 uv run better-code-review-graph
```

The backup is created the first time alembic crosses the breaking
boundary (revision `005_temporal_columns`); subsequent runs reuse
the existing backup file. After a downgrade the v2-state DB is
preserved at `<graph_db>.post-2.0.archived` so you can forward-roll
again later.

What you get on v2.0+:

- **Temporal queries** -- `query`/`search`/`impact` accept
  `as_of=<sha>` for snapshot semantics; `query(action="diff",
  from_sha=X, to_sha=Y)` returns `{added, removed, modified}`
  buckets driven entirely by the temporal columns (no re-parse).
  See `help(topic="query")`.
- **Refactor auditing** -- `review(action="delta",
  show_line_shifts=true, ...)` surfaces symbols whose `line_start`
  moved between two commits.
- **Security scanning** -- `security(action="scan", ...)` runs a
  regex-based Tier-1 scanner (5 rules) by default; pass
  `engine="semgrep"` (after `uv add 'better-code-review-graph[security]'`)
  for the Tier-2 engine, which runs Semgrep's `p/auto` registry pack
  plus a 3-rule curated overlay. Findings persist on
  `nodes.security_tags`; `report` re-emits the cache as JSON or
  SARIF v2.1.0. See `help(topic="security")`.

## What's new in v1.6

- **LLM-generated summaries** -- `graph(action="summarize")` writes a one-paragraph docstring for each `Function` node via Gemini or OpenAI (cloud opt-in, no key = no-op). Run it after `graph(action="update")` to lift semantic-search recall by ~15% on repos with terse function names.
- **Graph export in 4 formats** -- `graph(action="export", format=...)` emits `graphml` (Gephi/Cytoscape), `json-ld`, `dot` (Graphviz), or `cypher` (Neo4j replay). Inline by default; pass `output_path` to write to disk.
- **Source text capture** -- `Function` nodes now persist their raw source so summaries can be regenerated whenever an edit changes the body. The cache key is `sha256(source_text):provider`; unchanged nodes cost zero LLM calls on re-run.
- **Cost cap on summaries** -- `max_nodes` (default 500) caps LLM calls per invocation; pair with cron / `update` cadence for predictable spend.
- **Phase 1 quality wins** (also new in this train): `query(action="spot_check")` for random callsite snippets, `query(action="renamed_in_diff")` for shifted callsites, dynamic-dispatch hints in `callers_of` results, a dedicated `recipes` help topic, and `embeddings_count` exposed in `graph(action="stats")`.

Example -- after pulling new functions in, refresh embeddings with summaries:
```
graph(action="update")
graph(action="summarize", max_nodes=200)
graph(action="embed")
```

## Features

| Feature | code-review-graph | better-code-review-graph |
|:--------|:------------------|:-------------------------|
| Multi-word search | Broken (literal substring) | AND-logic word splitting |
| callers_of/callees_of | Empty results (bare name targets) | Qualified name resolution + bare fallback |
| Embedding | sentence-transformers + torch (1.1 GB) | qwen3-embed ONNX + cloud (200 MB), dual-mode |
| Output size | Unbounded (500K+ chars) | Paginated (max_results, truncated flag) |
| Tool design | 9 individual tools | 7 tools: graph + query + review + config + security + help + config__open_relay |
| Plugin hooks | Invalid PostEdit/PostGit | Valid PostToolUse |

## Status

> **2026-05-02 -- Architecture stabilization update**
>
> Past months saw significant churn around credential handling and the daemon-bridge auto-spawn pattern. This caused multi-process races, browser tab spam, and inconsistent setup UX across plugins. **As of v<auto>, the architecture is stable**: 2 clean modes (stdio + HTTP), no daemon-bridge layer, no auto-spawn from stdio.
>
> Apologies for the instability period. If you encountered issues with prior versions, please update to v<auto>+ and follow the current [Setup guide](https://mcp.n24q02m.com/servers/better-code-review-graph/setup/) -- most prior workarounds are no longer needed.
>
> **Related plugins from the same author**:
> - [wet-mcp](https://github.com/n24q02m/wet-mcp) -- Web search + content extraction
> - [mnemo-mcp](https://github.com/n24q02m/mnemo-mcp) -- Persistent AI memory
> - [imagine-mcp](https://github.com/n24q02m/imagine-mcp) -- Image/video understanding + generation
> - [better-notion-mcp](https://github.com/n24q02m/better-notion-mcp) -- Notion API
> - [better-email-mcp](https://github.com/n24q02m/better-email-mcp) -- Email management
> - [better-telegram-mcp](https://github.com/n24q02m/better-telegram-mcp) -- Telegram
> - [better-godot-mcp](https://github.com/n24q02m/better-godot-mcp) -- Godot Engine
>
> All plugins share the same architecture -- install once, learn pattern transfers.

## Documentation

Full docs at **[mcp.n24q02m.com/servers/better-code-review-graph/setup/](https://mcp.n24q02m.com/servers/better-code-review-graph/setup/)**:

- [Setup](https://mcp.n24q02m.com/servers/better-code-review-graph/setup/) -- install methods for Claude Code, Codex, Gemini CLI, Cursor, Windsurf, mcp.json
- [Modes overview](https://mcp.n24q02m.com/get-started/modes-overview/) -- stdio / local-relay / remote-relay / remote-oauth
- [Multi-user setup](https://mcp.n24q02m.com/get-started/multi-user/) -- per-JWT-sub credential model

**Install with AI agent** -- paste this to your AI coding agent:

> Install MCP server `better-code-review-graph` following the steps at
> https://raw.githubusercontent.com/n24q02m/claude-plugins/main/plugins/better-code-review-graph/setup-with-agent.md

## Tools

### `graph` -- Graph lifecycle

Actions: `build` | `update` | `stats` | `embed` | `export` | `summarize`

| Action | Description |
|:-------|:------------|
| `build` | Full or incremental graph build. Set `full_rebuild=true` to re-parse all files. |
| `update` | Alias for `build` with `full_rebuild=false` (incremental). |
| `stats` | Graph size, languages, node/edge breakdown, embedding count. |
| `embed` | Compute vector embeddings for semantic search. Dual-mode: local ONNX or cloud. |
| `export` | Export graph in `graphml` / `json-ld` / `dot` / `cypher`. Inline or to `output_path`. |
| `summarize` | LLM-generated one-paragraph docstrings for `Function` nodes (Gemini or OpenAI, cloud opt-in). Cost-capped via `max_nodes`. |

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

### `config` -- Server configuration and credential setup

Actions: `status` | `set` | `cache_clear` | `setup_status` | `setup_start` | `setup_skip` | `setup_reset` | `setup_complete`

| Action | Description |
|:-------|:------------|
| `status` | Server info: version, graph path, node/edge counts, embedding backend. |
| `set` | Update runtime settings (e.g., `log_level`). |
| `cache_clear` | Remove all computed embeddings. |
| `setup_status` | Show current credential state and setup URL. |
| `setup_start` | Start relay setup to configure API keys via browser. |
| `setup_skip` | Set local mode (skip relay permanently, use ONNX only). |
| `setup_reset` | Clear credentials and reset state. |
| `setup_complete` | Re-resolve credentials from environment variables. |

### `security` -- Security scanning

Actions: `scan` | `report` | `suppress` | `rule_list`

| Action | Description |
|:-------|:------------|
| `scan` | Run a security scan (`engine='heuristic'` default, or `'semgrep'`). Findings persist on `nodes.security_tags`. |
| `report` | Re-emit cached findings as JSON (`format='json'`) or SARIF v2.1.0 (`format='sarif'`). |
| `suppress` | Suppress a finding by `rule_id` (or `remove=true` to un-suppress). |
| `rule_list` | List available rules for an engine. |

### `help` -- Full documentation

Topics: `graph` | `query` | `review` | `config` | `security` | `recipes`

Returns complete documentation for each tool. Use when the compressed descriptions above are insufficient.

### `config__open_relay` -- Re-trigger the relay setup form

Registered automatically from `mcp-core`. In HTTP mode it returns `<PUBLIC_URL>/authorize` so the agent can re-open the browser setup form (e.g. after credential expiry); in stdio mode it returns `status: 'stdio_unsupported'`.

## Comparison

How better-code-review-graph stacks up against direct competitors in each pillar:

| Capability | better-code-review-graph | Greptile | Sourcegraph (Cody / MCP) | CodeGraph (colbymchenry) |
|---|---|---|---|---|
| Codebase knowledge graph | Yes (Tree-sitter, 14 langs, SQLite) | Yes (functions/classes/deps) | Yes (precise code indexing) | Yes (Tree-sitter, 20+ langs, SQLite) |
| Persistent incremental updates | Yes (git-diff + file-hash re-parse) | ? | Yes (continuous indexing) | Yes (OS file-watcher debounced) |
| Qualified call resolution (callers/callees) | Yes (same-file bare-call resolution + fallback) | ? | Yes (go-to-def / find-references) | Yes (callers / callees / impact) |
| Semantic search / embeddings | Yes (qwen3 ONNX local + cloud Jina/Gemini/OpenAI/Cohere) | ? | Yes (semantic + keyword + regex) | No (FTS5 full-text only) |
| Token-optimized review context | Yes (`review` tool, git-diff scoped) | Yes (PR review comments) | No (code-context assistant) | No (context layer, not review) |
| Security scanning | Yes (Semgrep `p/auto` + 3-rule overlay, SARIF) | ? | ? | No |
| Self-hostable | Yes (stdio default, machine-bound) | Yes (Docker / K8s / air-gapped) | Yes (self-hosted instance) | Yes (100% local, no API keys) |
| Free / open source | Yes (MIT) | No (proprietary SaaS; free OSS tier) | No (Enterprise license, source private) | Yes (MIT) |

Sources: [Greptile](https://www.greptile.com/docs/introduction) · [Greptile pricing](https://www.greptile.com/pricing) · [Sourcegraph MCP](https://sourcegraph.com/mcp) · [CodeGraph](https://github.com/colbymchenry/codegraph). Cells marked `?` are capabilities the competitor does not publicly document, not confirmed absences.

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

## Trust Model

This plugin implements **TC-Local** (machine-bound, single trust principal). See the [mcp-core trust model](https://mcp.n24q02m.com/servers/mcp-core/trust-model/) for full classification.

| Mode | Storage | Encryption | Who can read your data? |
|---|---|---|---|
| stdio (default) | `~/.better-code-review-graph-mcp/config.json` | AES-GCM, machine-bound key | Only your OS user (file perm 0600) |
| HTTP self-host | Same as stdio | Same | Only you (admin = user) |

## License

MIT -- See [LICENSE](LICENSE).
