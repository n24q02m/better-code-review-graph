---
name: onboard-repo
description: Index an unfamiliar codebase into the knowledge graph, then produce a first orientation map -- entry points, most-depended-upon modules, hotspots, test topology.
argument-hint: "[repo path] [area of interest]"
---

# Onboard Repo

Take a codebase you have never seen and turn it into a queryable graph, then read the graph to produce an orientation map. Use this on first contact with a repository, before answering questions about it or changing anything in it.

**Scope:** this skill builds and reads a knowledge graph. It does not modify source files, CI configuration, or project conventions. The only files it creates are the graph database under `.code-review-graph/` (already self-ignored) and, when you choose to add one, a `.code-review-graphignore`.

## Steps

1. **Check what already exists** by calling `config(action="status")`. It returns `graph_path`, `total_nodes`, `total_edges`, `files_count`, `languages`, `embedding_backend`, `embeddings_count`, and `last_updated`.
   - `total_nodes > 0` means a graph is already built -- skip to step 5 instead of rebuilding.
   - `graph_path: null` or a missing status means no graph yet -- continue.

2. **Decide the indexing scope before building**:
   - Single repository: no extra arguments needed.
   - A repository that vendors or embeds others: add a `.code-review-graphignore` at the repo root (one `fnmatch` pattern per line, `#` for comments) so vendored trees, build output, and fixtures do not inflate the graph. Common additions: `vendor/*`, `third_party/*`, `**/generated/*`, `**/*.min.js`.
   - Several sibling repositories that call each other: federate them in one graph with the `roots` argument in step 3, then use `impact-audit` for cross-repo questions.

3. **Build the graph** by calling `graph(action="build")`.
   - For a federated build: `graph(action="build", roots=["<path-a>", "<path-b>"])`. Each root is registered in the repo registry and its files are tagged with a `repo_id`, which later lets you scope any query with `repo="<repo_id>"`.
   - Parsing is Tree-sitter based and needs no language servers, toolchains, or compilation -- an unbuildable checkout still indexes.

4. **Enable semantic search** by calling `graph(action="embed")`. Without embeddings, `query(action="search")` falls back to name and keyword matching, which will miss "where is authentication handled" style questions.
   - The default backend is local and requires no credentials. `config(action="status")` reports which backend resolved under `embedding_backend`.
   - If a cloud embedding chain is expected but `embedding_backend` shows local, check `config(action="setup_status")` before assuming the model list is wrong.
   - Optional: `graph(action="summarize")` adds generated summaries for function nodes, but only when a summarizer model chain is configured. It is a no-op otherwise -- do not report it as a failure.

5. **Read the shape of the codebase** by calling `graph(action="stats")`. Record the language mix, file count, and node/edge counts. The language mix decides which conventions to expect in later steps -- do not assume the dominant language from the repository name.

6. **Locate the entry points**. Use `query(action="search", search_query=...)` with terms that suit the language mix -- `main`, `cli`, `handler`, `route`, `server`, `worker`, `command`. Then confirm each candidate is genuinely an entry point by checking it has few or no callers:
   - `query(action="query", pattern="callers_of", target="<name>")` -- an entry point is typically called by nothing inside the repo.

7. **Find the load-bearing modules** -- the files everything else depends on:
   - `query(action="query", pattern="importers_of", target="<file_path>")` for candidate core files; the ones with the most importers are where a newcomer should start reading.
   - `query(action="query", pattern="file_summary", target="<file_path>")` for a structural digest of a file without reading it in full.

8. **Trace one representative flow end to end.** Pick a single entry point from step 6 and walk outward with `query(action="query", pattern="callees_of", target="<name>")`, two or three hops deep. One traced flow teaches the layering faster than reading ten files.

9. **Check the test topology**:
   - `query(action="query", pattern="tests_for", target="<name>")` on the core modules from step 7.
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
