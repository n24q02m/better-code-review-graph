# Better Code Review Graph -- Agent Setup Guide

> Give this file to your AI agent to automatically set up better-code-review-graph.

> **2026-05-02 Update (v<auto>+)**: Plugin install (Option 1) now uses pure stdio mode. API keys are optional env vars.
> The previous "Zero-Config Relay" auto-spawn pattern has been removed.
> If you relied on the relay form to enter API keys, please:
> 1. Set the env var directly in plugin config (Option 1), OR
> 2. Use HTTP self-host mode (advanced; out of scope of this guide).

## Method overview

This plugin supports **1 install method only**: stdio via plugin install (`uvx`/`npx`). Reason: the plugin needs direct host access to your project files (Godot project / repo path) and doesn't ship Docker or HTTP variants.

For comparison, the other 6 plugins in this stack (`better-notion-mcp`, `better-email-mcp`, `better-telegram-mcp`, `wet-mcp`, `mnemo-mcp`, `imagine-mcp`) support 3 methods:
1. **Default** -- Plugin install (`uvx`/`npx`) stdio
2. **Fallback** -- Docker stdio (Windows/macOS PATH issues)
3. **Recommended** -- Docker HTTP (multi-device, OAuth/relay form, claude.ai web)

## Option 1: Claude Code Plugin (Recommended)

Plugin marketplace install runs the server in **pure stdio mode** with optional API key env vars. No daemon-bridge, no auto-spawn, no relay form. Graph storage is local SQLite -- no external graph database required.

### Step 0: Credential prompt

When the install command runs, Claude Code prompts for the optional field declared in `plugin.json` `userConfig`:

| Field | Required | Sensitive | Source |
|:------|:---------|:----------|:-------|
| `JINA_AI_API_KEY` | No | Yes | https://jina.ai/api-dashboard/ |

Press Enter to skip; the server falls back to local ONNX. The plugin manifest substitutes the value into `mcpServers.better-code-review-graph.env.JINA_AI_API_KEY` via `${user_config.JINA_AI_API_KEY}` and stores the sensitive value in the system keychain (persists across `/plugin update`). You do not edit `env` manually.

### Steps

```bash
# Install from marketplace (includes skills: /refactor-check, /review-delta, /review-pr + hooks)
/plugin marketplace add n24q02m/claude-plugins
/plugin install better-code-review-graph@n24q02m-plugins
```

The plugin includes SessionStart and PostToolUse hooks that auto-build and auto-update the code graph.

> Other optional env vars (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `COHERE_API_KEY`, `EMBEDDING_BACKEND`, etc.) are not part of the `userConfig` prompt; add them manually to `mcpServers.better-code-review-graph.env` in your settings if needed.

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
