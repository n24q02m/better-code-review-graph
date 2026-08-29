---
name: impact-audit
description: Blast radius of a change you have not made yet -- traces a symbol across federated repositories, splits impact per repo, and reports what must ship together.
argument-hint: "<symbol, file, or described change> [additional repo paths]"
---

# Impact Audit

Scope a **planned** change before writing it. Answers "if I change this, what else has to change, and in which repositories" -- across a federation of repositories, not just the one you have open.

Run this while the change is still a proposal. Once code is written, `review-delta` and `review-pr` review what actually changed.

**Command surface:** run the local CLI through the coding harness shell. Examples
use the installed `better-code-review-graph` command; from a source checkout,
prefix it with `uv run`. No MCP mapping is required. Use
`better-code-review-graph query --help` for the actions reference.

## Steps

1. **State the change under audit in one line** before querying anything -- for example "add a required `tenant_id` parameter to `create_session`". The audit is only meaningful against a specific proposed edit, because the risky part differs: adding a required parameter breaks callers, changing a return type breaks consumers, renaming breaks both plus anything resolving the name dynamically.

2. **Make sure every repository that could be affected is in the graph.** A blast radius is only as wide as the graph:
   - `better-code-review-graph graph stats --repo-root "<path-a>"` -- confirm the graph exists and note `files_count`.
   - `better-code-review-graph graph build --full-rebuild --repo-root "<path-a>" --roots "<path-b>"` -- federate the additional repositories into the same graph. Each root is registered and its files tagged with a `repo_id`.
   - Without federation, a cross-repo audit will report a clean radius simply because the consumers were never indexed. Say so in the report rather than implying the change is contained.

3. **Locate every definition of the symbol** with `better-code-review-graph query search --search-query "<name>" --repo-root "<path-a>"`, leaving `--repo` unset so the search spans all federated repositories. Two repositories may define the same name for unrelated purposes -- resolve which definition is actually the target before tracing, and note any same-named decoys so a later reader does not re-open the question.

4. **Map direct consumers**, unscoped across the federation:
   - `better-code-review-graph query query --pattern callers_of --target "<name>" --repo-root "<path-a>"` -- who calls it
   - `better-code-review-graph query query --pattern importers_of --target "<file_path>" --repo-root "<path-a>"` -- which files import the module
   - use `--pattern inheritors_of` and `--pattern children_of` when the target is a class -- subclasses inherit the change whether or not they call it

5. **Measure the full radius** with `better-code-review-graph query impact --changed-files "<file>" --max-depth 2 --repo-root "<path-a>"`. Raise `--max-depth` to 3 when step 4 shows the direct consumers are themselves widely used; leave it at 2 otherwise, since depth costs tokens and the tail is mostly noise.

6. **Split the radius per repository.** Re-run the impact command with `--repo "<repo_id>"` for each federated repository. The per-repo split is the deliverable: it converts "47 impacted files" into "3 repositories, one of which is published and consumed elsewhere", which is what determines release ordering.

7. **Call out the boundaries the graph cannot cross.** Call and import edges are resolved per language (Python, TypeScript, Go, Java, Rust, plus a generic fallback). Edges do **not** exist for:
   - calls that cross a network boundary (HTTP route, RPC, queue message)
   - dynamic dispatch by string name, reflection, or plugin registries
   - generated clients and schema-derived code, unless the generated files are indexed

   These are exactly the places a cross-repo change breaks silently. List them as unverified rather than reporting a radius that looks complete.

8. **Check the radius is tested** with `better-code-review-graph query query --pattern tests_for --target "<name>" --repo-root "<path-a>"` for the target and its direct consumers. An impacted call site with no test is a site that will not tell you when the change is wrong.

9. **Report**:

    ```
    ## Impact Audit: <change in one line>

    ### Target
    - **Symbol**: <name> (<file>:<line>)
    - **Kind**: function / class / method / module
    - **Also defined as**: <same-named decoys, or none>

    ### Radius by Repository
    | Repository | Impacted files | Impacted symbols | Tested | Notes |
    |---|---|---|---|---|
    | <repo_id> | N | M | K/M | <published? consumed elsewhere?> |

    ### Direct Consumers Requiring Edits
    - `<caller>` (<repo>/<file>:<line>) -- <what breaks>

    ### Unverified Boundaries
    - <HTTP route / dynamic dispatch / generated client the graph cannot trace>

    ### Verdict: CONTAINED / MULTI-REPO / CROSS-BOUNDARY

    **CONTAINED** -- one repository, no published surface. Make the change directly.

    **MULTI-REPO** -- more than one repository impacted. Ship in dependency order:
    1. <repo> -- <change, released first>
    2. <repo> -- <consume the new version>
    Add a compatibility window if the repositories cannot release together.

    **CROSS-BOUNDARY** -- impact crosses a network, dynamic, or generated boundary
    the graph cannot verify. Enumerate consumers by other means before proceeding.

    ### Recommended Sequence
    1. <step>
    ```

## Verdict Criteria

| Condition | Verdict |
|---|---|
| Single repository, no published or exported surface | CONTAINED |
| More than one federated repository impacted | MULTI-REPO |
| Consumers reached only via HTTP/RPC/queue, reflection, or generated code | CROSS-BOUNDARY |
| Any consumer repository not indexed in the graph | CROSS-BOUNDARY (radius is unproven) |

## Difference from refactor-check

| Aspect | refactor-check | impact-audit |
|---|---|---|
| Question | Is changing this symbol safe here? | What else must change, and where? |
| Scope | One repository | Federated repositories |
| Output | Safety verdict plus mitigation | Per-repo radius plus release ordering |
| Timing | Immediately before editing | While the change is still a proposal |

## When to Use

- Before changing a signature, return type, or name in shared or published code
- Before removing or renaming anything exported from a library consumed elsewhere
- When estimating the cost of a change across services during planning
- Before a migration that touches a data model or contract used by several repositories
