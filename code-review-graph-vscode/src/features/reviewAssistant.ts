/**
 * SCM integration for code review.
 *
 * Detects staged and unstaged changes via git, computes the blast radius
 * for those files, and populates the Blast Radius tree view so the reviewer
 * can see what is impacted before committing.
 */

import * as vscode from 'vscode';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { SqliteReader } from '../backend/sqlite';
import { BlastRadiusTreeProvider } from '../views/treeView';

const execFileAsync = promisify(execFile);

/** Timeout for git commands (milliseconds). */
const GIT_TIMEOUT_MS = 10_000;

/**
 * Run a git command in the given working directory and return trimmed stdout
 * lines. Returns an empty array on any error (e.g. git not installed, not a
 * git repo, etc.).
 */
async function gitLines(
  args: string[],
  cwd: string,
): Promise<string[]> {
  try {
    const { stdout } = await execFileAsync('git', args, {
      cwd,
      timeout: GIT_TIMEOUT_MS,
    });
    return stdout
      .trim()
      .split('\n')
      .filter((line) => line.length > 0);
  } catch {
    return [];
  }
}

/**
 * Register the `codeReviewGraph.reviewChanges` command.
 *
 * The command:
 *  1. Runs `git diff --name-only HEAD` and `git diff --cached --name-only`
 *     to collect changed + staged files.
 *  2. Computes the blast radius for those files.
 *  3. Updates the BlastRadiusTreeProvider with the results.
 *  4. Focuses the blast radius view.
 */
export function registerReviewCommand(
  context: vscode.ExtensionContext,
  reader: SqliteReader,
  blastRadiusProvider: BlastRadiusTreeProvider,
): void {
  const disposable = vscode.commands.registerCommand(
    'codeReviewGraph.reviewChanges',
    async () => {
      const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
      if (!workspaceFolder) {
        vscode.window.showErrorMessage('No workspace folder is open.');
        return;
      }

      const workspaceRoot = workspaceFolder.uri.fsPath;

      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: 'Code Graph: Analyzing changes...',
          cancellable: false,
        },
        async () => {
          // 1. Collect changed files (unstaged + staged, deduplicated)
          const [unstaged, staged] = await Promise.all([
            gitLines(['diff', '--name-only', 'HEAD'], workspaceRoot),
            gitLines(['diff', '--cached', '--name-only'], workspaceRoot),
          ]);

          const changedFiles = [...new Set([...unstaged, ...staged])];

          if (changedFiles.length === 0) {
            vscode.window.showInformationMessage(
              'No changes detected.',
            );
            return;
          }

          // 2. Compute blast radius
          const config = vscode.workspace.getConfiguration('codeReviewGraph');
          const depth = config.get<number>('blastRadiusDepth', 2);
          const impact = reader.getImpactRadius(changedFiles, depth);

          // 3. Update tree provider
          blastRadiusProvider.setResults(
            impact.changedNodes,
            impact.impactedNodes,
          );

          // 4. Focus the blast radius view
          await vscode.commands.executeCommand(
            'codeReviewGraph.blastRadius.focus',
          );

          // 5. Show summary
          vscode.window.showInformationMessage(
            `Review: ${changedFiles.length} changed file(s) impact ${impact.impactedNodes.length} additional file(s).`,
          );
        },
      );
    },
  );

  context.subscriptions.push(disposable);
}
