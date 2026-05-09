"""TypeScript cross-repo symbol resolver (Phase 2 Task 4).

Resolves ``import { foo } from '@/lib/utils'`` style imports across
federated TypeScript repos by:

1. Reading the source repo's ``tsconfig.json`` ``compilerOptions.paths``
   to expand path-mapping aliases (``@/foo/*`` -> ``packages/foo/*``).
2. Reading each target repo's ``package.json`` ``workspaces`` field
   (string list or ``{packages: [...]}`` object form) to identify
   monorepo workspace roots.
3. Walking each target repo's workspace dirs to find the matching
   ``.ts`` / ``.tsx`` / ``.d.ts`` file (with ``index.ts`` /
   ``index.tsx`` directory fallback).
4. Returning ``<target_repo_id>:<file_path>::<symbol>`` on hit, else
   ``None``.

Single-repo (non-federated) mode is unaffected: when ``targets`` is
empty or no match is found, the resolver returns ``None`` and the
caller leaves the edge as a within-repo bare reference.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ._types import TargetRepo  # re-exported for backwards compatibility

__all__ = [
    "TargetRepo",
    "TypeScriptImport",
    "TypeScriptResolver",
    "parse_import_statement",
]


@dataclass(frozen=True)
class TypeScriptImport:
    """Parsed TypeScript import declaration.

    ``module`` is the module specifier (``'@/lib/utils'``,
    ``'lodash'``, etc). ``name`` is the symbol associated with the
    import: the namespace identifier for ``import * as ns``, the
    default-import name for ``import x from``, the first named symbol
    for ``import { x, y }``, or ``None`` for side-effect-only imports
    (``import 'reflect-metadata'``).
    """

    module: str
    name: str | None


# Match named imports first (curly braces present) -> capture first symbol.
_NAMED_IMPORT_RE = re.compile(
    r"^import\s*\{\s*(\w+)[^}]*\}\s*from\s*['\"]([^'\"]+)['\"]"
)
# Match ``import * as ns from 'mod'``.
_NAMESPACE_IMPORT_RE = re.compile(
    r"^import\s+\*\s+as\s+(\w+)\s+from\s*['\"]([^'\"]+)['\"]"
)
# Match ``import name from 'mod'`` (default).
_DEFAULT_IMPORT_RE = re.compile(r"^import\s+(\w+)\s+from\s*['\"]([^'\"]+)['\"]")
# Match ``import 'mod'`` (side effect only).
_SIDE_EFFECT_IMPORT_RE = re.compile(r"^import\s*['\"]([^'\"]+)['\"]")


def parse_import_statement(stmt: str) -> TypeScriptImport | None:
    """Parse a TypeScript import declaration. Returns None on garbage.

    Supported forms (in matching order):

    * ``import { foo, bar } from 'mod'`` -> ``name='foo'`` (first
      named symbol)
    * ``import * as ns from 'mod'`` -> ``name='ns'``
    * ``import foo from 'mod'`` -> ``name='foo'`` (default import)
    * ``import 'mod'`` -> ``name=None`` (side-effect only)

    A trailing ``;`` is tolerated. Lines that look like comments,
    declarations, or anything else return ``None``.
    """
    stmt = stmt.strip().rstrip(";").strip()
    m = _NAMED_IMPORT_RE.match(stmt)
    if m:
        return TypeScriptImport(module=m.group(2), name=m.group(1))
    m = _NAMESPACE_IMPORT_RE.match(stmt)
    if m:
        return TypeScriptImport(module=m.group(2), name=m.group(1))
    m = _DEFAULT_IMPORT_RE.match(stmt)
    if m:
        return TypeScriptImport(module=m.group(2), name=m.group(1))
    m = _SIDE_EFFECT_IMPORT_RE.match(stmt)
    if m:
        return TypeScriptImport(module=m.group(1), name=None)
    return None


def _read_tsconfig_paths(tsconfig_path: Path) -> dict[str, list[str]]:
    """Return ``compilerOptions.paths`` mapping. Empty dict on missing/malformed.

    ``tsconfig.json`` files frequently contain ``//`` line comments
    which are not strict JSON; this helper strips those before
    parsing. Non-existent or unparseable files yield an empty dict so
    the caller treats both as "no path aliases".
    """
    if not tsconfig_path.is_file():
        return {}
    try:
        text = tsconfig_path.read_text(encoding="utf-8")
        # Strip ``//`` line comments (good-enough for the common case;
        # block comments and string-embedded ``//`` are out of scope).
        text = re.sub(r"//[^\n]*", "", text)
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return {}
    compiler_options = data.get("compilerOptions") or {}
    paths = compiler_options.get("paths") or {}
    out: dict[str, list[str]] = {}
    for alias, target in paths.items():
        # TypeScript allows either a string or a list of strings.
        if isinstance(target, str):
            out[alias] = [target]
        elif isinstance(target, list):
            out[alias] = [str(t) for t in target]
    return out


def _read_workspaces(package_json_path: Path) -> list[str]:
    """Return ``workspaces`` glob list from ``package.json``.

    Both the npm/yarn array form (``"workspaces": ["packages/*"]``) and
    the yarn classic object form (``"workspaces": {"packages": [...]}``)
    are supported. Missing files, unparseable JSON, missing field, or
    the object form without a ``packages`` key all yield an empty list.
    """
    if not package_json_path.is_file():
        return []
    try:
        data = json.loads(package_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    ws = data.get("workspaces")
    if isinstance(ws, list):
        return [str(w) for w in ws]
    if isinstance(ws, dict):
        packages = ws.get("packages") or []
        return [str(p) for p in packages]
    return []


def _expand_alias(import_module: str, paths: dict[str, list[str]]) -> list[str]:
    """Expand a tsconfig path alias into candidate filesystem paths.

    ``paths={"@/foo/*": ["packages/foo/*"]}`` with ``import_module =
    "@/foo/utils"`` yields ``["packages/foo/utils"]``. Aliases ending
    in ``/*`` glob-match a prefix and substitute the suffix into the
    target. Aliases without ``/*`` only match the exact module
    specifier. When no alias matches, the module is returned as the
    sole candidate (the resolver will then try to find it directly
    under workspace roots / repo root).
    """
    candidates: list[str] = []
    for alias, targets in paths.items():
        if alias.endswith("/*"):
            prefix = alias[:-2]
            if import_module.startswith(prefix + "/"):
                suffix = import_module[len(prefix) + 1 :]
                for t in targets:
                    if t.endswith("/*"):
                        candidates.append(t[:-2] + "/" + suffix)
                    else:
                        candidates.append(t + "/" + suffix)
        elif import_module == alias:
            candidates.extend(targets)
    if not candidates:
        candidates.append(import_module)
    return candidates


class TypeScriptResolver:
    """Resolve TypeScript imports across federated repos.

    Parameters
    ----------
    source_repo_root:
        Filesystem root of the repo containing the import line. Used
        to read its ``tsconfig.json`` once at construction time.
    source_repo_id:
        Logical id of the source repo. Targets sharing this id are
        skipped during :meth:`resolve` so a target list including
        ``self`` never produces a self-referential edge.
    """

    def __init__(
        self,
        source_repo_root: Path,
        source_repo_id: str,
    ) -> None:
        self._source_root = source_repo_root.resolve()
        self._source_repo_id = source_repo_id
        self._tsconfig_paths = _read_tsconfig_paths(self._source_root / "tsconfig.json")

    def resolve(
        self,
        import_stmt: str,
        targets: list[TargetRepo],
    ) -> str | None:
        """Return ``<repo_id>:<file_path>::<symbol>`` on hit, else None."""
        parsed = parse_import_statement(import_stmt)
        if parsed is None or parsed.name is None:
            # Side-effect imports don't link to a specific symbol, and
            # garbage lines have nothing to look up.
            return None
        candidates = _expand_alias(parsed.module, self._tsconfig_paths)
        for target in targets:
            if target.repo_id == self._source_repo_id:
                continue
            hit = self._walk_target(target, candidates, parsed.name)
            if hit is not None:
                return hit
        return None

    def _walk_target(
        self,
        target: TargetRepo,
        candidates: list[str],
        symbol: str,
    ) -> str | None:
        """Look for any candidate path under target's workspace roots.

        Each workspace glob (``packages/*``) is treated as a directory
        prefix (``packages``) under which candidate paths are joined.
        The repo root itself is also tried as a fallback so monorepos
        without a ``workspaces`` declaration still resolve. For each
        ``(root, candidate)`` pair, the ``.ts`` / ``.tsx`` / ``.d.ts``
        extensions are tried plus an ``index.ts`` / ``index.tsx``
        directory form. Returns the qualified name on the first hit.
        """
        target_root = target.root.resolve()
        workspaces = _read_workspaces(target_root / "package.json")
        # Build search roots: workspace dirs first, then bare repo root.
        search_roots: list[Path] = []
        for ws_glob in workspaces:
            ws_dir = ws_glob.rstrip("/*").rstrip("/")
            search_roots.append(target_root / ws_dir)
        search_roots.append(target_root)

        for candidate in candidates:
            for root in search_roots:
                for ext in (".ts", ".tsx", ".d.ts"):
                    f = root / (candidate + ext)
                    if f.is_file():
                        rel = f.resolve().relative_to(target_root)
                        return f"{target.repo_id}:{rel.as_posix()}::{symbol}"
                for index_name in ("index.ts", "index.tsx"):
                    f = root / candidate / index_name
                    if f.is_file():
                        rel = f.resolve().relative_to(target_root)
                        return f"{target.repo_id}:{rel.as_posix()}::{symbol}"
        return None
