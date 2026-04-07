# Better Code Review Graph -- Manual Setup Guide

## Prerequisites

- **Python 3.13** (3.14+ is NOT supported)
- `uv` or `uvx` installed ([docs](https://docs.astral.sh/uv/getting-started/installation/))
- Docker (optional, for containerized setup)
- A code repository to analyze

## Method 1: Plugin Install

For Claude Code users, the plugin approach includes auto-build hooks and review skills.

1. Open Claude Code
2. Run the following commands:
   ```bash
   /plugin marketplace add n24q02m/claude-plugins
   /plugin install better-code-review-graph@n24q02m-plugins
   ```
3. The server starts automatically when Claude Code launches
4. The SessionStart hook auto-builds the graph for the current project
5. PostToolUse hook auto-updates the graph after file changes

## Method 2: uvx Direct

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

2. Restart your MCP client
3. Build the graph for your project:
   ```
   graph(action="build", repo_path="/path/to/your/repo")
   ```

## Method 3: Docker

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

## Credential Setup

### Option A: Environment Variables (Recommended)

Set API keys in your shell profile or MCP client settings:

```bash
export JINA_AI_API_KEY="jina_..."
```

When environment variables are set, the relay is skipped entirely.

## Environment Variable Reference

| Variable | Default | Description |
|:---------|:--------|:------------|
| `JINA_AI_API_KEY` | -- | Jina AI: embedding + reranking (highest priority) |
| `GEMINI_API_KEY` | -- | Gemini: embedding (free tier). Also accepts `GOOGLE_API_KEY` |
| `OPENAI_API_KEY` | -- | OpenAI: embedding |
| `COHERE_API_KEY` | -- | Cohere: embedding + reranking. Also accepts `CO_API_KEY` |
| `EMBEDDING_BACKEND` | auto-detect | `cloud` or `local` (ONNX) |
| `EMBEDDING_MODEL` | auto-detect | Cloud embedding model name |
| `LOG_LEVEL` | `INFO` | Logging level |

### Zero-Config Relay

> **Recommended for new users.** The relay is the primary setup method -- no environment variables needed. Credentials are encrypted end-to-end and stored locally.

No manual configuration needed. On first start:

1. The server prints a setup URL to stderr
2. Open the URL in any browser
3. Fill in your API keys on the guided form:
   - **Jina AI API Key** -- embedding + reranking ([get key](https://jina.ai/api-key))
   - **Gemini API Key** -- embedding, free tier available ([get key](https://aistudio.google.com/apikey))
   - **OpenAI API Key** -- embedding ([get key](https://platform.openai.com/api-keys))
   - **Cohere API Key** -- embedding + reranking ([get key](https://dashboard.cohere.com/api-keys))
4. All fields are optional -- leave empty for local ONNX mode
5. Credentials are encrypted and stored at `~/.config/mcp/config.enc`

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

### Relay setup URL does not appear

The relay URL only appears when no API keys are set in environment. To force relay setup, unset all API key variables first.
