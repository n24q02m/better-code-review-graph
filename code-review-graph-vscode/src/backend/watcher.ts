import * as path from 'path';
import * as vscode from 'vscode';

/**
 * Return a debounced version of `fn` that delays invocation until `ms`
 * milliseconds have elapsed since the last call.  The returned function
 * has the same signature as the original.
 */
export function debounce<T extends (...args: any[]) => any>(fn: T, ms: number): T {
    let timer: ReturnType<typeof setTimeout> | undefined;

    const debounced = (...args: Parameters<T>): void => {
        if (timer !== undefined) {
            clearTimeout(timer);
        }
        timer = setTimeout(() => {
            timer = undefined;
            fn(...args);
        }, ms);
    };

    return debounced as unknown as T;
}

/**
 * Watches a `graph.db` file on disk and fires a callback whenever the
 * file is created or modified (debounced to avoid rapid successive events).
 */
export class GraphWatcher implements vscode.Disposable {
    private readonly watcher: vscode.FileSystemWatcher;
    private readonly disposables: vscode.Disposable[] = [];

    /**
     * @param dbPath   Absolute path to the `graph.db` file to watch.
     * @param onChanged Callback invoked (at most once per 500 ms) when the file changes.
     */
    constructor(dbPath: string, onChanged: () => void) {
        const dir = path.dirname(dbPath);
        const filename = path.basename(dbPath);

        this.watcher = vscode.workspace.createFileSystemWatcher(
            new vscode.RelativePattern(vscode.Uri.file(dir), filename),
        );

        const debouncedOnChanged = debounce(onChanged, 500);

        this.disposables.push(
            this.watcher.onDidChange(() => debouncedOnChanged()),
            this.watcher.onDidCreate(() => debouncedOnChanged()),
            this.watcher,
        );
    }

    dispose(): void {
        for (const d of this.disposables) {
            d.dispose();
        }
        this.disposables.length = 0;
    }
}
