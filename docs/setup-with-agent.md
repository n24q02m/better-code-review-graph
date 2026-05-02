# Better Code Review Graph -- Agent Setup Guide

> Give this file to your AI agent to automatically set up better-code-review-graph.

> **2026-05-02 Update (v<auto>+)**: Plugin install (Option 1) now uses pure stdio mode. API keys are optional env vars.
> The previous "Zero-Config Relay" auto-spawn pattern has been removed.
> If you relied on the relay form to enter API keys, please:
> 1. Set the env var directly in plugin config (Option 1), OR
> 2. Switch to HTTP mode (Option 4) for browser-based setup.

## Option 1: Claude Code Plugin (Recommended)

Plugin marketplace install runs the server in **pure stdio mode** with optional API key env vars. No daemon-bridge, no auto-spawn, no relay form. Graph storage is local SQLite -- no external graph database required.

```bash
# Install from marketplace (includes skills: /refactor-check, /review-delta, /review-pr + hooks)
/plugin marketplace add n24q02m/claude-plugins
/plugin install better-code-review-graph@n24q02m-plugins
```

The plugin includes SessionStart and PostToolUse hooks that auto-build and auto-update the code graph.

**Optional**: set any of `GEMINI_API_KEY`, `OPENAI_API_KEY`, `JINA_AI_API_KEY`, `COHERE_API_KEY` in the plugin config to enable cloud embedding/reranking. Without keys, the server runs in pure local ONNX mode (Qwen3 embedding, ~570MB downloaded on first use).

## Option 2: MCP Direct (Stdio + uvx)

**Python 3.13 required** -- Python 3.14+ is NOT supported.

### Claude Code (settings.json)

Add to `~/.claude/settings.local.json` under `"mcpServers"`:

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph"]
    }
  }
}
```

To enable cloud embedding, add an `env` block with any subset of API keys:

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph"],
      "env": {
        "JINA_AI_API_KEY": "jina_..."
      }
    }
  }
}
```

### Codex CLI (config.toml)

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.better-code-review-graph]
command = "uvx"
args = ["--python", "3.13", "better-code-review-graph"]
```

### OpenCode (opencode.json)

Add to `opencode.json` in the project root:

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "uvx",
      "args": ["--python", "3.13", "better-code-review-graph"]
    }
  }
}
```

## Option 3: Docker (Stdio)

```bash
docker run -i --rm \
  -v ".:/repo:ro" \
  n24q02m/better-code-review-graph:latest
```

Or as an MCP server config:

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", ".:/repo:ro", "n24q02m/better-code-review-graph:latest"]
    }
  }
}
```

Note: The `-v ".:/repo:ro"` mount gives the server read-only access to the current directory for graph building.

## Why upgrade to HTTP mode?

Stdio is the default and works fine for single-user local setups. You may want to switch to HTTP mode (Option 4) when you need any of the following:

- **claude.ai web compatibility** -- claude.ai (the web UI) supports HTTP MCP servers but cannot spawn local stdio processes.
- **One server shared across N Claude Code sessions** -- a single HTTP instance serves multiple terminals/IDEs without re-spawning per session.
- **Browser-based API key setup** -- paste cloud-embedding keys into a guided form instead of editing JSON config files. No upstream OAuth (better-code-review-graph has no upstream identity provider; keys belong to Jina/Gemini/OpenAI/Cohere).
- **Multi-device credential sync** -- configure once on your laptop, the same encrypted credential set works from your desktop / tablet without copying API keys.
- **Multi-user team sharing** -- a self-hosted HTTP server can serve multiple developers, each with isolated per-user credentials (per-JWT-sub).
- **Always-on persistent process for webhooks/agents** -- HTTP servers stay alive between sessions, enabling background work, scheduled agents, or long-running graph builds.

## Option 4: HTTP Self-Host (Multi-User)

Host your own HTTP server with paste-token relay form per user. See [setup-manual.md](setup-manual.md) "Method 5: Self-Hosting HTTP Mode" for full instructions.

Quick start:

```bash
docker run -p 8080:8080 \
  -e TRANSPORT_MODE=http \
  -e PUBLIC_URL=https://your-domain.com \
  -e DCR_SERVER_SECRET=$(openssl rand -hex 32) \
  n24q02m/better-code-review-graph:latest
```

Client config:

```json
{
  "mcpServers": {
    "better-code-review-graph": {
      "type": "http",
      "url": "https://your-domain.com/mcp"
    }
  }
}
```

Each user opens `https://your-domain.com/authorize` once, pastes API keys (or leaves empty for local ONNX), and submits. Credentials are encrypted per-JWT-sub.

## Environment Variables

All environment variables are **optional**. The server works with local ONNX embeddings with zero configuration.

### API Keys (Cloud Embedding Providers)

| Variable | Required | Default | Description |
|:---------|:---------|:--------|:------------|
| `JINA_AI_API_KEY` | No | -- | Jina AI key: embedding + reranking (highest priority) |
| `GEMINI_API_KEY` | No | -- | Google Gemini key: embedding (free tier available). Also accepts `GOOGLE_API_KEY` |
| `OPENAI_API_KEY` | No | -- | OpenAI key: embedding |
| `COHERE_API_KEY` | No | -- | Cohere key: embedding + reranking. Also accepts `CO_API_KEY` |

### Embedding Configuration

| Variable | Required | Default | Description |
|:---------|:---------|:--------|:------------|
| `EMBEDDING_BACKEND` | No | auto-detect | `cloud` or `local`. Auto: API keys present -> cloud, else local |
| `EMBEDDING_MODEL` | No | auto-detect | Cloud embedding model name. Provider auto-detected from model prefix |

### HTTP Mode (Self-Host)

| Variable | Required | Default | Description |
|:---------|:---------|:--------|:------------|
| `TRANSPORT_MODE` | No | `stdio` | Set to `http` to enable HTTP transport (multi-user). |
| `PUBLIC_URL` | Yes (http) | -- | Server's public URL for relay form. |
| `DCR_SERVER_SECRET` | Yes (http) | -- | HMAC secret for stateless Dynamic Client Registration. |
| `PORT` | No | `8080` | Server port (http mode only). |

### General

| Variable | Required | Default | Description |
|:---------|:---------|:--------|:------------|
| `LOG_LEVEL` | No | `INFO` | Logging level |

## Authentication

### Stdio Mode (Env Vars)

Set API keys directly via env vars (or leave unset for local ONNX). No relay form, no browser flow.

### HTTP Mode (Relay Form)

Each user opens `https://<your-host>/authorize` in their browser, pastes any subset of API keys, and submits. All fields are optional -- empty submission keeps the user on local ONNX. Credentials are encrypted per-JWT-sub and never shared between users.

## Verification

After setup, verify the server is working by building the graph:

```
graph(action="build", repo_path="/path/to/your/repo")
```

Expected: returns a JSON summary with node counts, edge counts, and supported languages found.

Then try a search:

```
query(action="search", query="main function", repo_path="/path/to/your/repo")
```
