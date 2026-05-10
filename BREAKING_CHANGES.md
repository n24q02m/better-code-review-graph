# v2.0.0 Breaking Changes

This release introduces required schema changes to the on-disk graph
database. The migration is auto-applied on first GraphStore open, with
a backup saved to `graph.db.pre-2.0.bak` for rollback.

## Schema changes

- `nodes.valid_from_sha` (TEXT NOT NULL) -- backfilled with the repo's
  current HEAD SHA at migration time.
- `nodes.valid_to_sha` (TEXT NULL) -- NULL = currently-valid row.
- `edges.valid_from_sha` (TEXT NOT NULL) and `edges.valid_to_sha` (TEXT NULL).
- `nodes.security_tags` (TEXT NULL) -- JSON array of `<rule_id>:<severity>`.
- New `commits` table -- populated on first federated build.
- New `idx_nodes_temporal` and `idx_edges_temporal` composite indexes.
- New `idx_commits_repo_time` index.

## Behavior changes

- All query/search/impact actions default to `WHERE valid_to_sha IS NULL`
  (currently-valid rows only). Set `as_of=<sha>` for snapshot queries.
- `nodes.qualified_name` UNIQUE constraint replaced with partial unique
  index `WHERE valid_to_sha IS NULL` to allow temporal supersedes.

## Required environment

- The migration requires `git rev-parse HEAD` to succeed in the directory
  containing the graph database. If git is unavailable, the migration
  aborts with an actionable error.
- Set `CRG_TEST_ALLOW_NO_GIT=1` to bypass the git check (test/CI use only).

## Rollback

```bash
CRG_DOWNGRADE_TO_1_X=1 uv run better-code-review-graph
```

This restores `graph.db.pre-2.0.bak` and archives the v2 db as
`graph.db.post-2.0.archived`.

## New features

- **Security scanning** (`security` tool) -- Tier 1 heuristic + Tier 2 Semgrep.
  See `help(topic="security")`.
- **Temporal queries** -- `as_of` / `diff` cross-cutting params on `query`.
  See `help(topic="query")`.
- **Refactor auditing** -- `review(action="delta", show_line_shifts=true)`.
  See `help(topic="review")`.
- **Cross-repo federation** (introduced in Phase 2) -- `roots=[...]` on
  `graph(action="build")` + `repo` filter on query/review.
