# graph Tool Documentation

Code knowledge graph operations. Build, query, search, and analyze your codebase structure.

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

### query
Run predefined graph queries to explore code relationships.

**Parameters:**
- `pattern` (required): Query pattern. One of:
  - `callers_of`: Find functions that call the target
  - `callees_of`: Find functions called by the target
  - `imports_of`: Find what the target imports
  - `importers_of`: Find files that import the target
  - `children_of`: Find nodes contained in a file or class
  - `tests_for`: Find tests for the target
  - `inheritors_of`: Find classes inheriting from the target
  - `file_summary`: Get all nodes in a file
- `target` (required): Node name, qualified name, or file path
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "query", "pattern": "callers_of", "target": "authenticate"}
{"action": "query", "pattern": "file_summary", "target": "src/auth.py"}
{"action": "query", "pattern": "tests_for", "target": "UserService"}
```

Multi-word search uses AND-logic: `"firebase auth"` matches nodes containing both words.
Common JS/TS builtins (map, filter, forEach, etc.) are filtered from `callers_of` results to reduce noise.

---

### search
Search for code entities by name, keyword, or semantic similarity.

**Parameters:**
- `query` (required): Search string
- `kind`: Filter by node type: File, Class, Function, Type, or Test
- `limit`: Maximum results (default: 20)
- `repo_root`: Repository root path (auto-detected)

Uses vector embeddings for semantic search when available (run `embed` first). Falls back to keyword matching otherwise.

**Example:**
```json
{"action": "search", "query": "authentication", "kind": "Function"}
{"action": "search", "query": "database connection", "limit": 10}
```

---

### impact
Analyze the blast radius of changed files. Shows which functions, classes, and files are impacted by changes.

**Parameters:**
- `changed_files`: List of changed file paths (auto-detected from git)
- `max_depth`: Hops to traverse in dependency graph (default: 2)
- `max_results`: Maximum impacted nodes to return (default: 500)
- `base`: Git ref for auto-detecting changes (default: HEAD~1)
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "impact", "changed_files": ["src/auth.py", "src/models.py"]}
{"action": "impact", "max_depth": 3, "base": "main"}
```

---

### review
Generate a focused, token-efficient review context for code changes. Combines impact analysis with source snippets and review guidance.

**Parameters:**
- `changed_files`: Files to review (auto-detected from git)
- `max_depth`: Impact radius depth (default: 2)
- `include_source`: Include source code snippets (default: true)
- `max_lines_per_file`: Max source lines per file (default: 200)
- `base`: Git ref for change detection (default: HEAD~1)
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "review", "changed_files": ["src/auth.py"]}
{"action": "review", "include_source": false, "base": "main"}
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

Fixed 768-dim storage. Switching backends does NOT invalidate existing vectors. Only embeds nodes that don't already have up-to-date embeddings.

**Example:**
```json
{"action": "embed"}
```

---

### stats
Get aggregate statistics about the code knowledge graph.

**Parameters:**
- `repo_root`: Repository root path (auto-detected)

Returns total nodes, edges, languages, files, embedding count, and last update time.

**Example:**
```json
{"action": "stats"}
```

---

### large_functions
Find functions, classes, or files exceeding a line-count threshold. Useful for decomposition audits and code quality checks.

**Parameters:**
- `min_lines`: Minimum line count to flag (default: 50)
- `kind`: Filter: Function, Class, File, or Test
- `file_path_pattern`: Filter by file path substring (e.g. "components/")
- `limit`: Maximum results (default: 50)
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "large_functions", "min_lines": 100, "kind": "Function"}
{"action": "large_functions", "file_path_pattern": "src/", "limit": 20}
```

## Supported Languages

Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++

## Graph Structure

**Node types:** File, Class, Function, Type, Test
**Edge types:** CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON

Qualified names use `file_path::name` format (e.g. `src/auth.py::authenticate`).
