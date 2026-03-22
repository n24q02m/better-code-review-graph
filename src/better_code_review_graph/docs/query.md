# query Tool Documentation

Read-only queries against the knowledge graph — pattern queries, search, impact analysis, and code quality checks.

## Actions

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
- `search_query` (required): Search string
- `kind`: Filter by node type: File, Class, Function, Type, or Test
- `limit`: Maximum results (default: 20)
- `repo_root`: Repository root path (auto-detected)

Uses vector embeddings for semantic search when available (run `graph action=embed` first). Falls back to keyword matching otherwise.

**Example:**
```json
{"action": "search", "search_query": "authentication", "kind": "Function"}
{"action": "search", "search_query": "database connection", "limit": 10}
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
