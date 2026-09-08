# Better Code Review Graph Handover

## Current operation

- Package: `better-code-review-graph`; local-first code intelligence graph.
- Runtime: Python 3.13, SQLite graph state, Tree-sitter parser, optional local Fastretrieval embeddings, optional cloud embedding and summary adapters through `mcp_core.llm`.
- Primary surfaces: `better-code-review-graph` CLI and MCP stdio adapter. HTTP is opt-in and uses authenticated subject-scoped storage.
- Default graph state: `<repository>/.better-code-review-graph/graph.db`. Existing `.code-review-graph` state is preserved and is never adopted or deleted automatically.
- Cloud model configuration is explicit per task. Empty embedding configuration uses local Fastretrieval; empty summary configuration disables summaries. Cohere `embed-v4.0` uses 1024 dimensions and explicit document/query input types.

## Build, run, and verify

```bash
uv sync --locked --group dev --no-sources
uv run better-code-review-graph
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv build
```

Use an isolated repository fixture for graph builds and protocol checks. Do not point validation at a user's existing graph database unless the scenario explicitly tests migration or preservation.

## Data and safety invariants

- A remote HTTP request without a verified authenticated subject fails closed.
- Subject credentials, model chains, API bases, and graph databases are isolated by subject.
- PHP CALLS post-processing resolves unique same-repository targets and leaves dynamic, ambiguous, inherited, or external calls unresolved with coverage warnings.
- Exporters stream SQLite rows and escape format-specific identifiers and values.
- Cohere requests must not be made without an explicit capped spend authorization and usage receipt.
- This repository has no dependency on hosted VM infrastructure.

## In-flight and rollback

The current maintenance lane covers PHP call resolution, graph-state collision prevention, embedding dimension validation, request isolation, export correctness, and dependency maintenance. Roll back a source change by reverting the owning commit after checking the graph schema and package version; do not delete either old or new graph state as a rollback shortcut. Rebuild a graph into the new state directory when changing parser or embedding contracts.

## Target architecture and migration map

1. Keep domain logic in `parser.py`, `graph.py`, `incremental.py`, `embeddings.py`, `summarizer.py`, and `tools.py`; adapters remain thin.
2. Keep `server.py` responsible for MCP registration, request context, and structured error payloads only.
3. Preserve the graph schema and migration history. Add migrations for durable schema changes; never silently reinterpret legacy rows.
4. Keep embedding provider and dimension identity attached to stored vectors. Re-embed when provider or width changes; reject malformed or mixed-width data.
5. Keep exports cursor-based and validate representative DOT, JSON-LD, GraphML, Cypher, and CRG payloads with format consumers where available.
6. Extend CLI and MCP behavior from the same tool/domain functions; do not duplicate graph logic in an adapter.

## First weeks

### Week 1

- Reproduce graph build and impact behavior on an isolated PHP fixture.
- Verify new-state creation leaves legacy `.code-review-graph` data unchanged.
- Run repository-native lint, type, package, and full tests.
- Review current dependency and security backlog individually.

### Weeks 2–3

- Verify a BETA artifact by exact workflow run, job conclusions, digest, and install readback.
- Exercise a representative MCP graph build/query/impact round trip against the verified artifact.
- Verify remote subject isolation with two independent subjects and no ambient credential fallback.

### Months 1–3

- Measure large-graph export memory with a reproducible public fixture.
- Maintain provider/dimension compatibility as producer libraries evolve.
- Add domain API/CLI parity only where a real consumer requires it; preserve MCP compatibility during migration.
