import * as vscode from 'vscode';
import { SqliteReader } from '../backend/sqlite';
import { BlastRadiusTreeProvider } from '../views/treeView';
import { resolveNodeAtCursor } from './cursorResolver';

/**
 * Register the cursor-aware blast radius command.
 *
 * When invoked the command:
 *  1. Gets the active editor's file path and cursor line.
 *  2. Resolves the innermost node at cursor via the graph database.
 *  3. Falls back to the file-level node when no specific node is found.
 *  4. Runs a BFS impact radius query up to the configured depth.
 *  5. Updates the BlastRadiusTreeProvider with the results.
 *  6. Focuses the blast radius tree view.
 */
export function registerBlastRadiusCommand(
    context: vscode.ExtensionContext,
    getReader: () => SqliteReader | undefined,
    blastRadiusProvider: BlastRadiusTreeProvider,
    workspaceRoot: string,
): void {
    context.subscriptions.push(
        vscode.commands.registerCommand('codeReviewGraph.showBlastRadius', async () => {
            const reader = getReader();
            if (!reader) {
                vscode.window.showWarningMessage('Code Graph: No graph database loaded.');
                return;
            }

            // --- Active editor check ---
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showWarningMessage('Open a file first');
                return;
            }

            // --- Resolve file path and cursor position ---
            const absFilePath = editor.document.uri.fsPath;
            const cursorLine = editor.selection.active.line + 1; // 1-based

            // --- Resolve node at cursor ---
            const nodeAtCursor = reader.getNodeAtCursor(absFilePath, cursorLine);

            // Determine the file path to feed into getImpactRadius.
            // If we found a node, use its filePath (which is the canonical path
            // stored in the database). Otherwise fall back to the editor path.
            const filePath = nodeAtCursor ? nodeAtCursor.filePath : absFilePath;

            // --- Read depth from settings ---
            const config = vscode.workspace.getConfiguration('codeReviewGraph');
            const depth = config.get<number>('blastRadiusDepth', 2);

            // --- Compute blast radius ---
            const impact = reader.getImpactRadius([filePath], depth);

            // --- Update tree provider ---
            blastRadiusProvider.setResults(impact.changedNodes, impact.impactedNodes);

            // --- Focus the blast radius view ---
            await vscode.commands.executeCommand('codeReviewGraph.blastRadius.focus');

            // --- Summary message ---
            const impactedFileCount = new Set(impact.impactedNodes.map((n) => n.filePath)).size;
            vscode.window.showInformationMessage(
                `Blast radius: ${impact.impactedNodes.length} nodes impacted across ${impactedFileCount} files`,
            );
        }),
    );
}
