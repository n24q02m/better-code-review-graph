import * as vscode from 'vscode';
import { SqliteReader } from '../backend/sqlite';

/** Number of milliseconds in one hour. */
const ONE_HOUR_MS = 60 * 60 * 1000;

/**
 * Manages a status bar item that shows a summary of the code graph
 * database and its staleness.
 *
 * Clicking the status bar item triggers `codeReviewGraph.updateGraph`.
 */
export class StatusBar implements vscode.Disposable {
    private item: vscode.StatusBarItem;

    constructor() {
        this.item = vscode.window.createStatusBarItem(
            vscode.StatusBarAlignment.Left,
            100,
        );
        this.item.command = 'codeReviewGraph.updateGraph';
    }

    /**
     * Update the status bar text, icon, and tooltip based on the current
     * state of the graph database.
     *
     * @param reader  The open SQLite reader, or `undefined` if no database
     *                is loaded.
     */
    update(reader: SqliteReader | undefined): void {
        if (!reader) {
            this.item.text = '$(warning) Code Graph: Not built';
            this.item.tooltip = 'Click to build';
            return;
        }

        const stats = reader.getStats();

        const lastUpdated = stats.lastUpdated;
        const isOutdated = this.isOlderThanOneHour(lastUpdated);

        if (isOutdated) {
            this.item.text = '$(warning) Code Graph: Outdated';
            this.item.tooltip =
                `Code Graph: ${stats.filesCount} files, ${stats.totalEdges} edges\n` +
                `Last updated: ${lastUpdated || 'unknown'}`;
        } else {
            this.item.text = `$(database) ${stats.totalNodes} nodes`;
            this.item.tooltip =
                `Code Graph: ${stats.filesCount} files, ${stats.totalEdges} edges\n` +
                `Last updated: ${lastUpdated || 'unknown'}`;
        }
    }

    /** Show the status bar item. */
    show(): void {
        this.item.show();
    }

    /** Hide the status bar item. */
    hide(): void {
        this.item.hide();
    }

    /** Dispose the status bar item. */
    dispose(): void {
        this.item.dispose();
    }

    /**
     * Determine whether `lastUpdated` is more than one hour in the past.
     *
     * Returns `true` if the timestamp is missing, unparseable, or older
     * than one hour.
     */
    private isOlderThanOneHour(lastUpdated: string | null): boolean {
        if (!lastUpdated) {
            return true;
        }

        const updatedTime = new Date(lastUpdated).getTime();
        if (isNaN(updatedTime)) {
            return true;
        }

        return Date.now() - updatedTime > ONE_HOUR_MS;
    }
}
