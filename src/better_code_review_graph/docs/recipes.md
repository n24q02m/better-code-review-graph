# Recipes

Stage-mapped operational patterns combining the 5 tools (graph, query,
review, config, help). Reduces derive-from-first-principles overhead for
new agents picking up the toolset for code review and scope-completeness
audits.

## Stage 0 - Prerequisites

### Freshness check
Before any query: verify the graph is current and embeddings exist.

```json
{"tool": "config", "action": "status"}
```

Look for `total_nodes > 0` and `last_updated < 24h`. If `embeddings_count == 0`
and you plan to run `search` on phrases (not literal identifiers), run
`graph action=embed` first or expect a keyword-only warning (#317).

---

## Stage 1 - Build / refresh

### Fresh clone
```json
{"tool": "graph", "action": "build", "full_rebuild": true}
```

### Incremental after fetch / pull
```json
{"tool": "graph", "action": "update"}
```

The response includes a `reviewer_summary` block (#329) with
`functions_added` / `functions_removed` / `functions_modified` /
`modules_newly_impacted`. Feed those names into Stage 5 verification
subagents directly.

---

## Stage 2 - Search and exploration

### Who calls X
```json
{"tool": "query", "action": "query", "pattern": "callers_of", "target": "<file::symbol>"}
```

Spot-check at least one caller's source line before drawing conclusions.
Same-file dynamic dispatch (`asyncio.to_thread`, `functools.partial`,
decorators) is surfaced via `dynamic_dispatch_hints` (#331) so you know
when the AST answer is a lower bound.

### Blast radius
```json
{"tool": "query", "action": "impact", "target": "<file::symbol>", "max_depth": 1}
```

Depth 2 fans to 1000+ on shared hooks/utils. The response is auto-truncated
to `max_payload_bytes` bytes (default 500_000); check `results_truncated`
and `hint` to scope down (#315).

### Duplicate-implementation check
```json
{"tool": "query", "action": "search", "search_query": "<pattern>"}
```

Check the response `header.embeddings_count` first (#330). If zero, use a
literal identifier only - keyword fallback returns garbage on phrases
(#317 emits a warning when it sees a phrase-shaped query).

---

## Stage 3 - Scope completeness check

For every function named in scope, run `callers_of` and compare the
caller count against your expectation. For every "X doesn't exist" claim,
run `search X`.

```json
{"tool": "query", "action": "query", "pattern": "callers_of", "target": "<symbol>"}
{"tool": "query", "action": "search", "search_query": "<symbol>"}
```

Note: the response `header.keyword_only` (#330) tells you whether `search`
ran in semantic or keyword mode without a separate `config status` call.

---

## Stage 4 - Pre-merge review

```json
{"tool": "review", "base": "<default-branch>"}
```

Returns: blast radius, untested-function list, wide-blast flags, and
`source_snippets` for the diff in one call. Use `base="main"` for full PRs,
`base="HEAD~1"` for the most recent commit.

---

## Tips

- `query.action="callers_of"` auto-resolves the bare-name File+Function
  ambiguity (#316) - you can pass `auth` directly when both `auth.py`
  and `auth()` exist, the Function will be picked.
- `search` and `query` responses always include a `header` block with
  `embeddings_count`, `keyword_only`, and `graph_last_updated` (#330)
  so audit trails do not need a separate `config status` call.
- Pass `max_payload_bytes=0` to `impact` to opt out of the size cap if
  you can handle the full payload.
