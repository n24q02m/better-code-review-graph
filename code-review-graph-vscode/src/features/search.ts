/**
 * Quick search command with live filtering.
 *
 * Shows a QuickPick that queries the graph database as the user types,
 * then navigates to the selected node's source location.
 */

import * as vscode from 'vscode';
import * as path from 'node:path';
import { SqliteReader, GraphNode } from '../backend/sqlite';

// ---------------------------------------------------------------------------
// Kind-to-icon mapping (uses VS Code codicon identifiers)
// ---------------------------------------------------------------------------

const KIND_ICON: Record<string, string> = {
  Function: '$(symbol-method)',
  Class: '$(symbol-class)',
  File: '$(file)',
  Test: '$(beaker)',
  Type: '$(symbol-interface)',
};

/**
 * Build a QuickPickItem from a GraphNode.
 */
function nodeToQuickPickItem(
  node: GraphNode,
  workspaceRoot: string | undefined,
): vscode.QuickPickItem & { node: GraphNode } {
  const icon = KIND_ICON[node.kind] ?? '$(symbol-misc)';
  const relativePath = workspaceRoot
    ? path.relative(workspaceRoot, node.filePath)
    : node.filePath;
  const lineInfo = node.lineStart != null ? `:${node.lineStart}` : '';

  return {
    label: `${icon} ${node.name}`,
    description: node.kind,
    detail: `${relativePath}${lineInfo}`,
    node,
  };
}

/**
 * Navigate to a node's source location.
 */
async function navigateToNode(
  node: GraphNode,
  workspaceRoot: string | undefined,
): Promise<void> {
  const filePath = workspaceRoot
    ? path.join(workspaceRoot, node.filePath)
    : node.filePath;

  const uri = vscode.Uri.file(filePath);
  const doc = await vscode.workspace.openTextDocument(uri);
  const line = Math.max(0, (node.lineStart ?? 1) - 1);
  await vscode.window.showTextDocument(doc, {
    selection: new vscode.Range(line, 0, line, 0),
  });
}

/**
 * Register the `codeReviewGraph.search` command.
 *
 * Opens a QuickPick with live filtering:
 *  - As the user types, `reader.searchNodes(value, 20)` is called.
 *  - Results are displayed with kind-specific icons.
 *  - On accept, the editor navigates to the selected node.
 */
export function registerSearchCommand(
  context: vscode.ExtensionContext,
  reader: SqliteReader,
): void {
  const disposable = vscode.commands.registerCommand(
    'codeReviewGraph.search',
    async () => {
      const workspaceRoot =
        vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

      const quickPick = vscode.window.createQuickPick<
        vscode.QuickPickItem & { node: GraphNode }
      >();
      quickPick.placeholder = 'Search for functions, classes, files, types...';
      quickPick.matchOnDescription = true;
      quickPick.matchOnDetail = true;

      // Debounce timer to avoid querying on every keystroke
      let debounceTimer: ReturnType<typeof setTimeout> | undefined;

      quickPick.onDidChangeValue((value) => {
        if (debounceTimer) {
          clearTimeout(debounceTimer);
        }

        if (!value) {
          quickPick.items = [];
          return;
        }

        debounceTimer = setTimeout(() => {
          const results = reader.searchNodes(value, 20);
          quickPick.items = results.map((node) =>
            nodeToQuickPickItem(node, workspaceRoot),
          );
        }, 100);
      });

      quickPick.onDidAccept(async () => {
        const selected = quickPick.selectedItems[0];
        quickPick.dispose();

        if (selected?.node) {
          await navigateToNode(selected.node, workspaceRoot);
        }
      });

      quickPick.onDidHide(() => {
        if (debounceTimer) {
          clearTimeout(debounceTimer);
        }
        quickPick.dispose();
      });

      quickPick.show();
    },
  );

  context.subscriptions.push(disposable);
}
