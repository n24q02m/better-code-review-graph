import * as vscode from 'vscode';
import { SqliteReader, GraphNode, GraphEdge } from '../backend/sqlite';
import {
  FileTreeItem,
  SymbolTreeItem,
  EdgeTreeItem,
  BlastRadiusGroupItem,
  StatsItem,
} from './treeItems';

// ---------------------------------------------------------------------------
// CodeGraphTreeProvider -- main file > symbol > edge tree
// ---------------------------------------------------------------------------

export class CodeGraphTreeProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<vscode.TreeItem | undefined | null>();
  readonly onDidChangeTreeData: vscode.Event<vscode.TreeItem | undefined | null> = this._onDidChangeTreeData.event;

  constructor(
    private readonly reader: SqliteReader,
    private readonly workspaceRoot: string,
  ) {}

  refresh(): void {
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: vscode.TreeItem): vscode.ProviderResult<vscode.TreeItem[]> {
    if (!element) {
      return this.getRootChildren();
    }
    if (element instanceof FileTreeItem) {
      return this.getFileChildren(element);
    }
    if (element instanceof SymbolTreeItem) {
      return this.getSymbolChildren(element);
    }
    return [];
  }

  // -- Root level: one FileTreeItem per file --------------------------------

  private getRootChildren(): vscode.TreeItem[] {
    const files = this.reader.getAllFiles();
    return files
      .slice()
      .sort((a, b) => a.localeCompare(b))
      .map((filePath) => new FileTreeItem(filePath, this.workspaceRoot));
  }

  // -- File level: symbols (non-File nodes) sorted by line ------------------

  private getFileChildren(fileItem: FileTreeItem): vscode.TreeItem[] {
    const nodes = this.reader.getNodesByFile(fileItem.filePath);
    return nodes
      .filter((n) => n.kind !== 'File')
      .sort((a, b) => (a.lineStart ?? 0) - (b.lineStart ?? 0))
      .map(
        (n) =>
          new SymbolTreeItem(
            n.qualifiedName,
            n.name,
            n.kind,
            n.filePath,
            n.lineStart,
            n.lineEnd,
          ),
      );
  }

  // -- Symbol level: outgoing + incoming edges (skip CONTAINS) --------------

  private getSymbolChildren(symbolItem: SymbolTreeItem): vscode.TreeItem[] {
    const items: vscode.TreeItem[] = [];

    // Outgoing edges
    const outgoing = this.reader.getEdgesBySource(symbolItem.qualifiedName);
    for (const edge of outgoing) {
      if (edge.kind === 'CONTAINS') {
        continue;
      }
      const targetNode = this.reader.getNode(edge.targetQualified);
      const targetFile = targetNode?.filePath ?? edge.filePath;
      const targetLine = targetNode?.lineStart ?? edge.line;
      items.push(
        new EdgeTreeItem(
          edge.kind,
          'outgoing',
          edge.targetQualified,
          targetFile,
          targetLine,
        ),
      );
    }

    // Incoming edges
    const incoming = this.reader.getEdgesByTarget(symbolItem.qualifiedName);
    for (const edge of incoming) {
      if (edge.kind === 'CONTAINS') {
        continue;
      }
      const sourceNode = this.reader.getNode(edge.sourceQualified);
      const sourceFile = sourceNode?.filePath ?? edge.filePath;
      const sourceLine = sourceNode?.lineStart ?? edge.line;
      items.push(
        new EdgeTreeItem(
          edge.kind,
          'incoming',
          edge.sourceQualified,
          sourceFile,
          sourceLine,
        ),
      );
    }

    return items;
  }
}

// ---------------------------------------------------------------------------
// BlastRadiusTreeProvider -- shows changed + impacted nodes
// ---------------------------------------------------------------------------

export class BlastRadiusTreeProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<vscode.TreeItem | undefined | null>();
  readonly onDidChangeTreeData: vscode.Event<vscode.TreeItem | undefined | null> = this._onDidChangeTreeData.event;

  private changedNodes: GraphNode[] = [];
  private impactedNodes: GraphNode[] = [];

  setResults(changed: GraphNode[], impacted: GraphNode[]): void {
    this.changedNodes = changed;
    this.impactedNodes = impacted;
    this._onDidChangeTreeData.fire(undefined);
  }

  clear(): void {
    this.changedNodes = [];
    this.impactedNodes = [];
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: vscode.TreeItem): vscode.ProviderResult<vscode.TreeItem[]> {
    if (!element) {
      return this.getRootChildren();
    }
    if (element instanceof BlastRadiusGroupItem) {
      return this.getGroupChildren(element);
    }
    return [];
  }

  private getRootChildren(): vscode.TreeItem[] {
    if (this.changedNodes.length === 0 && this.impactedNodes.length === 0) {
      return [];
    }
    const groups: vscode.TreeItem[] = [];
    if (this.changedNodes.length > 0) {
      groups.push(new BlastRadiusGroupItem('changed', this.changedNodes.length));
    }
    if (this.impactedNodes.length > 0) {
      groups.push(new BlastRadiusGroupItem('impacted', this.impactedNodes.length));
    }
    return groups;
  }

  private getGroupChildren(group: BlastRadiusGroupItem): vscode.TreeItem[] {
    const nodes = group.groupKind === 'changed' ? this.changedNodes : this.impactedNodes;
    return nodes.map(
      (n) =>
        new SymbolTreeItem(
          n.qualifiedName,
          n.name,
          n.kind,
          n.filePath,
          n.lineStart,
          n.lineEnd,
        ),
    );
  }
}

// ---------------------------------------------------------------------------
// StatsTreeProvider -- graph statistics overview
// ---------------------------------------------------------------------------

export class StatsTreeProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<vscode.TreeItem | undefined | null>();
  readonly onDidChangeTreeData: vscode.Event<vscode.TreeItem | undefined | null> = this._onDidChangeTreeData.event;

  constructor(private readonly reader: SqliteReader) {}

  refresh(): void {
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(): vscode.ProviderResult<vscode.TreeItem[]> {
    const stats = this.reader.getStats();
    const items: StatsItem[] = [];

    items.push(new StatsItem('Files', stats.filesCount.toLocaleString()));
    items.push(new StatsItem('Total Nodes', stats.totalNodes.toLocaleString()));
    items.push(new StatsItem('Total Edges', stats.totalEdges.toLocaleString()));
    items.push(
      new StatsItem(
        'Languages',
        stats.languages.length > 0 ? stats.languages.join(', ') : 'none',
      ),
    );
    items.push(
      new StatsItem(
        'Last Updated',
        stats.lastUpdated ?? 'unknown',
      ),
    );
    items.push(
      new StatsItem(
        'Embeddings',
        stats.embeddingsCount > 0 ? stats.embeddingsCount.toLocaleString() : 'none',
      ),
    );

    return items;
  }
}
