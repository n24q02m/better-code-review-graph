# Better Code Review Graph -- Manual Setup Guide

> **2026-05-02 Update (v<auto>+)**: Plugin install (Method 1) now uses pure stdio mode. API keys are optional env vars.
> The previous "Zero-Config Relay" auto-spawn pattern has been removed.
> If you relied on the relay form to enter API keys, please:
> 1. Set the env var directly in plugin config (Method 1), OR
> 2. Switch to HTTP mode (Method 5) for browser-based setup.

## Method overview

This plugin supports **1 install method only**: stdio via plugin install (`uvx`/`npx`). Reason: the plugin needs direct host access to your project files (Godot project / repo path) and doesn't ship Docker or HTTP variants.

For comparison, the other 6 plugins in this stack (`better-notion-mcp`, `better-email-mcp`, `better-telegram-mcp`, `wet-mcp`, `mnemo-mcp`, `imagine-mcp`) support 3 methods:
1. **Default** -- Plugin install (`uvx`/`npx`) stdio
2. **Fallback** -- Docker stdio (Windows/macOS PATH issues)
3. **Recommended** -- Docker HTTP (multi-device, OAuth/relay form, claude.ai web)

## Prerequisites

- **Python 3.13** (3.14+ is NOT supported)
- `uv` or `uvx` installed ([docs](https://docs.astral.sh/uv/getting-started/installation/))
- Docker (optional, for containerized setup)
- A code repository to analyze

## Method 1: Claude Code Plugin (Recommended)

Plugin marketplace install runs the server in **pure stdio mode** with optional API key env vars. No daemon-bridge, no auto-spawn, no relay form. The graph is stored locally in SQLite -- no external graph database required.

1. Open Claude Code
2. Install the plugin:
   ```bash
   /plugin marketplace add n24q02m/claude-plugins
   /plugin install better-code-review-graph@n24q02m-plugins
   ```
3. The server starts automatically when Claude Code launches
4. The SessionStart hook auto-builds the graph for the current project; PostToolUse updates it after edits
5. **Optional**: set any of `GEMINI_API_KEY`, `OPENAI_API_KEY`, `JINA_AI_API_KEY`, `COHERE_API_KEY` in the plugin config to enable cloud embedding/reranking. Without keys, the server runs in pure local ONNX mode (Qwen3 embedding, ~570MB downloaded on first use).

## Method 2: uvx Direct (Stdio)

1. Add to your MCP client configuration file:

   **Claude Code** (`~/.claude/settings.local.json`):
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

   **Codex CLI** (`~/.codex/config.toml`):
   ```toml
   [mcp_servers.better-code-review-graph]
   command = "uvx"
   args = ["--python", "3.13", "better-code-review-graph"]
   ```

   **OpenCode** (`opencode.json` in project root):
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

2. (Optional) add API keys via the `env` block:
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
3. Restart your MCP client
4. Build the graph for your project:
   ```
   graph(action="build", repo_path="/path/to/your/repo")
   ```

## Method 3: Docker (Stdio)

1. Pull the image:
   ```bash
   docker pull n24q02m/better-code-review-graph:latest
   ```

2. Run with a repo mount:
   ```bash
   docker run -i --rm \
     -v "/path/to/your/repo:/repo:ro" \
     n24q02m/better-code-review-graph:latest
   ```

3. Or add to your MCP client config:
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

   Note: The `:ro` flag mounts the repo as read-only for safety.

## Method 4: Build from Source

1. Clone the repository:
   ```bash
   git clone https://github.com/n24q02m/better-code-review-graph.git
   cd better-code-review-graph
   ```

2. Install dependencies:
   ```bash
   uv sync --group dev
   ```

3. Run the server:
   ```bash
   uv run better-code-review-graph
   ```

## Why upgrade to HTTP mode?

Stdio is the default and works fine for single-user local setups. You may want to switch to HTTP mode (Method 5) when you need any of the following:

- **claude.ai web compatibility** -- claude.ai (the web UI) supports HTTP MCP servers but cannot spawn local stdio processes.
- **One server shared across N Claude Code sessions** -- a single HTTP instance serves multiple terminals/IDEs without re-spawning per session.
- **Browser-based API key setup** -- paste cloud-embedding keys into a guided form instead of editing JSON config files. No upstream OAuth (better-code-review-graph has no upstream identity provider; keys belong to Jina/Gemini/OpenAI/Cohere).
- **Multi-device credential sync** -- configure once on your laptop, the same encrypted credential set works from your desktop / tablet without copying API keys.
- **Multi-user team sharing** -- a self-hosted HTTP server can serve multiple developers, each with isolated per-user credentials (per-JWT-sub).
- **Always-on persistent process for webhooks/agents** -- HTTP servers stay alive between sessions, enabling background work, scheduled agents, or long-running graph builds.

## Method 5: Self-Hosting HTTP Mode

Host your own multi-user server. Single multi-user mode (per-JWT-sub credential isolation). Users paste their cloud-embedding API keys via the relay form -- there is no upstream OAuth flow because the API keys belong to third-party providers (Jina, Gemini, OpenAI, Cohere), not to better-code-review-graph itself.

### Required Env

| Variable | Description |
|:---------|:------------|
| `TRANSPORT_MODE=http` | Selects HTTP transport. |
| `PUBLIC_URL` | Public URL of your server (e.g. `https://your-domain.com`). |
| `DCR_SERVER_SECRET` | HMAC secret for stateless Dynamic Client Registration. Generate via `openssl rand -hex 32`. |

### Run the Server

```bash
docker run -p 8080:8080 \
  -e TRANSPORT_MODE=http \
  -e PUBLIC_URL=https://your-domain.com \
  -e DCR_SERVER_SECRET=$(openssl rand -hex 32) \
  n24q02m/better-code-review-graph:latest
```

Point clients to your server:
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

On first connection, each user opens the relay form at `https://your-domain.com/authorize` and pastes their cloud-embedding API keys (all optional -- empty submission keeps the user on local ONNX). Credentials are encrypted per-JWT-sub and never shared between users.

### Edge auth: relay password

Public HTTP deployments expose `<your-domain>/authorize` to URL discovery. To prevent random Internet users from accessing the relay form, mint a relay password:

```bash
openssl rand -hex 32
# Save in your skret / .env as:
MCP_RELAY_PASSWORD=<generated-32-byte-hex>
```

Share this password out-of-band (Signal/email/SMS) with anyone you invite to use your server. They will see a login form when first opening `/authorize`; once logged in, the cookie persists 24 hours.

**Single-user dev exception**: If `PUBLIC_URL=http://localhost:8080`, you can leave `MCP_RELAY_PASSWORD` empty to disable the gate. The server logs a warning if you skip the password with a non-localhost `PUBLIC_URL`.

## Credential Setup

All API keys are **optional**. The server works with local ONNX embeddings out of the box.

### Stdio Mode (Env Vars)

Set API keys in your MCP client `env` block or shell profile:

```bash
export JINA_AI_API_KEY="jina_..."
export GEMINI_API_KEY="AIza..."
```

### HTTP Mode (Relay Form)

Each user opens `https://<your-host>/authorize` in their browser, pastes API keys (or leaves empty), and submits. Credentials are encrypted per-JWT-sub and stored server-side.

## Environment Variable Reference

| Variable | Required | Default | Description |
|:---------|:---------|:--------|:------------|
| `JINA_AI_API_KEY` | No | -- | Jina AI: embedding + reranking (highest priority) |
| `GEMINI_API_KEY` | No | -- | Gemini: embedding (free tier). Also accepts `GOOGLE_API_KEY` |
| `OPENAI_API_KEY` | No | -- | OpenAI: embedding |
| `COHERE_API_KEY` | No | -- | Cohere: embedding + reranking. Also accepts `CO_API_KEY` |
| `EMBEDDING_BACKEND` | No | auto-detect | `cloud` or `local` (ONNX) |
| `EMBEDDING_MODEL` | No | auto-detect | Cloud embedding model name |
| `TRANSPORT_MODE` | No | `stdio` | Set to `http` to enable HTTP transport (multi-user). |
| `PUBLIC_URL` | Yes (http) | -- | Server's public URL for relay form. |
| `DCR_SERVER_SECRET` | Yes (http) | -- | HMAC secret for stateless Dynamic Client Registration. |
| `PORT` | No | `8080` | Server port (http mode only). |
| `LOG_LEVEL` | No | `INFO` | Logging level |

### Embedding Provider Priority

Cloud auto-detection order: Jina AI > Gemini > OpenAI > Cohere > Local ONNX (Qwen3)

All embeddings are stored at 768 dimensions. Switching providers does NOT invalidate existing vectors.

### Supported Languages

Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++, Solidity

### Ignore Files

Create `.code-review-graphignore` in your project root to exclude paths:

```
generated/**
*.generated.ts
vendor/**
node_modules/**
```

## Troubleshooting

### Graph build finds no files

Ensure the `repo_path` parameter points to the root of a code repository. Check that the project contains files in a supported language.

### First embedding is slow

On first use, the local ONNX embedding model (~570MB) is downloaded. Subsequent runs are instant. Use cloud embedding (any API key) to avoid this download.

### "No graph found" error

Build the graph first:

```
graph(action="build", repo_path="/path/to/your/repo")
```

### Docker cannot access repo files

Ensure the volume mount is correct. The repo path inside the container is `/repo`:

```bash
docker run -i --rm -v "/absolute/path/to/repo:/repo:ro" n24q02m/better-code-review-graph:latest
```
