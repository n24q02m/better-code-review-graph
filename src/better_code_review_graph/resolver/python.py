"""Python cross-repo symbol resolver (Phase 2 Task 3).

Resolves ``from lib.utils import retry`` style imports across federated
repos by:

1. Reading the source repo's ``pyproject.toml`` to confirm the import
   target is a declared dependency. Cross-repo edges are emitted only
   for declared deps so we don't spuriously link unrelated packages
   that happen to share a top-level name.
2. Walking each target repo's ``src/<package>/`` (PEP 420 namespace
   packages) to find a matching module path. Both ``module.py`` and
   ``module/__init__.py`` layouts are supported, and a non-``src``
   bare-root layout is tried as a fallback.
3. Returning a qualified-name string
   ``<target_repo_id>:<file_path>::<symbol>`` on a hit, or ``None``
   when nothing matches.

Single-repo (non-federated) mode is unaffected: when ``targets`` is
empty or no match is found, the resolver returns ``None`` and the
caller leaves the edge as a within-repo bare reference.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TargetRepo:
    """Per-target descriptor: ``repo_id`` plus its filesystem root."""

    repo_id: str
    root: Path


@dataclass(frozen=True)
class PythonImport:
    """Parsed Python import statement.

    ``module`` is the dotted module name being imported from. ``name``
    is the imported symbol (``from X import Y``) or the trailing
    component for a dotted ``import X.Y`` (``Y``); for a bare
    ``import X`` it is ``None`` and the resolver falls back to the
    module's own basename.
    """

    module: str
    name: str | None


_FROM_IMPORT_RE = re.compile(r"^from\s+([\w.]+)\s+import\s+(\w+)")
_BARE_IMPORT_RE = re.compile(r"^import\s+([\w.]+)")
_DEP_NAME_RE = re.compile(r"^([A-Za-z0-9_.-]+)")


def parse_import_statement(stmt: str) -> PythonImport | None:
    """Parse ``from X import Y`` or ``import X[.Y]``. Returns None on garbage.

    The parser intentionally accepts only the head of an import line so
    callers can pass either a single source line or a stripped fragment;
    relative imports (``from .x import y``) and aliased imports
    (``import x as y``) are out of scope for cross-repo resolution.
    """
    stmt = stmt.strip()
    m = _FROM_IMPORT_RE.match(stmt)
    if m:
        return PythonImport(module=m.group(1), name=m.group(2))
    m = _BARE_IMPORT_RE.match(stmt)
    if m:
        full = m.group(1)
        if "." in full:
            module, _, name = full.rpartition(".")
            return PythonImport(module=module, name=name)
        return PythonImport(module=full, name=None)
    return None


def _read_dependencies(pyproject_path: Path) -> set[str]:
    """Return the set of normalised top-level dep names from ``[project.dependencies]``.

    Names are lowercased and dashes are replaced with underscores so the
    set can be compared directly against an import top-level component
    (``Some-Pkg`` -> ``some_pkg``). Missing files and unparseable TOML
    yield an empty set so the caller treats both as "no declared deps".
    """
    if not pyproject_path.is_file():
        return set()
    try:
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return set()
    project = data.get("project") or {}
    deps = project.get("dependencies") or []
    out: set[str] = set()
    for entry in deps:
        m = _DEP_NAME_RE.match(str(entry).strip())
        if m:
            out.add(m.group(1).lower().replace("-", "_"))
    return out


class PythonResolver:
    """Resolve Python import statements across federated repos.

    Parameters
    ----------
    source_repo_root:
        Filesystem root of the repo containing the import line. Used to
        read its ``pyproject.toml`` once at construction time.
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
        self._declared_deps = _read_dependencies(self._source_root / "pyproject.toml")

    def resolve(
        self,
        import_stmt: str,
        targets: list[TargetRepo],
    ) -> str | None:
        """Return ``<repo_id>:<file_path>::<symbol>`` on hit, else None."""
        parsed = parse_import_statement(import_stmt)
        if parsed is None:
            return None
        top_level = parsed.module.split(".")[0].lower().replace("-", "_")
        if top_level not in self._declared_deps:
            return None
        for target in targets:
            if target.repo_id == self._source_repo_id:
                continue
            hit = self._walk_target(target, parsed)
            if hit is not None:
                return hit
        return None

    def _walk_target(
        self,
        target: TargetRepo,
        parsed: PythonImport,
    ) -> str | None:
        """Look for ``parsed.module`` under ``target.root``.

        The src-layout (``<root>/src/<pkg>/...``) is preferred and
        checked first; bare-root layouts (``<root>/<pkg>/...``) act as
        a fallback so the resolver works for both PEP 420 namespace
        packages laid out under ``src/`` and legacy flat repos.
        Returns a qualified name when the module file exists; otherwise
        ``None``.
        """
        target_root = target.root.resolve()
        module_parts = parsed.module.split(".")
        symbol = parsed.name or module_parts[-1]
        for layout_root in (target_root / "src", target_root):
            module_file = layout_root.joinpath(*module_parts).with_suffix(".py")
            if module_file.is_file():
                rel = module_file.relative_to(target_root)
                return f"{target.repo_id}:{rel.as_posix()}::{symbol}"
            init_file = layout_root.joinpath(*module_parts) / "__init__.py"
            if init_file.is_file():
                rel = init_file.relative_to(target_root)
                return f"{target.repo_id}:{rel.as_posix()}::{symbol}"
        return None
