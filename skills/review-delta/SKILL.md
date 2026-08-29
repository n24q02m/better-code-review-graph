---
name: review-delta
description: Review uncommitted changes using impact analysis. Quick local delta review with blast-radius detection.
argument-hint: "[file or function name]"
---

# Review Delta

Perform a focused, token-efficient code review of uncommitted changes and their blast radius. Use this for quick local reviews BEFORE committing. For full branch/PR reviews, use review-pr instead.

**Command surface:** run the local CLI through the coding harness shell. Examples
use the installed `better-code-review-graph` command; from a source checkout,
prefix it with `uv run`. No MCP mapping is required. Use
`better-code-review-graph review --help` for the command reference.

## Steps

1. **Ensure the graph is current** with `better-code-review-graph graph build --base HEAD --repo-root "<path>"`.

2. **Get review context** with `better-code-review-graph review context --base HEAD --repo-root "<path>"`. This returns:
   - Changed files (auto-detected from git diff)
   - Impacted nodes and files (blast radius)
   - Source code snippets for changed areas
   - Review guidance (test coverage gaps, wide impact warnings, inheritance concerns)

3. **Analyze the blast radius** by reviewing the `impacted_nodes` and `impacted_files` in the JSON result. Focus on:
   - Functions whose callers changed (may need signature/behavior verification)
   - Classes with inheritance changes (Liskov substitution concerns)
   - Files with many dependents (high-risk changes)

4. **Perform the review** using the context. For each changed file:
   - Review the source snippet for correctness, style, and potential bugs
   - Check if impacted callers/dependents need updates
   - Verify test coverage with `better-code-review-graph query query --pattern tests_for --target "<function>" --repo-root "<path>"`
   - Flag any untested changed functions

5. **Report findings** in a structured format:

   ```
   ## Delta Review

   ### Summary
   <One-line overview of the changes>

   ### Risk Level
   - **Low**: Test-only changes, documentation, config files
   - **Medium**: Implementation changes with <5 impacted files, no public API changes
   - **High**: >5 impacted files OR public API signature/behavior change

   ### Issues Found
   - <Bugs, style issues, missing tests>

   ### Blast Radius
   - <List of impacted files/functions>

   ### Recommendations
   1. <Actionable suggestion>
   ```

## Risk Level Escalation Rules

- **High** if any of: >5 impacted files, public API signature change, public API behavior change, breaking change in exported symbols
- **Low** if all of: only test files changed, only documentation/comments changed, only config/CI files changed
- **Medium**: everything else

## Advantages Over Full-Repo Review

- Only sends changed + impacted code to the model (5-10x fewer tokens)
- Automatically identifies blast radius without manual file searching
- Provides structural context (who calls what, inheritance chains)
- Flags untested functions automatically
