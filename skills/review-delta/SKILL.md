---
name: review-delta
description: Review uncommitted changes using impact analysis. Quick local delta review with blast-radius detection.
argument-hint: "[file or function name]"
---

# Review Delta

Perform a focused, token-efficient code review of uncommitted changes and their blast radius. Use this for quick local reviews BEFORE committing. For full branch/PR reviews, use review-pr instead.

**Token optimization:** Before starting, call `help(topic="graph")` for the full actions reference. Use ONLY changed nodes + 2-hop neighbors in context.

## Steps

1. **Ensure the graph is current** by calling `graph(action="update")`.

2. **Get review context** by calling `review()`. This returns:
   - Changed files (auto-detected from git diff)
   - Impacted nodes and files (blast radius)
   - Source code snippets for changed areas
   - Review guidance (test coverage gaps, wide impact warnings, inheritance concerns)

3. **Analyze the blast radius** by reviewing the `impacted_nodes` and `impacted_files` in the context. Focus on:
   - Functions whose callers changed (may need signature/behavior verification)
   - Classes with inheritance changes (Liskov substitution concerns)
   - Files with many dependents (high-risk changes)

4. **Perform the review** using the context. For each changed file:
   - Review the source snippet for correctness, style, and potential bugs
   - Check if impacted callers/dependents need updates
   - Verify test coverage using `query(action="query", pattern="tests_for", target=<function_name>)`
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
