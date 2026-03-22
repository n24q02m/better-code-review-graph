# review Tool Documentation

Generate focused, token-efficient review context for code changes. Combines impact analysis with source snippets and review guidance.

## Parameters

- `changed_files`: Files to review (auto-detected from git diff if omitted)
- `max_depth`: Impact radius depth (default: 2)
- `include_source`: Include source code snippets (default: true)
- `max_lines_per_file`: Max source lines per file (default: 200)
- `base`: Git ref for change detection (default: HEAD~1)
- `repo_root`: Repository root path (auto-detected)

## Example

```json
{"changed_files": ["src/auth.py"]}
{"include_source": false, "base": "main"}
```

## What It Returns

1. **Changed files** — auto-detected from git diff
2. **Impacted nodes and files** — blast radius via BFS traversal
3. **Source code snippets** — relevant lines for changed areas (with context)
4. **Review guidance** — automated analysis:
   - Untested changed functions
   - Wide blast radius warnings
   - Inheritance/implementation relationship changes
   - Cross-file impact assessment

## Usage Tips

- Use `base="main"` when reviewing a full PR (instead of just last commit)
- Set `include_source=false` to reduce token usage when you only need structural info
- Combine with `query(action="query", pattern="tests_for", target=<func>)` for deeper test coverage analysis
