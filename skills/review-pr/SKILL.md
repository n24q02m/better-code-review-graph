---
name: review-pr
description: Comprehensive PR review -- full branch diff against base, commit-by-commit analysis, breaking change detection, conventional commit verification.
argument-hint: "[PR number or branch name]"
---

# Review PR

Comprehensive code review of a pull request or branch diff against its base. Unlike review-delta (quick review of uncommitted local changes), this reviews ALL commits in a branch for PR submission readiness.

**Token optimization:** Before starting, call `help(topic="graph")` for the full actions reference. Never include full files unless explicitly asked.

## Steps

1. **Identify the changes** for the PR:
   - If a PR number or branch is provided, use `git diff main...<branch>` to get changed files
   - Otherwise auto-detect from the current branch vs main/master

2. **Update the graph** by calling `graph(action="build", base="main")` to ensure the graph reflects the current state.

3. **Commit-by-commit analysis** (for PRs with >3 commits):
   - `git log --oneline main..HEAD` to list all commits
   - Group related commits by area (feature, fix, refactor, test, docs)
   - Verify each commit message follows Conventional Commits (`type(scope): description`)
   - Flag commits that mix unrelated changes

4. **Get the full review context** by calling `review(base="main")`:
   - Returns all changed files across all commits in the PR
   - Includes impacted nodes and blast radius

5. **Analyze impact** by calling `query(action="impact", base="main")`:
   - Review the blast radius across the entire PR
   - Identify high-risk areas (widely depended-upon code)

6. **Breaking change detection** for public APIs:
   - Identify exported/public functions, classes, types that changed
   - Check for: removed parameters, changed return types, renamed exports, removed functions
   - Use `query(action="query", pattern="callers_of", target=<func>)` to find all consumers
   - Flag any change where callers outside the PR would break

7. **Deep-dive each changed file**:
   - Read the full source of files with significant changes
   - Use `query(action="query", pattern="tests_for", target=<func>)` to verify test coverage
   - Check for untested new functions

8. **Generate structured review output**:

   ```
   ## PR Review: <title>

   ### Summary
   <1-3 sentence overview>

   ### Conventional Commits Check
   - [x] `feat(parser): add Go support` -- valid
   - [ ] `fixed stuff` -- invalid, should be `fix(scope): description`

   ### Risk Assessment
   - **Overall risk**: Low / Medium / High
   - **Blast radius**: X files, Y functions impacted
   - **Test coverage**: N changed functions covered / M total
   - **Breaking changes**: None / List of breaking changes

   ### File-by-File Review
   #### <file_path>
   - Changes: <description>
   - Impact: <who depends on this>
   - Issues: <bugs, style, concerns>

   ### Missing Tests
   - <function_name> in <file> - no test coverage found

   ### Recommendations
   1. <actionable suggestion>
   ```

## Key Differences from review-delta

| Aspect | review-delta | review-pr |
|---|---|---|
| Scope | Uncommitted changes only | Full branch diff (all commits) |
| Speed | Fast, minimal context | Thorough, more context |
| Use case | Quick check before commit | PR submission readiness |
| Commit analysis | N/A | Commit-by-commit + conventional commit check |
| Breaking changes | Not checked | Explicitly detected |

## Tips

- For large PRs (>10 files), focus on the highest-impact files first (most dependents)
- Use `query(action="search", search_query=<term>)` to find related code the PR might have missed
- Check if renamed/moved functions have updated all callers
