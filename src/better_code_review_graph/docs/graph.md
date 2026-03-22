# graph Tool Documentation

Graph lifecycle operations — build, update, embed, and check stats.

## Actions

### build
Full or incremental graph build. Parses source files with Tree-sitter, extracts functions/classes/imports, and builds a structural knowledge graph.

**Parameters:**
- `full_rebuild`: Re-parse all files (default: false, incremental)
- `base`: Git ref for incremental diff (default: HEAD~1)
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "build", "full_rebuild": true}
{"action": "build", "base": "main"}
```

---

### update
Alias for `build` with `full_rebuild=false`. Only re-parses changed files.

**Parameters:**
- `base`: Git ref for diff (default: HEAD~1)
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "update"}
{"action": "update", "base": "origin/main"}
```

---

### stats
Get aggregate statistics about the code knowledge graph. Returns total nodes, edges, languages, files, embedding count, and last update time.

**Parameters:**
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "stats"}
```

---

### embed
Compute vector embeddings for all graph nodes to enable semantic search.

**Parameters:**
- `repo_root`: Repository root path (auto-detected)

Dual-mode embedding:
- **Local (default)**: qwen3-embed ONNX (~570MB download on first use, zero-config)
- **Cloud**: LiteLLM (set `API_KEYS` or `LITELLM_PROXY_URL` to activate)
- **Explicit**: Set `EMBEDDING_BACKEND=local|litellm` to override

Fixed 768-dim storage. Switching backends does NOT invalidate existing vectors.

**Example:**
```json
{"action": "embed"}
```

## Supported Languages

Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++

## Graph Structure

**Node types:** File, Class, Function, Type, Test
**Edge types:** CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON

Qualified names use `file_path::name` format (e.g. `src/auth.py::authenticate`).
