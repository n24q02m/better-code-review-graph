# Better Code Review Graph -- Manual Setup Guide

> **2026-05-02 Update (v<auto>+)**: Plugin install (Method 1) now uses pure stdio mode. API keys are optional env vars.
> The previous "Zero-Config Relay" auto-spawn pattern has been removed.
> If you relied on the relay form to enter API keys, please:
> 1. Set the env var directly in plugin config (Method 1), OR
> 2. Use HTTP self-host mode (advanced; out of scope of this guide).

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

## Credential Setup

All API keys are **optional**. The server works with local ONNX embeddings out of the box.

### Stdio Mode (Env Vars)

Set API keys in your MCP client `env` block or shell profile:

```bash
export JINA_AI_API_KEY="jina_..."
export GEMINI_API_KEY="AIza..."
```

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
