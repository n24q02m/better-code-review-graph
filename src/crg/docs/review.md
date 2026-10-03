# review Tool Documentation

Generate focused, token-efficient review context for code changes. Combines impact analysis with source snippets and review guidance.

## Actions

- `context` (default): Auto-detects changed files from git diff and returns the structural summary, impacted nodes, source snippets, and review guidance.
- `delta`: Wraps the `query.diff` buckets (added / removed / modified) and, when `show_line_shifts=true`, surfaces qualified_names whose `line_start` moved between two commits — useful for refactor auditing ("this function moved from line 10 to line 42, did anything break?").

## Parameters

### context action

- `changed_files`: Files to review (auto-detected from git diff if omitted)
- `max_depth`: Impact radius depth (default: 2)
- `include_source`: Include source code snippets (default: true)
- `max_lines_per_file`: Max source lines per file (default: 200)
- `base`: Git ref for change detection (default: HEAD~1)
- `repo_root`: Repository root path (auto-detected)
- `languages`: Optional list of language names (e.g. `["python"]`) to scope the `untested_functions` list. Excludes functions whose language doesn't match.
- `repo`: Federated repo filter (Phase 2). When non-empty, scopes the impact subgraph and untested-function audit to nodes whose `repo_id` matches. Default `""` includes every federated repo, so cross-repo callers/importers contribute to the review context. Useful when a PR touches one repo in a federated graph but you only want review guidance about that repo. See `graph.md` "Federation: cross-repo graphs" for `repo_id` discovery.

### delta action

- `from_sha`: Earlier commit SHA (required).
- `to_sha`: Later commit SHA (required).
- `show_line_shifts`: When true, include nodes whose `line_start` moved between `from_sha` and `to_sha` in the response (default: false). Each entry is `{qualified_name, before_line, after_line}`.
- `repo`: Federated repo filter (same semantics as context).
- `repo_root`: Repository root path (auto-detected).

## Examples

```json
{"changed_files": ["src/auth.py"]}
{"action": "context", "include_source": false, "base": "main"}
{"changed_files": ["src/auth.py"], "repo": "repo_a-3f2a91bc"}
{"action": "delta", "from_sha": "abc123...", "to_sha": "def456...", "show_line_shifts": true}
```

## What It Returns

### context action

1. **Changed files** — auto-detected from git diff
2. **Impacted nodes and files** — blast radius via BFS traversal
3. **Source code snippets** — relevant lines for changed areas (with context)
4. **Review guidance** — automated analysis:
   - Untested changed functions
   - Wide blast radius warnings
   - Inheritance/implementation relationship changes
   - Cross-file impact assessment

### delta action

- `diff`: The full `query.diff` payload (`from_sha`, `to_sha`, `added`, `removed`, `modified`).
- `line_shifts` (only when `show_line_shifts=true`): list of `{qualified_name, before_line, after_line}` for every symbol whose `line_start` moved across the supersede pair at `to_sha`. Same-line supersedes (body changed but `line_start` unchanged) are excluded.

## Usage Tips

- Use `base="main"` when reviewing a full PR (instead of just last commit)
- Set `include_source=false` to reduce token usage when you only need structural info
- Combine with `query(action="query", pattern="tests_for", target=<func>)` for deeper test coverage analysis
- Use `action="delta"` with `show_line_shifts=true` to audit pure refactors — when no logic changed but functions moved, the `line_shifts` list pinpoints exactly which callsites a reviewer should re-verify.
