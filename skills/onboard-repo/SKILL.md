---
name: onboard-repo
description: Index an unfamiliar codebase into the knowledge graph, then produce a first orientation map -- entry points, most-depended-upon modules, hotspots, test topology.
argument-hint: "[repo path] [area of interest]"
---

# Onboard Repo

Take a codebase you have never seen and turn it into a queryable graph, then read the graph to produce an orientation map. Use this on first contact with a repository, before answering questions about it or changing anything in it.

**Scope:** this skill builds and reads a knowledge graph. It does not modify source files, CI configuration, or project conventions. The only files it creates are the graph database under `.code-review-graph/` (already self-ignored) and, when you choose to add one, a `.code-review-graphignore`.

**Command surface:** run the local CLI through the coding harness shell. Examples
use the installed `better-code-review-graph` command; from a source checkout,
prefix it with `uv run`. No MCP mapping is required.

## Steps

1. **Check what already exists** with `better-code-review-graph graph stats --repo-root "<path>"`. A non-empty graph can go directly to step 5; a missing-graph error means continue with a build.

2. **Decide the indexing scope before building**:
   - Single repository: pass only `--repo-root "<path>"`.
   - A repository that vendors or embeds others: add a `.code-review-graphignore` at the repo root (one `fnmatch` pattern per line, `#` for comments) so vendored trees, build output, and fixtures do not inflate the graph. Common additions: `vendor/*`, `third_party/*`, `**/generated/*`, `**/*.min.js`.
   - Several sibling repositories that call each other: federate them in one graph with `--roots` in step 3, then use `impact-audit` for cross-repo questions.

3. **Build the graph** with `better-code-review-graph graph build --full-rebuild --repo-root "<path>"`.
   - For a federated build: `better-code-review-graph graph build --full-rebuild --repo-root "<path-a>" --roots "<path-b>"`. Each root is registered in the repo registry and its files are tagged with a `repo_id`, which later lets you scope any query with `--repo "<repo_id>"`.
   - Parsing is Tree-sitter based and needs no language servers, toolchains, or compilation -- an unbuildable checkout still indexes.

4. **Enable semantic search** with `better-code-review-graph graph embed --repo-root "<path>"`. Without embeddings, the CLI's search action falls back to name and keyword matching, which will miss "where is authentication handled" style questions.
   - The default backend is local and requires no credentials. The graph-stats result reports the resolved backend and embedding count.
   - If a cloud embedding chain is expected but stats show local, inspect the local environment/configuration rather than assuming the model list is wrong.
   - Optional: `better-code-review-graph graph summarize --repo-root "<path>"` adds generated summaries for function nodes, but only when a summarizer model chain is configured. It is a no-op otherwise -- do not report it as a failure.

5. **Read the shape of the codebase** with `better-code-review-graph graph stats --repo-root "<path>"`. Record the language mix, file count, and node/edge counts. The language mix decides which conventions to expect in later steps -- do not assume the dominant language from the repository name.

6. **Locate the entry points**. Use `better-code-review-graph query search --search-query "<term>" --repo-root "<path>"` with terms that suit the language mix -- `main`, `cli`, `handler`, `route`, `server`, `worker`, `command`. Then confirm each candidate is genuinely an entry point by checking it has few or no callers:
   - `better-code-review-graph query query --pattern callers_of --target "<name>" --repo-root "<path>"` -- an entry point is typically called by nothing inside the repo.

7. **Find the load-bearing modules** -- the files everything else depends on:
   - use `better-code-review-graph query query --pattern importers_of --target "<file_path>" --repo-root "<path>"` for candidate core files; the ones with the most importers are where a newcomer should start reading.
   - use `better-code-review-graph query query --pattern file_summary --target "<file_path>" --repo-root "<path>"` for a structural digest of a file without reading it in full.

8. **Trace one representative flow end to end.** Pick a single entry point from step 6 and walk outward with `better-code-review-graph query query --pattern callees_of --target "<name>" --repo-root "<path>"`, two or three hops deep. One traced flow teaches the layering faster than reading ten files.

9. **Check the test topology**:
   - run `better-code-review-graph query query --pattern tests_for --target "<name>" --repo-root "<path>"` on the core modules from step 7.
   - Modules with many importers and no tests are the risky parts of the codebase, and worth stating explicitly in the report.

10. **Report the orientation map**:

    ```
    ## Codebase Orientation: <repo>

    ### Graph
    - **Nodes / edges**: N / M across K files
    - **Languages**: <language: file count, ...>
    - **Semantic search**: enabled (<backend>) / name-matching only

    ### Entry Points
    - `<name>` (<file>:<line>) -- <what starts here>

    ### Core Modules (most depended upon)
    | Module | Importers | Tested |
    |---|---|---|
    | <file> | N | yes / no |

    ### Traced Flow: <entry point>
    <entry> -> <callee> -> <callee> -- <one line on what the layering implies>

    ### Hotspots
    - <file or function> -- <many dependents / oversized / untested>

    ### Suggested Reading Order
    1. <file> -- <why first>
    2. <file> -- <why next>

    ### Open Questions
    - <what the graph could not answer and where to look instead>
    ```

## Interpreting the Result

| Observation | What it means |
|---|---|
| Many nodes, few edges | Mostly leaf code, or a language whose call edges resolve poorly -- lean on `search` over `callers_of` |
| A file with very high importer count | Core abstraction; changes there need `impact-audit` before editing |
| Entry point with no `tests_for` result | Integration behaviour is unverified; treat changes as high risk |
| `languages` shows a language you did not expect | Generated or vendored code is likely in scope; add it to `.code-review-graphignore` and rebuild |

## When to Use

- First time working in a repository, before answering questions about it
- Taking over an unfamiliar service or an abandoned codebase
- After cloning a repository whose structure is not documented
- Before planning a change in a codebase whose layering you cannot yet describe

## Related Skills

- `impact-audit` -- once oriented, to scope a planned change across repositories
- `refactor-check` -- safety verdict for changing one specific symbol
- `security-sweep` -- risk-ranked security posture of the newly indexed code
