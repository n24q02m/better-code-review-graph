import * as vscode from 'vscode';
import { SqliteReader, GraphNode } from '../backend/sqlite';
import { resolveNodeAtCursor, navigateToNode } from './cursorResolver';

/**
 * Register the navigation commands: findCallers, findTests, and search.
 */
export function registerNavigationCommands(
    context: vscode.ExtensionContext,
    getReader: () => SqliteReader | undefined,
): void {
    // -----------------------------------------------------------------
    // codeReviewGraph.findCallers
    // -----------------------------------------------------------------
    context.subscriptions.push(
        vscode.commands.registerCommand('codeReviewGraph.findCallers', async () => {
            const reader = getReader();
            if (!reader) {
                vscode.window.showWarningMessage('Code Graph: No graph database loaded.');
                return;
            }

            // Resolve node at cursor
            const node = resolveNodeAtCursor(reader);
            if (!node) {
                vscode.window.showWarningMessage(
                    'Code Graph: No graph node found at the current cursor position.',
                );
                return;
            }

            // Query incoming CALLS edges
            const edges = reader.getEdgesByTarget(node.qualifiedName);
            const callerEdges = edges.filter((e) => e.kind === 'CALLS');

            if (callerEdges.length === 0) {
                vscode.window.showInformationMessage(
                    `Code Graph: No callers found for "${node.name}".`,
                );
                return;
            }

            // Build QuickPick items, resolving each caller to its full node
            const items: Array<{
                label: string;
                description: string;
                detail: string;
                node: GraphNode | undefined;
            }> = [];

            for (const edge of callerEdges) {
                const callerNode = reader.getNode(edge.sourceQualified);
                items.push({
                    label: callerNode?.name ?? edge.sourceQualified,
                    description: callerNode?.filePath ?? edge.filePath,
                    detail: `Line ${callerNode?.lineStart ?? edge.line}`,
                    node: callerNode,
                });
            }

            const selected = await vscode.window.showQuickPick(items, {
                placeHolder: `Callers of ${node.name}`,
            });

            if (selected?.node) {
                await navigateToNode(selected.node);
            }
        }),
    );

    // -----------------------------------------------------------------
    // codeReviewGraph.findTests
    // -----------------------------------------------------------------
    context.subscriptions.push(
        vscode.commands.registerCommand('codeReviewGraph.findTests', async () => {
            const reader = getReader();
            if (!reader) {
                vscode.window.showWarningMessage('Code Graph: No graph database loaded.');
                return;
            }

            // Resolve node at cursor
            const node = resolveNodeAtCursor(reader);
            if (!node) {
                vscode.window.showWarningMessage(
                    'Code Graph: No graph node found at the current cursor position.',
                );
                return;
            }

            // --- Collect test qualified names from TESTED_BY edges (both directions) ---
            const incomingEdges = reader.getEdgesByTarget(node.qualifiedName);
            const incomingTestEdges = incomingEdges.filter((e) => e.kind === 'TESTED_BY');

            const outgoingEdges = reader.getEdgesBySource(node.qualifiedName);
            const outgoingTestEdges = outgoingEdges.filter((e) => e.kind === 'TESTED_BY');

            const testQualifiedNames = new Set<string>([
                ...incomingTestEdges.map((e) => e.sourceQualified),
                ...outgoingTestEdges.map((e) => e.targetQualified),
            ]);

            // --- Also search by naming convention: test_{name}, Test{name} ---
            const conventionPatterns = [`test_${node.name}`, `Test${node.name}`];
            for (const pattern of conventionPatterns) {
                const matches = reader.searchNodes(pattern, 10);
                for (const match of matches) {
                    if (match.isTest || match.kind === 'Test') {
                        testQualifiedNames.add(match.qualifiedName);
                    }
                }
            }

            if (testQualifiedNames.size === 0) {
                vscode.window.showInformationMessage(
                    `Code Graph: No tests found for "${node.name}".`,
                );
                return;
            }

            // --- Build QuickPick items ---
            const items: Array<{
                label: string;
                description: string;
                detail: string;
                node: GraphNode | undefined;
            }> = [];

            for (const tqn of testQualifiedNames) {
                const testNode = reader.getNode(tqn);
                items.push({
                    label: testNode?.name ?? tqn,
                    description: testNode?.filePath ?? '',
                    detail: `Line ${testNode?.lineStart ?? '?'}`,
                    node: testNode,
                });
            }

            const selected = await vscode.window.showQuickPick(items, {
                placeHolder: `Tests for ${node.name}`,
            });

            if (selected?.node) {
                await navigateToNode(selected.node);
            }
        }),
    );

    // -----------------------------------------------------------------
    // codeReviewGraph.search
    // -----------------------------------------------------------------
    context.subscriptions.push(
        vscode.commands.registerCommand('codeReviewGraph.search', async () => {
            const reader = getReader();
            if (!reader) {
                vscode.window.showWarningMessage('Code Graph: No graph database loaded.');
                return;
            }

            const query = await vscode.window.showInputBox({
                prompt: 'Search the code graph',
                placeHolder: 'Enter a function, class, or module name',
            });

            if (!query) {
                return;
            }

            const results = reader.searchNodes(query, 30);

            if (results.length === 0) {
                vscode.window.showInformationMessage(
                    `Code Graph: No results found for "${query}".`,
                );
                return;
            }

            const items = results.map((r) => ({
                label: r.name,
                description: r.kind,
                detail: r.filePath
                    ? `${r.filePath}:${r.lineStart ?? ''}`
                    : undefined,
                result: r,
            }));

            const selected = await vscode.window.showQuickPick(items, {
                placeHolder: `Results for "${query}"`,
            });

            if (selected?.result) {
                await navigateToNode(selected.result);
            }
        }),
    );
}
