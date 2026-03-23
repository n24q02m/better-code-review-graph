---
name: refactor-check
description: Safety analysis before refactoring -- dependency graph, test coverage, public API exposure, blast radius verdict.
argument-hint: "<function or class name> [intended change]"
---

# Refactor Check

Analyze whether a refactoring is safe BEFORE making changes. Produces a verdict with specific risks and mitigation steps.

## Steps

1. **Get the full dependency graph** for the target:
   - `graph(action="update")` to ensure graph is current
   - `query(action="query", pattern="callers_of", target="<name>")` -- who calls this
   - `query(action="query", pattern="callees_of", target="<name>")` -- what this calls
   - `query(action="query", pattern="imports_of", target="<name>")` -- what this imports
   - If it is a class: `query(action="query", pattern="inheritors_of", target="<name>")` and `query(action="query", pattern="children_of", target="<name>")`

2. **Identify test coverage**:
   - `query(action="query", pattern="tests_for", target="<name>")` -- direct tests
   - For each caller, also check `tests_for` to see if callers have integration tests covering this function indirectly
   - Record: number of direct tests, number of callers with tests, number of callers without tests

3. **Flag public API exposure**:
   - Check if the target is exported from a package `__init__.py`, `index.ts`, or similar
   - Check if the target is referenced from outside its own module/package
   - Check if the target appears in documentation or type stubs
   - Public API = any function/class importable by external consumers

4. **Estimate blast radius**:
   - `query(action="impact", target="<name>")` -- full impact analysis
   - Count: total impacted files, total impacted functions, depth of dependency chain
   - Identify any impacted files outside the immediate package/module

5. **Produce verdict**:

   ```
   ## Refactor Safety: <name>

   ### Target
   - **Location**: <file_path>:<line>
   - **Type**: function / class / method
   - **Public API**: Yes / No

   ### Dependency Summary
   - **Callers**: N functions depend on this
   - **Callees**: Calls M other functions
   - **Inheritance**: N subclasses (if class)

   ### Test Coverage
   - **Direct tests**: N tests
   - **Caller tests**: M/K callers have tests covering this path
   - **Coverage gaps**: <list uncovered callers>

   ### Blast Radius
   - **Impacted files**: N
   - **Impacted functions**: M
   - **Max depth**: K hops

   ### Verdict: SAFE / NEEDS MIGRATION / DANGEROUS

   **SAFE** -- Low blast radius (<5 files), good test coverage, no public API exposure.
   Make the change, run tests, done.

   **NEEDS MIGRATION** -- Public API or moderate blast radius (5-15 files).
   Recommended approach:
   1. Create new version alongside old
   2. Migrate callers incrementally
   3. Deprecate old version
   4. Remove after all callers migrated

   **DANGEROUS** -- High blast radius (>15 files), poor test coverage, or public API with external consumers.
   Specific risks:
   - <risk 1 with affected files>
   - <risk 2 with affected files>
   Mitigation: <steps to reduce risk before proceeding>
   ```

## Verdict Criteria

| Condition | Verdict |
|---|---|
| <5 impacted files, not public API, >80% caller test coverage | SAFE |
| 5-15 impacted files OR public API with known consumers | NEEDS MIGRATION |
| >15 impacted files OR public API with unknown consumers OR <50% test coverage | DANGEROUS |
| Any external package/library depends on it | DANGEROUS |

## When to Use

- Before renaming a function, class, or method
- Before changing a function signature (parameters, return type)
- Before moving code to a different module/package
- Before splitting a class or merging functions
- Before deleting code that might still be referenced
