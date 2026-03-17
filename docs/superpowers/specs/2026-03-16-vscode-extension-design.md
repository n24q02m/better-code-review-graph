# VS Code Extension for code-review-graph

**Date:** 2026-03-16
**Status:** Approved

## Overview

A full-featured VS Code extension that brings code-review-graph's knowledge graph into the IDE. Provides a tree view sidebar, interactive force-directed graph panel, on-demand blast-radius analysis, code navigation commands, SCM review integration, and guided onboarding for first-time users.

**Target audience:** General VS Code marketplace users (discovery-driven), with power features for existing code-review-graph users.

## Architecture

**TypeScript Extension + Subprocess Bridge.**

- Read operations (tree view, graph data, queries, search): TypeScript reads SQLite directly via `better-sqlite3`. No Python needed.
- Write operations (build, update, embed, review context): Spawns `code-review-graph` CLI as a child process.
- The SQLite schema (4 tables: `nodes`, `edges`, `metadata`, `embeddings`) is the contract between the Python backend and the TypeScript reader. The `embeddings` table stores vector blobs for semantic search and is optional (only present after `embed_graph` runs).
- No MCP protocol dependency. The extension is standalone from Claude Code.
- CLI output contract: The extension invokes CLI commands with a `--json` flag (to be added to the Python CLI) for structured output. Fallback: ignore CLI stdout and re-read the DB after command completion.

**Schema compatibility:**
- The extension reads `schema_version` from the `metadata` table (to be added to the Python backend) and warns if the DB was created by an incompatible version.
- The extension handles both legacy (`.code-review-graph.db` at repo root) and current (`.code-review-graph/graph.db`) DB locations, matching the Python backend's migration logic.

**Graceful degradation:**
- If `graph.db` exists but Python is not installed, all read features work (tree view, graph panel, navigation). Write commands show "Backend not found. [Install Now]".
- If `graph.db` does not exist, the welcome walkthrough guides the user through setup.
- VS Code for the Web is not supported (`better-sqlite3` requires native Node.js). The extension sets `"extensionKind": ["workspace"]` in `package.json`.

## Project Structure

```
code-review-graph-vscode/
├── package.json              # Extension manifest, commands, views, config
├── tsconfig.json
├── esbuild.mjs               # Build config: extension host + webview bundles
├── src/
│   ├── extension.ts          # Activation, command registration, lifecycle
│   ├── backend/
│   │   ├── sqlite.ts         # Read-only SQLite access via better-sqlite3
│   │   ├── cli.ts            # Subprocess wrapper for code-review-graph CLI
│   │   └── watcher.ts        # FileSystemWatcher for .db changes → refresh UI
│   ├── views/
│   │   ├── treeView.ts       # TreeDataProvider for sidebar
│   │   ├── treeItems.ts      # TreeItem types (file, class, function, test, edge)
│   │   └── graphPanel.ts     # WebviewPanel for D3.js force-directed graph
│   ├── features/
│   │   ├── blastRadius.ts    # On-demand blast radius command
│   │   ├── reviewAssistant.ts# SCM integration, review context
│   │   ├── navigation.ts     # Go-to-callers, go-to-tests, etc.
│   │   └── search.ts         # Command palette search across graph nodes
│   ├── onboarding/
│   │   ├── welcome.ts        # Welcome walkthrough webview
│   │   └── installer.ts      # Auto-detect & install code-review-graph
│   └── webview/
│       ├── graph.html         # D3.js graph template
│       ├── graph.ts           # Client-side graph logic (bundled separately)
│       └── styles.css         # Graph styles (respects VS Code theme)
├── media/
│   ├── icons/                 # Tree view icons (file, class, fn, test, edge types)
│   └── logo.png
├── test/
└── .vscodeignore
```

**Key dependencies:**
- `better-sqlite3` -- Direct SQLite reads (sub-millisecond). Distributed via platform-specific extension packages (`vsce package --target`). Prebuilt binaries for Windows x64, macOS arm64/x64, Linux x64.
- `d3` (bundled in webview) -- Force-directed graph rendering
- `esbuild` -- Bundles extension host code and webview code separately
- VS Code API (`vscode` namespace) -- TreeView, WebviewPanel, commands, SCM

**Activation events:**
- `workspaceContains:.code-review-graph/graph.db` -- activate when graph exists
- `onCommand:codeReviewGraph.*` -- activate on any extension command
- `onView:codeReviewGraph.*` -- activate when sidebar view is opened

## Sidebar Tree View

Lives in a dedicated activity bar icon. Three top-level sections:

### 1. Code Graph

Organized by file, expandable into classes/functions/types/tests. Each node shows its kind icon and name. Expanding a node shows relationships as children:

```
▸ auth.py                          (file)
  ▸ login()                        (function)
    → calls validate_token()       (call edge)
    → tested by test_login()       (test edge)
    ← called by AuthMiddleware     (reverse call)
  ▸ UserService                    (class)
    → inherits BaseService         (inheritance edge)
    → contains login(), logout()   (contains edges)
▸ routes.py
  ...
```

### 2. Blast Radius

Empty by default. Populates when the blast radius command runs. Shows changed nodes at top, impacted nodes below, grouped by file. Clears on dismiss.

### 3. Stats

Quick glance: total nodes, edges, languages, last updated, embeddings status.

### Tree Interactions

- **Click** node → jump to source (file:line)
- **Click** edge → jump to target node's source
- **Right-click** node → context menu: "Show Blast Radius", "Find Callers", "Find Tests", "Show in Graph"
- **"Show in Graph"** → highlights node in the webview graph panel
- **Filter input** at top of tree. Dropdown to filter by kind (Files, Classes, Functions, Tests).

## Graph Webview Panel

Opens as a VS Code editor tab. Uses D3.js force-directed layout in a webview.

### Toolbar

- Search input: filter and highlight matching nodes
- Edge-type toggles: CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON (clickable pills, all enabled by default except CONTAINS)
- Depth slider: control how many hops to show (default: 2)
- Stats: node count, edge count
- Fit button: auto-zoom to show all visible nodes
- Export: save as PNG or SVG

### Node Rendering

- Color-coded by type: Changed (red), Function (green), Class (yellow), Test (blue), File (purple)
- Changed nodes get a dashed pulsing ring indicator
- Each node shows name + file path
- Respects VS Code theme (dark/light/high-contrast)

### Interactions

- Click node → jump to source file
- Double-click node → center and expand neighbors
- Drag node → reposition
- Scroll → zoom in/out
- Click+drag background → pan
- Hover node → tooltip with parameters, line range, kind

### Bidirectional Sync

Selecting a node in the tree highlights it in the graph (centers + pulses). Clicking a node in the graph selects it in the tree (expands parents, scrolls into view).

## Commands

All features are on-demand via the Command Palette (`Ctrl+Shift+P`).

| Command | Keybinding | Description |
|---|---|---|
| `Code Graph: Show Blast Radius` | none | Blast radius for function/class at cursor. Populates tree + graph. |
| `Code Graph: Find Callers` | none | All functions calling the symbol at cursor |
| `Code Graph: Find Tests` | none | Tests covering the symbol at cursor |
| `Code Graph: Show Graph` | none | Open/focus the graph webview panel |
| `Code Graph: Search` | none | Fuzzy search across all graph nodes, quick-pick list |
| `Code Graph: Review Changes` | -- | Review context for staged/unstaged changes |
| `Code Graph: Build Graph` | -- | Full rebuild (CLI subprocess) |
| `Code Graph: Update Graph` | -- | Incremental update (CLI subprocess) |

## Automatic Behaviors

- **On workspace open:** Check for `.code-review-graph/graph.db`. If found, load tree view. If not, show welcome walkthrough.
- **On DB file change:** `FileSystemWatcher` monitors `graph.db`. On change, tree view and open graph panel refresh automatically.
- **Status bar item:** Shows `$(database) 1,234 nodes` when healthy, `$(warning) Graph outdated` when DB is stale (>1 hour). Click to run update.
- **Auto-update on save:** When `codeReviewGraph.autoUpdate` is enabled (default), runs `code-review-graph update` on file save with a 2-second debounce. If a user also has Claude Code hooks configured, they should set `codeReviewGraph.autoUpdate` to `false` to avoid double-updates.

## Review Assistant (SCM Integration)

- "Show Blast Radius" button in the SCM title bar when changed files are present
- File badges on the SCM file list:
  - `IMPACTED` (orange) -- files in the blast radius that aren't staged
  - `TESTED` (green) -- changed functions with test coverage
  - `UNTESTED` (red) -- changed functions without tests

## Onboarding

### Welcome Walkthrough (VS Code native walkthrough API)

**Step 1: Install Backend**
- Auto-detects available Python package managers: uv → pipx → pip
- One-click install button runs the best available installer
- Manual instructions expandable for users who prefer control
- Checks `python3 --version >= 3.10`

**Step 2: Build Your Graph**
- "Build Graph" button runs `code-review-graph build`
- Progress bar in notification area
- Completion message: "Built X nodes and Y edges across Z languages"

**Step 3: Explore**
- Opens the tree view sidebar
- Links to: "Show Graph Panel", "Try Blast Radius", "Keyboard Shortcuts"

### Graceful Degradation

- `graph.db` exists + no Python: all read features work, write commands show "[Install Now]" prompt
- No `graph.db` + no Python: welcome walkthrough opens
- No `graph.db` + Python available: walkthrough skips to "Build Your Graph"

## Extension Settings

```jsonc
{
  // Path to code-review-graph CLI (auto-detected if on PATH)
  "codeReviewGraph.cliPath": "",

  // Auto-update graph on file save (debounced 2s)
  "codeReviewGraph.autoUpdate": true,

  // Default blast radius depth
  "codeReviewGraph.blastRadiusDepth": 2,

  // Graph panel theme: "auto" (follows VS Code), "dark", "light"
  "codeReviewGraph.graphTheme": "auto",

  // Node types to show in tree view
  "codeReviewGraph.treeView.showFiles": true,
  "codeReviewGraph.treeView.showClasses": true,
  "codeReviewGraph.treeView.showFunctions": true,
  "codeReviewGraph.treeView.showTests": true,
  "codeReviewGraph.treeView.showTypes": true,

  // Edge types visible by default in graph panel
  "codeReviewGraph.graph.defaultEdges": ["CALLS", "IMPORTS_FROM", "INHERITS", "IMPLEMENTS", "TESTED_BY", "DEPENDS_ON"],

  // Max nodes to render in graph (performance guard)
  "codeReviewGraph.graph.maxNodes": 500
}
```

**Design decisions:**
- `graphTheme: "auto"` reads `workbench.colorTheme` kind and adapts node/edge colors
- `maxNodes: 500` prevents graph panel from choking on large repos. When exceeded, renders the subgraph around selected/changed nodes with a "Show more" button.
- Tree view uses lazy loading: file nodes load on activation, children (classes/functions/edges) load on expand. No full tree materialization.
- `autoUpdate` defaults to on. Users with Claude Code hooks should disable it to avoid double-updates.

## Cursor-to-Node Resolution

Commands like "Show Blast Radius" and "Find Callers" operate on the symbol at cursor. Resolution steps:

1. Get `file_path` and `cursor_line` from the active editor
2. Query `nodes` table: `SELECT * FROM nodes WHERE file_path = ? AND line_start <= ? AND line_end >= ? ORDER BY (line_end - line_start) ASC LIMIT 1` (innermost enclosing node)
3. Use the node's `qualified_name` for graph traversal
4. BFS traversal for blast radius runs in TypeScript over the SQLite data (no CLI needed for read-only graph traversal)

This is purely a read operation -- no Python dependency.

## Multi-Root Workspace Support

When multiple workspace folders are open, the extension:
- Discovers `graph.db` in each folder independently
- Tree view groups nodes under workspace folder headers
- Status bar shows aggregate counts or the active folder's counts
- Commands operate on the workspace folder of the active editor

## Error Handling

- **Corrupted DB:** If SQLite open fails, show notification with "Rebuild Graph" action
- **CLI timeout:** 60-second timeout on subprocess calls. On timeout, show "Build taking longer than expected" with option to cancel
- **Schema mismatch:** Check `schema_version` in `metadata` table. If missing or too old, prompt "Graph was built with an older version. [Rebuild]"
- **DB locked:** Retry reads up to 3 times with 100ms backoff (handles concurrent CLI updates)

## Testing Strategy

- **Unit tests:** SQLite reader, CLI wrapper, cursor-to-node resolution (standard Jest/Mocha)
- **Integration tests:** Tree view population, command execution (`@vscode/test-electron`)
- **Webview:** Manual testing + screenshot regression (D3.js in webview is not unit-testable)
- Test infrastructure established in Phase 1

## Phased Delivery

### Phase 1 -- Foundation (v0.1)

- Extension scaffold, `package.json` manifest, build pipeline
- SQLite reader (`better-sqlite3`)
- Tree view sidebar with file/class/function/test nodes and relationship edges
- Click-to-navigate (jump to source)
- Status bar item with node count
- Welcome walkthrough + one-click install
- `Build Graph` and `Update Graph` commands (CLI subprocess)

### Phase 2 -- Graph Panel (v0.2)

- D3.js webview panel with force-directed layout
- Toolbar: search, edge-type toggles, depth slider
- Node interactions: click, drag, hover tooltip, double-click expand
- Bidirectional sync: tree selection ↔ graph highlight
- Export as PNG/SVG

### Phase 3 -- Blast Radius & Navigation (v0.3)

- `Show Blast Radius` command (cursor-aware)
- `Find Callers`, `Find Tests` commands
- `Search` command with fuzzy quick-pick
- Blast radius section in tree view
- FileSystemWatcher for auto-refresh on DB changes

### Phase 4 -- Review Assistant & Polish (v1.0)

- SCM integration: blast radius button, file badges (IMPACTED/TESTED/UNTESTED)
- Review context panel for staged changes
- Auto-update on file save (debounced)
- Theme-aware graph colors (dark/light/high-contrast)
- `maxNodes` performance guard
- Marketplace listing: icon, screenshots, README, demo GIF
