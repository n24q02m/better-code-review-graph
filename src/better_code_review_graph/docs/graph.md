# graph Tool Documentation

Graph lifecycle operations — build, update, embed, and check stats.

## Actions

### build
Full or incremental graph build. Parses source files with Tree-sitter, extracts functions/classes/imports, and builds a structural knowledge graph.

**Parameters:**
- `full_rebuild`: Re-parse all files (default: false, incremental)
- `base`: Git ref for incremental diff (default: HEAD~1)
- `repo_root`: Repository root path (auto-detected)
- `roots`: Optional list of additional repo roots for federated build (Phase 2). When provided, runs a full federated rebuild over `repo_root` plus every entry in `roots`. Each root is registered in the `repos` table with a stable `repo_id` derived from its path. Omit (default `null`) for a single-repo build that preserves the legacy behaviour. See "Federation: cross-repo graphs" below for the full recipe.

**Example:**
```json
{"action": "build", "full_rebuild": true}
{"action": "build", "base": "main"}
{"action": "build", "roots": ["../shared-lib", "../web-app"]}
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
- **Local (default)**: fastretrieval built-in ONNX registry (~570MB download on first use, zero-config)
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

## Federation: cross-repo graphs (Phase 2 v1.7+)

A single graph DB can index multiple repository roots and resolve imports between them. Pass a `roots` list to `graph(action="build")` and each root is registered in the `repos` registry table with a stable `repo_id`. Subsequent `query` and `review` actions accept a `repo='<repo_id>'` filter to scope results to one federated repo (see `query.md` / `review.md`).

**`repo_id` derivation:** `<basename>-<sha256-prefix-8>` of the absolute, resolved path. Filesystem-root basenames (`/`, `C:\`) normalise to `root-<hash>`. The id is deterministic across machines for the same absolute path -- pass the same `roots` list and you get the same ids. Empty / `.` / `..` basenames also normalise to `root`.

**Single-repo backwards compat:** Omitting `roots` (or passing `roots=[]` / `null`) runs the existing single-root build path. Existing graphs created before Phase 2 keep working; the migration adds a `repo_id` column with a NULL default and a `repos` table without forcing a re-build. Federation is purely opt-in.

**Cross-repo edges:** When the parser resolves an `IMPORTS_FROM` edge whose target lives in a different registered repo, the edge's `target_qualified` is written as `<other_repo_id>:<file>::<symbol>` (note the leading `<repo_id>:` prefix -- single-repo edges keep the legacy `<file>::<symbol>` shape). Per-language resolvers cover Python, TypeScript, Go, Rust, and Java; remaining tier-2 languages fall back to a generic dispatcher that performs basename matching against registered roots.

**`last_indexed_sha`:** `graph(action="update")` records the current git HEAD per repo into `repos.last_indexed_sha` when git is available, so federated incremental updates can later diff per-root against the last indexed commit.

### Recipe 1 -- Federated multi-repo Python build

Two Python repos that import each other; build them into one graph and query a single repo.

```json
{"tool": "graph", "action": "build",
 "repo_root": "./repo_a",
 "roots": ["./repo_b"]}
```

Response (abridged):
```json
{
  "status": "ok",
  "build_type": "full_federated",
  "summary": "Federated build over 2 root(s): parsed 87 files, created 612 nodes and 941 edges.",
  "files_parsed": 87,
  "total_nodes": 612,
  "total_edges": 941,
  "roots": ["/abs/path/repo_a", "/abs/path/repo_b"]
}
```

The derived `repo_id`s for these roots will look like `repo_a-3f2a91bc` / `repo_b-1d4e87aa`. Inspect `repos` in the SQLite DB (or capture them from `RepoRegistry.entries()` if you embed the library) to copy-paste them into a scoped query:

```json
{"tool": "query", "action": "query",
 "pattern": "callers_of",
 "target": "src/auth.py::authenticate",
 "repo": "repo_a-3f2a91bc"}
```

Only callers whose nodes belong to `repo_a` are returned -- callers in `repo_b` are filtered out, even if `repo_b` imports `authenticate`.

### Recipe 2 -- Cross-language federation (Python lib + TypeScript app)

A Python library + a TypeScript app that consumes its compiled artefacts. Each language's per-language resolver runs first; the dispatcher falls back to basename matching for any tier-2 file under either root.

```json
{"tool": "graph", "action": "build",
 "repo_root": "./py-core",
 "roots": ["./ts-app"]}
```

After build, an import in `ts-app/src/api.ts` that resolves to a Python symbol in `py-core/src/core/auth.py::authenticate` materialises an `IMPORTS_FROM` edge whose `target_qualified` reads:

```
py_core-9a8b7c6d:src/core/auth.py::authenticate
```

Use the cross-repo qualified name to walk back across the boundary:

```json
{"tool": "query", "action": "query",
 "pattern": "importers_of",
 "target": "src/core/auth.py::authenticate",
 "repo": "py_core-9a8b7c6d"}
```

Importers in both repos appear, and each result row carries its own `repo_id` so you can tell which side the call lives on. Drop the `repo` filter to see every importer regardless of repo, including the TypeScript ones.

---

## Supported Languages

Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++

## Graph Structure

**Node types:** File, Class, Function, Type, Test
**Edge types:** CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON

`IMPLEMENTS` means the parser found a declared abstract contract: an explicit
interface/trait clause in languages that have one, or an ABC/Protocol contract
in Python. Qualified Python decorators such as `@abc.abstractmethod` count.
It does not claim implicit or structural conformance, such as Python protocol
typing without inheritance or Go method-set satisfaction. C# has no distinct
`implements` syntax, so a class's single external base remains unresolved and
is kept as `INHERITS`; same-file interfaces and struct base lists are proven
implementations. `INHERITS` remains the edge for concrete superclass and other
inheritance relationships.

`TESTED_BY` means **called directly by a test function**, not "adequately
tested". It is emitted for each call site inside a test, so a function the
test merely uses along the way -- a fixture builder, a comparison utility --
also receives one. Functions defined in a test file are excluded, since test
scaffolding is never the subject under test; support code living in an
ordinary module cannot be told apart from a subject by syntax alone and is
not excluded. A call written inside a helper belongs to that helper, so
indirect reach is not credited to the test. Read `tests_for` results and the
untested-function warning in `get_review_context` with that meaning in mind.

Qualified names use `file_path::name` format (e.g. `src/auth.py::authenticate`). Cross-repo edges produced by federation prefix the target with the owning `repo_id`: `<repo_id>:<file_path>::<symbol>` (see "Federation: cross-repo graphs" above).
