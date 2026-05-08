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
- **Cloud**: Multi-provider (set `JINA_AI_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `COHERE_API_KEY` to activate)
- **Explicit**: Set `EMBEDDING_BACKEND=local|cloud` to override

Fixed 768-dim storage. Switching backends does NOT invalidate existing vectors.

**Example:**
```json
{"action": "embed"}
```

---

## Export the graph

Export the full code knowledge graph in an interoperable format. Inline by default; pass `output_path` to write to disk and return only metadata.

**Parameters:**
- `format`: `graphml` | `json-ld` | `dot` | `cypher` (default: `graphml`, case-insensitive)
- `output_path`: Optional file path. When provided, payload is written and the response includes only `bytes` + `output_path`. When omitted, payload is returned inline under `payload`.
- `repo_root`: Repository root path (auto-detected)

**Format integration hints:**
- `graphml` -- Imports into Gephi / Cytoscape / NetworkX for visualization and structural analysis.
- `json-ld` -- JSON-aware tooling and linked-data pipelines; preserves node/edge typing.
- `dot` -- Renders directly via Graphviz (`dot -Tsvg graph.dot -o graph.svg`).
- `cypher` -- Replays into Neo4j (`MERGE` statements for nodes + edges); useful for ad-hoc graph queries.

**Example:**
```json
{"action": "export", "format": "graphml"}
{"action": "export", "format": "json-ld", "output_path": "g.jsonld"}
```

MCP call form:
```
graph(action="export", format="graphml")                          # inline
graph(action="export", format="json-ld", output_path="g.jsonld")  # file
```

---

## Generate LLM summaries

Generate one-paragraph LLM docstrings for `Function` nodes that lack a stored summary or whose source has changed. Stored alongside each node and concatenated into the embedding input -- boosts semantic search recall by roughly 15% by giving the embedder higher-signal text than raw identifiers + signatures alone.

**Parameters:**
- `max_nodes`: Cost cap -- max LLM calls per invocation (default: `500`)
- `repo_root`: Repository root path (auto-detected)

**Provider auto-detection** (priority order):
1. `GEMINI_API_KEY` (or `GOOGLE_API_KEY` alias) -- Gemini
2. `OPENAI_API_KEY` -- OpenAI

Local-only mode does **not** generate summaries. This is intentional: a small ONNX embedder running offline is the zero-cost default; summaries are an opt-in cloud upgrade. When no provider key is set, the action returns `status: "skipped", reason: "no_provider_configured"` and the graph is unchanged.

**Cost cap + caching:**
- Default cap is 500 LLM calls per invocation. Tune with `max_nodes` for tighter budgets.
- Repeat invocations skip nodes whose `source_hash` + `summary_provider` haven't changed -- the cache key is `"{sha256(source_text)}:{provider}"`, so re-running on an unchanged repo is a no-op (cached count goes up, generated count stays at 0). Switching provider invalidates entries even when source bytes are identical.

**Example:**
```json
{"action": "summarize", "max_nodes": 200}
```

MCP call form:
```
graph(action="summarize", max_nodes=200)
```

**When to re-run:** after `graph(action="update")` brings new functions in, or after large refactors where many `source_hash` values change. Edits to existing function bodies invalidate their cached summary automatically -- the next `summarize` call regenerates only the changed nodes.

## Supported Languages

Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++

## Graph Structure

**Node types:** File, Class, Function, Type, Test
**Edge types:** CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON

Qualified names use `file_path::name` format (e.g. `src/auth.py::authenticate`).
