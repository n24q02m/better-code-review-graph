import * as vscode from 'vscode';
import * as path from 'path';

// ---------------------------------------------------------------------------
// FileTreeItem – represents a source file in the code graph
// ---------------------------------------------------------------------------

export class FileTreeItem extends vscode.TreeItem {
  public readonly filePath: string;
  public readonly qualifiedName: string;

  constructor(filePath: string, workspaceRoot: string) {
    const fileName = path.basename(filePath);
    super(fileName, vscode.TreeItemCollapsibleState.Collapsed);

    this.filePath = filePath;
    this.qualifiedName = filePath;

    const relativePath = path.relative(workspaceRoot, filePath);
    this.description = relativePath !== fileName ? relativePath : '';
    this.iconPath = new vscode.ThemeIcon('file');
    this.contextValue = 'node-file';
    this.tooltip = filePath;

    this.command = {
      title: 'Open File',
      command: 'vscode.open',
      arguments: [vscode.Uri.file(filePath)],
    };
  }
}

// ---------------------------------------------------------------------------
// SymbolTreeItem – represents a class, function, type, or test node
// ---------------------------------------------------------------------------

const KIND_ICON_MAP: Record<string, string> = {
  Function: 'symbol-method',
  Class: 'symbol-class',
  Type: 'symbol-interface',
  Test: 'testing-run-icon',
};

const KIND_CONTEXT_MAP: Record<string, string> = {
  Function: 'node-function',
  Class: 'node-class',
  Type: 'node-type',
  Test: 'node-test',
};

function formatSymbolLabel(name: string, kind: string): string {
  if (kind === 'Function' || kind === 'Test') {
    return `${name}()`;
  }
  return name;
}

function formatSymbolDescription(kind: string, lineStart: number | null, lineEnd: number | null): string {
  const kindLower = kind.toLowerCase();
  if (lineStart != null && lineEnd != null) {
    return `${kindLower} \u00b7 L${lineStart}\u2013${lineEnd}`;
  }
  if (lineStart != null) {
    return `${kindLower} \u00b7 L${lineStart}`;
  }
  return kindLower;
}

export class SymbolTreeItem extends vscode.TreeItem {
  public readonly qualifiedName: string;
  public readonly filePath: string;
  public readonly lineStart: number | null;
  public readonly kind: string;

  constructor(
    qualifiedName: string,
    name: string,
    kind: string,
    filePath: string,
    lineStart: number | null,
    lineEnd: number | null,
  ) {
    const label = formatSymbolLabel(name, kind);
    super(label, vscode.TreeItemCollapsibleState.Collapsed);

    this.qualifiedName = qualifiedName;
    this.filePath = filePath;
    this.lineStart = lineStart;
    this.kind = kind;

    this.description = formatSymbolDescription(kind, lineStart, lineEnd);
    this.iconPath = new vscode.ThemeIcon(KIND_ICON_MAP[kind] ?? 'symbol-misc');
    this.contextValue = KIND_CONTEXT_MAP[kind] ?? 'node-function';
    this.tooltip = qualifiedName;

    const line = lineStart != null ? lineStart - 1 : 0;
    this.command = {
      title: 'Go to Symbol',
      command: 'vscode.open',
      arguments: [
        vscode.Uri.file(filePath),
        { selection: new vscode.Range(line, 0, line, 0) } as vscode.TextDocumentShowOptions,
      ],
    };
  }
}

// ---------------------------------------------------------------------------
// EdgeTreeItem – represents a relationship edge (leaf node)
// ---------------------------------------------------------------------------

const OUTGOING_EDGE_LABELS: Record<string, string> = {
  CALLS: 'calls',
  IMPORTS_FROM: 'imports',
  INHERITS: 'inherits from',
  IMPLEMENTS: 'implements',
  TESTED_BY: 'tested by',
  CONTAINS: 'contains',
  DEPENDS_ON: 'depends on',
};

const INCOMING_EDGE_LABELS: Record<string, string> = {
  CALLS: 'called by',
  IMPORTS_FROM: 'imported by',
  INHERITS: 'inherited by',
  IMPLEMENTS: 'implemented by',
  TESTED_BY: 'tests',
  CONTAINS: 'contained in',
  DEPENDS_ON: 'depended on by',
};

const EDGE_ICON_MAP_OUTGOING: Record<string, string> = {
  CALLS: 'arrow-right',
  IMPORTS_FROM: 'package',
  INHERITS: 'type-hierarchy',
  IMPLEMENTS: 'symbol-interface',
  TESTED_BY: 'testing-run-icon',
  CONTAINS: 'symbol-namespace',
  DEPENDS_ON: 'references',
};

const EDGE_ICON_MAP_INCOMING: Record<string, string> = {
  CALLS: 'arrow-left',
  IMPORTS_FROM: 'package',
  INHERITS: 'type-hierarchy',
  IMPLEMENTS: 'symbol-interface',
  TESTED_BY: 'testing-run-icon',
  CONTAINS: 'symbol-namespace',
  DEPENDS_ON: 'references',
};

function extractShortName(qualifiedName: string): string {
  // Qualified names are like "/path/to/file.py::ClassName.method" or "/path/to/file.py"
  const colonIdx = qualifiedName.lastIndexOf('::');
  if (colonIdx >= 0) {
    return qualifiedName.substring(colonIdx + 2);
  }
  return path.basename(qualifiedName);
}

export class EdgeTreeItem extends vscode.TreeItem {
  public readonly targetQualifiedName: string;
  public readonly targetFilePath: string;
  public readonly targetLine: number;

  constructor(
    edgeKind: string,
    direction: 'outgoing' | 'incoming',
    targetQualifiedName: string,
    targetFilePath: string,
    targetLine: number,
  ) {
    const shortName = extractShortName(targetQualifiedName);
    const verb = direction === 'outgoing'
      ? (OUTGOING_EDGE_LABELS[edgeKind] ?? edgeKind.toLowerCase())
      : (INCOMING_EDGE_LABELS[edgeKind] ?? edgeKind.toLowerCase());
    const arrow = direction === 'outgoing' ? '\u2192' : '\u2190';
    const label = `${arrow} ${verb} ${shortName}`;

    super(label, vscode.TreeItemCollapsibleState.None);

    this.targetQualifiedName = targetQualifiedName;
    this.targetFilePath = targetFilePath;
    this.targetLine = targetLine;

    const iconMap = direction === 'outgoing' ? EDGE_ICON_MAP_OUTGOING : EDGE_ICON_MAP_INCOMING;
    this.iconPath = new vscode.ThemeIcon(iconMap[edgeKind] ?? 'arrow-right');
    this.contextValue = 'edge';
    this.tooltip = `${arrow} ${verb} ${targetQualifiedName}`;

    const line = targetLine > 0 ? targetLine - 1 : 0;
    this.command = {
      title: 'Go to Target',
      command: 'vscode.open',
      arguments: [
        vscode.Uri.file(targetFilePath),
        { selection: new vscode.Range(line, 0, line, 0) } as vscode.TextDocumentShowOptions,
      ],
    };
  }
}

// ---------------------------------------------------------------------------
// BlastRadiusGroupItem – groups "Changed" and "Impacted" results
// ---------------------------------------------------------------------------

export class BlastRadiusGroupItem extends vscode.TreeItem {
  public readonly groupKind: 'changed' | 'impacted';

  constructor(groupKind: 'changed' | 'impacted', count: number) {
    const label = groupKind === 'changed' ? `Changed (${count})` : `Impacted (${count})`;
    super(label, vscode.TreeItemCollapsibleState.Expanded);

    this.groupKind = groupKind;
    this.iconPath = new vscode.ThemeIcon(groupKind === 'changed' ? 'flame' : 'broadcast');
    this.contextValue = `blast-radius-${groupKind}`;
    this.tooltip = groupKind === 'changed'
      ? `${count} directly changed node(s)`
      : `${count} transitively impacted node(s)`;
  }
}

// ---------------------------------------------------------------------------
// StatsItem – displays a single statistic line (leaf node)
// ---------------------------------------------------------------------------

export class StatsItem extends vscode.TreeItem {
  constructor(label: string, value: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.description = value;
    this.contextValue = 'stat';
    this.tooltip = `${label}: ${value}`;
  }
}
