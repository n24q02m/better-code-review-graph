# LLM-OPTIMIZED REFERENCE -- better-code-review-graph v0.1.0

Claude Code: Read ONLY the exact `<section>` you need. Never load the whole file.

<section name="usage">
Quick install: pip install better-code-review-graph
Then: better-code-review-graph install && better-code-review-graph build
First run: /better-code-review-graph:build-graph
After that use only delta/pr commands.
</section>

<section name="review-delta">
Always call get_impact_radius on changed files first.
Then get_review_context (depth=2).
Generate review using ONLY changed nodes + 2-hop neighbors.
Target: <800 tokens total context.
</section>

<section name="review-pr">
Fetch PR diff -> get_impact_radius -> get_review_context -> structured review with blast-radius table.
Never include full files unless explicitly asked.
</section>

<section name="commands">
MCP tools: build_or_update_graph_tool, get_impact_radius_tool, query_graph_tool, get_review_context_tool, semantic_search_nodes_tool, embed_graph_tool, list_graph_stats_tool, get_docs_section_tool, find_large_functions_tool
Skills: build-graph, review-delta, review-pr
CLI: better-code-review-graph [install|init|build|update|status|watch|serve]
</section>

<section name="legal">
MIT license. 100% local. No telemetry. DB file: .code-review-graph/graph.db
</section>

<section name="watch">
Run: better-code-review-graph watch (auto-updates graph on file save via watchdog)
Or use PostToolUse (Write|Edit|Bash) hooks for automatic background updates.
</section>

<section name="embeddings">
Dual-mode embedding (included by default, no extras needed):
- Local (default): qwen3-embed ONNX -- zero-config, 768-dim, ~570MB on first use
- Cloud: Set API_KEYS or LITELLM_PROXY_URL env var to use LiteLLM
- Explicit: EMBEDDING_BACKEND=local|litellm
Call embed_graph_tool to compute vectors.
semantic_search_nodes_tool auto-uses vectors when available, falls back to keyword.
Fixed 768-dim storage -- switching backend does NOT invalidate vectors.
</section>

<section name="search">
Multi-word search uses AND logic: "firebase auth" matches nodes containing BOTH words.
Configurable max_results parameter on impact radius and review context (default 50).
Qualified call resolution: same-file calls resolved to file.py::function_name format.
</section>

<section name="languages">
Supported: Python, TypeScript, JavaScript, Go, Rust, Java, C#, Ruby, Kotlin, Swift, PHP, C/C++
Parser: Tree-sitter via tree-sitter-language-pack
</section>

<section name="troubleshooting">
DB lock: SQLite WAL mode, auto-recovers. Only one build at a time.
Large repos: First build 30-60s. Incremental <2s. Add patterns to .code-review-graphignore.
Stale graph: Run /better-code-review-graph:build-graph manually.
Missing nodes: Check language support + ignore patterns. Use full_rebuild=True.
</section>

**Instruction to Claude Code (always follow):**
When user asks anything about "better-code-review-graph", "how to use", "commands", "review-delta", etc.:
1. Call get_docs_section_tool with the exact section name.
2. Use ONLY that content + current graph state.
3. Never include full docs or source code in your reasoning.
This guarantees 90%+ token savings.
