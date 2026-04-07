# Better Code Review Graph -- Agent Setup Guide

> Give this file to your AI agent to automatically set up better-code-review-graph.

## Option 1: Claude Code Plugin (Recommended)

```bash
# Install from marketplace (includes skills: /refactor-check, /review-delta, /review-pr + hooks)
/plugin marketplace add n24q02m/claude-plugins
/plugin install better-code-review-graph@n24q02m-plugins
```

No further configuration needed. The plugin includes SessionStart and PostToolUse hooks that auto-build and auto-update the code graph.

## Option 2: MCP Direct

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

## Option 3: Docker

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

### General

| Variable | Required | Default | Description |
|:---------|:---------|:--------|:------------|
| `LOG_LEVEL` | No | `INFO` | Logging level |

## Authentication

### Zero-Config Relay

> **Recommended.** The relay is the primary setup method. Credentials are encrypted end-to-end and stored locally. Environment variables are supported for backward compatibility.

On first run without any API keys in environment:

1. Server starts and creates a relay session
2. A setup URL is printed to stderr
3. Open the URL in any browser
4. Fill in API keys on the guided form (all optional)
5. Credentials are encrypted and stored locally at `~/.config/mcp/config.enc`
6. Subsequent runs load saved credentials automatically

The relay form has 4 optional fields:
- **Jina AI API Key** -- embedding + reranking (highest priority)
- **Gemini API Key** -- embedding (free tier available)
- **OpenAI API Key** -- embedding
- **Cohere API Key** -- embedding + reranking

Leave all empty to use local ONNX mode (Qwen3 embedding, ~570MB download on first use).

### Environment Variables (Recommended)

Set API keys directly as environment variables to skip relay entirely.

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
