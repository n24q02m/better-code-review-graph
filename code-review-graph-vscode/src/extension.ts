import * as vscode from "vscode";
import * as path from "node:path";
import * as fs from "node:fs";

import { SqliteReader } from "./backend/sqlite";
import type { GraphNode } from "./backend/sqlite";
import { CliWrapper } from "./backend/cli";
import {
  CodeGraphTreeProvider,
  BlastRadiusTreeProvider,
  StatsTreeProvider,
} from "./views/treeView";
import { GraphWebviewPanel } from "./views/graphWebview";
import { Installer } from "./onboarding/installer";
import { registerWalkthroughCommands, showWelcomeIfNeeded } from "./onboarding/welcome";
import { StatusBar } from "./views/statusBar";

let sqliteReader: SqliteReader | undefined;
let autoUpdateTimer: ReturnType<typeof setTimeout> | undefined;

/**
 * Locate the graph database file in the workspace.
 * Checks `.code-review-graph/graph.db` first, then falls back to `.code-review-graph.db`.
 */
function findGraphDb(workspaceRoot: string): string | undefined {
  const primary = path.join(workspaceRoot, ".code-review-graph", "graph.db");
  if (fs.existsSync(primary)) {
    return primary;
  }

  const fallback = path.join(workspaceRoot, ".code-review-graph.db");
  if (fs.existsSync(fallback)) {
    return fallback;
  }

  return undefined;
}

/**
 * Get the workspace root folder path, or undefined if no workspace is open.
 */
function getWorkspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}


/**
 * Navigate to a node's source file location.
 */
async function navigateToNode(node: GraphNode): Promise<void> {
  const workspaceRoot = getWorkspaceRoot();
  const filePath = workspaceRoot
    ? path.join(workspaceRoot, node.filePath)
    : node.filePath;

  const doc = await vscode.workspace.openTextDocument(filePath);
  const line = Math.max(0, (node.lineStart ?? 1) - 1);
  await vscode.window.showTextDocument(doc, {
    selection: new vscode.Range(line, 0, line, 0),
  });
}

/**
 * Register all extension commands.
 */
function registerCommands(
  context: vscode.ExtensionContext,
  cli: CliWrapper
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewGraph.buildGraph",
      async () => {
        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot) {
          vscode.window.showErrorMessage("No workspace folder is open.");
          return;
        }

        const result = await cli.buildGraph(workspaceRoot);
        if (result.success) {
          await reinitialize(context);
          vscode.window.showInformationMessage("Code Graph: Build complete.");
        } else {
          vscode.window.showErrorMessage(
            `Code Graph: Build failed. ${result.stderr}`
          );
        }
      }
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewGraph.updateGraph",
      async () => {
        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot) {
          vscode.window.showErrorMessage("No workspace folder is open.");
          return;
        }

        await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: "Code Graph: Updating graph...",
            cancellable: false,
          },
          async () => {
            const result = await cli.updateGraph(workspaceRoot);
            if (!result.success) {
              vscode.window.showErrorMessage(
                `Code Graph: Update failed. ${result.stderr}`
              );
            }
          }
        );
      }
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewGraph.showBlastRadius",
      async (qualifiedNameOrUri?: string | vscode.Uri) => {
        if (!sqliteReader) {
          vscode.window.showWarningMessage(
            "Code Graph: No graph database loaded."
          );
          return;
        }

        let qualifiedName: string | undefined;
        if (typeof qualifiedNameOrUri === "string") {
          qualifiedName = qualifiedNameOrUri;
        } else {
          qualifiedName = await vscode.window.showInputBox({
            prompt:
              "Enter the qualified name (e.g., my_module.MyClass.my_method)",
            placeHolder: "my_module.my_function",
          });
        }

        if (!qualifiedName) {
          return;
        }

        // Find the file for this node and compute impact radius
        const node = sqliteReader.getNode(qualifiedName);
        if (!node) {
          vscode.window.showInformationMessage(
            `Code Graph: Node "${qualifiedName}" not found.`
          );
          return;
        }

        const config = vscode.workspace.getConfiguration("codeReviewGraph");
        const depth = config.get<number>("blastRadiusDepth", 2);
        const impact = sqliteReader.getImpactRadius([node.filePath], depth);

        if (impact.impactedNodes.length === 0) {
          vscode.window.showInformationMessage(
            `Code Graph: No blast radius found for "${qualifiedName}".`
          );
          return;
        }

        await vscode.commands.executeCommand(
          "codeReviewGraph.blastRadius.focus"
        );
      }
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewGraph.findCallers",
      async (qualifiedName?: string) => {
        if (!sqliteReader) {
          vscode.window.showWarningMessage(
            "Code Graph: No graph database loaded."
          );
          return;
        }

        if (!qualifiedName) {
          qualifiedName = await vscode.window.showInputBox({
            prompt: "Enter the qualified name to find callers for",
            placeHolder: "my_module.my_function",
          });
        }

        if (!qualifiedName) {
          return;
        }

        const edges = sqliteReader.getEdgesByTarget(qualifiedName);
        const callerEdges = edges.filter((e) => e.kind === "CALLS");

        if (callerEdges.length === 0) {
          vscode.window.showInformationMessage(
            `Code Graph: No callers found for "${qualifiedName}".`
          );
          return;
        }

        const items = callerEdges.map((e) => {
          const callerNode = sqliteReader!.getNode(e.sourceQualified);
          return {
            label: callerNode?.name ?? e.sourceQualified,
            description: callerNode?.filePath ?? e.filePath,
            detail: `Line ${callerNode?.lineStart ?? e.line}`,
            node: callerNode,
            edge: e,
          };
        });

        const selected = await vscode.window.showQuickPick(items, {
          placeHolder: `Callers of ${qualifiedName}`,
        });

        if (selected?.node) {
          await navigateToNode(selected.node);
        }
      }
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewGraph.findTests",
      async (qualifiedName?: string) => {
        if (!sqliteReader) {
          vscode.window.showWarningMessage(
            "Code Graph: No graph database loaded."
          );
          return;
        }

        if (!qualifiedName) {
          qualifiedName = await vscode.window.showInputBox({
            prompt: "Enter the qualified name to find tests for",
            placeHolder: "my_module.my_function",
          });
        }

        if (!qualifiedName) {
          return;
        }

        // Find tests via TESTED_BY edges
        const edges = sqliteReader.getEdgesByTarget(qualifiedName);
        const testEdges = edges.filter((e) => e.kind === "TESTED_BY");

        // Also check reverse: source is the node, target is the test
        const outEdges = sqliteReader.getEdgesBySource(qualifiedName);
        const outTestEdges = outEdges.filter((e) => e.kind === "TESTED_BY");

        const allTestQualifiedNames = new Set([
          ...testEdges.map((e) => e.sourceQualified),
          ...outTestEdges.map((e) => e.targetQualified),
        ]);

        if (allTestQualifiedNames.size === 0) {
          vscode.window.showInformationMessage(
            `Code Graph: No tests found for "${qualifiedName}".`
          );
          return;
        }

        const items: Array<{
          label: string;
          description: string;
          detail: string;
          node: GraphNode | undefined;
        }> = [];

        for (const tqn of allTestQualifiedNames) {
          const testNode = sqliteReader.getNode(tqn);
          items.push({
            label: testNode?.name ?? tqn,
            description: testNode?.filePath ?? "",
            detail: `Line ${testNode?.lineStart ?? "?"}`,
            node: testNode,
          });
        }

        const selected = await vscode.window.showQuickPick(items, {
          placeHolder: `Tests for ${qualifiedName}`,
        });

        if (selected?.node) {
          await navigateToNode(selected.node);
        }
      }
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("codeReviewGraph.showGraph", async () => {
      if (!sqliteReader) {
        vscode.window.showWarningMessage(
          "Code Graph: No graph database loaded. Run 'Code Graph: Build Graph' first."
        );
        return;
      }

      GraphWebviewPanel.createOrShow(context.extensionUri, sqliteReader);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("codeReviewGraph.search", async () => {
      if (!sqliteReader) {
        vscode.window.showWarningMessage(
          "Code Graph: No graph database loaded."
        );
        return;
      }

      const query = await vscode.window.showInputBox({
        prompt: "Search the code graph",
        placeHolder: "Enter a function, class, or module name",
      });

      if (!query) {
        return;
      }

      const results = sqliteReader.searchNodes(query);

      if (results.length === 0) {
        vscode.window.showInformationMessage(
          `Code Graph: No results found for "${query}".`
        );
        return;
      }

      const items = results.map((r) => ({
        label: r.name,
        description: r.kind,
        detail: r.filePath
          ? `${r.filePath}:${r.lineStart ?? ""}`
          : undefined,
        result: r,
      }));

      const selected = await vscode.window.showQuickPick(items, {
        placeHolder: `Results for "${query}"`,
      });

      if (selected?.result) {
        await navigateToNode(selected.result);
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codeReviewGraph.reviewChanges",
      async () => {
        if (!sqliteReader) {
          vscode.window.showWarningMessage(
            "Code Graph: No graph database loaded."
          );
          return;
        }

        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot) {
          vscode.window.showErrorMessage("No workspace folder is open.");
          return;
        }

        await vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: "Code Graph: Analyzing changes...",
            cancellable: false,
          },
          async () => {
            const { execFile } = await import("node:child_process");
            const { promisify } = await import("node:util");
            const execFileAsync = promisify(execFile);

            let changedFiles: string[] = [];
            try {
              const { stdout } = await execFileAsync(
                "git",
                ["diff", "--name-only", "HEAD"],
                { cwd: workspaceRoot }
              );
              changedFiles = stdout
                .trim()
                .split("\n")
                .filter((line) => line.length > 0);
            } catch {
              // git not available or not a git repo
            }

            if (changedFiles.length === 0) {
              vscode.window.showInformationMessage(
                "Code Graph: No changes detected."
              );
              return;
            }

            const impact = sqliteReader!.getImpactRadius(changedFiles);
            GraphWebviewPanel.createOrShow(
              context.extensionUri,
              sqliteReader!,
              impact
            );
          }
        );
      }
    )
  );
}

/**
 * Reinitialize the reader and tree providers after a graph rebuild.
 */
async function reinitialize(
  context: vscode.ExtensionContext
): Promise<void> {
  const workspaceRoot = getWorkspaceRoot();
  if (!workspaceRoot) {
    return;
  }

  const dbPath = findGraphDb(workspaceRoot);
  if (!dbPath) {
    return;
  }

  sqliteReader?.close();
  sqliteReader = new SqliteReader(dbPath);

  // Refresh tree views
  await vscode.commands.executeCommand(
    "codeReviewGraph.codeGraph.refresh"
  );
}

/**
 * Set up a FileSystemWatcher to detect changes to the graph database.
 */
function watchGraphDb(context: vscode.ExtensionContext): void {
  const watcher = vscode.workspace.createFileSystemWatcher(
    "**/.code-review-graph/graph.db"
  );

  const dbPathRef = { current: "" };
  const workspaceRoot = getWorkspaceRoot();
  if (workspaceRoot) {
    const dbPath = findGraphDb(workspaceRoot);
    if (dbPath) {
      dbPathRef.current = dbPath;
    }
  }

  watcher.onDidChange(() => {
    // Close and reopen to pick up external writes
    if (sqliteReader && dbPathRef.current) {
      sqliteReader.close();
      sqliteReader = new SqliteReader(dbPathRef.current);
      vscode.commands.executeCommand("codeReviewGraph.codeGraph.refresh");
    }
  });

  watcher.onDidCreate(async () => {
    const wsRoot = getWorkspaceRoot();
    if (wsRoot && !sqliteReader) {
      const dbPath = findGraphDb(wsRoot);
      if (dbPath) {
        dbPathRef.current = dbPath;
        sqliteReader = new SqliteReader(dbPath);
        vscode.commands.executeCommand("codeReviewGraph.codeGraph.refresh");
      }
    }
  });

  watcher.onDidDelete(() => {
    sqliteReader?.close();
    sqliteReader = undefined;
    dbPathRef.current = "";
  });

  context.subscriptions.push(watcher);
}

/**
 * Set up debounced auto-update on file save.
 */
function setupAutoUpdate(
  context: vscode.ExtensionContext,
  cli: CliWrapper
): void {
  const AUTO_UPDATE_DEBOUNCE_MS = 2000;

  const onSave = vscode.workspace.onDidSaveTextDocument(() => {
    const config = vscode.workspace.getConfiguration("codeReviewGraph");
    if (!config.get<boolean>("autoUpdate", true)) {
      return;
    }

    if (autoUpdateTimer) {
      clearTimeout(autoUpdateTimer);
    }

    autoUpdateTimer = setTimeout(async () => {
      const wsRoot = getWorkspaceRoot();
      if (!wsRoot || !sqliteReader) {
        return;
      }

      try {
        await cli.updateGraph(wsRoot);
      } catch {
        // Silently ignore update errors on save; user can manually update
      }
    }, AUTO_UPDATE_DEBOUNCE_MS);
  });

  context.subscriptions.push(onSave);
}

/**
 * Extension activation entry point.
 */
export async function activate(
  context: vscode.ExtensionContext
): Promise<void> {
  const cli = new CliWrapper();
  const installer = new Installer(cli);

  // Register walkthrough commands
  registerWalkthroughCommands(context, cli, installer);

  const workspaceRoot = getWorkspaceRoot();

  if (workspaceRoot) {
    const dbPath = findGraphDb(workspaceRoot);

    if (dbPath) {
      // Graph database found - initialize
      sqliteReader = new SqliteReader(dbPath);

      // Register tree view providers
      const codeGraphProvider = new CodeGraphTreeProvider(
        sqliteReader,
        workspaceRoot
      );
      const blastRadiusProvider = new BlastRadiusTreeProvider();
      const statsProvider = new StatsTreeProvider(sqliteReader);

      context.subscriptions.push(
        vscode.window.registerTreeDataProvider(
          "codeReviewGraph.codeGraph",
          codeGraphProvider
        ),
        vscode.window.registerTreeDataProvider(
          "codeReviewGraph.blastRadius",
          blastRadiusProvider
        ),
        vscode.window.registerTreeDataProvider(
          "codeReviewGraph.stats",
          statsProvider
        )
      );

      // Create status bar
      const statusBar = new StatusBar();
      statusBar.update(sqliteReader);
      statusBar.show();
      context.subscriptions.push(statusBar);
    } else {
      // No graph database found - show welcome
      showWelcomeIfNeeded(context);
    }
  }

  // Register commands (always, even without a database)
  registerCommands(context, cli);

  // Watch for graph.db changes
  watchGraphDb(context);

  // Set up auto-update on save
  setupAutoUpdate(context, cli);
}

/**
 * Extension deactivation cleanup.
 */
export function deactivate(): void {
  if (autoUpdateTimer) {
    clearTimeout(autoUpdateTimer);
    autoUpdateTimer = undefined;
  }

  sqliteReader?.close();
  sqliteReader = undefined;
}
