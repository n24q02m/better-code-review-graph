#!/bin/bash
# Checks for the better-code-review-graph knowledge graph and outputs
# guidance for Claude Code at the start of every session.

DB_PATH=".code-review-graph/graph.db"

if [ -f "$DB_PATH" ]; then
    cat <<'INSTRUCTIONS'
[better-code-review-graph] Knowledge graph is available.

When answering questions about this codebase, prefer using the better-code-review-graph MCP tools before scanning files manually:
- Use the query tool with action="search" (search_query=...) to find classes, functions, or types by name or keyword (semantic search).
- Use the query tool with action="query" and a pattern like callers_of, callees_of, imports_of, importers_of, children_of, tests_for, inheritors_of, or file_summary (with target=...) to explore relationships.
- Use the query tool with action="impact" (changed_files=... or base=...) to understand the blast radius of changes.
- Use the review tool with action="context" for token-efficient review context.
- Fall back to Grep/Glob/Read only when the graph does not cover what you need.

This saves significant tokens by avoiding full codebase scans.
INSTRUCTIONS
else
    echo "[better-code-review-graph] No knowledge graph found. Use the graph tool with action='build' to parse this codebase and enable graph-powered queries."
fi
