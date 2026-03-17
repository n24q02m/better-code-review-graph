import * as vscode from 'vscode';
import { SqliteReader, GraphNode } from '../backend/sqlite';

/**
 * Resolve the innermost graph node at the current cursor position.
 *
 * Returns `undefined` when there is no active editor or no node spans the
 * cursor line in the graph database.
 */
export function resolveNodeAtCursor(
    reader: SqliteReader,
): GraphNode | undefined {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        return undefined;
    }

    const filePath = editor.document.uri.fsPath;
    const line = editor.selection.active.line + 1; // VS Code is 0-based, SQLite data is 1-based

    return reader.getNodeAtCursor(filePath, line);
}

/**
 * Open a document and scroll to the node's start line.
 *
 * The node's `filePath` is treated as an absolute path. If `lineStart` is
 * null the file is opened at the top.
 */
export async function navigateToNode(node: GraphNode): Promise<void> {
    const uri = vscode.Uri.file(node.filePath);
    const doc = await vscode.workspace.openTextDocument(uri);
    const line = Math.max(0, (node.lineStart ?? 1) - 1);
    await vscode.window.showTextDocument(doc, {
        selection: new vscode.Range(line, 0, line, 0),
    });
}
