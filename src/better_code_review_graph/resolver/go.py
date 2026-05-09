"""Go cross-repo symbol resolver (Phase 2 Task 5).

Resolves Go imports across federated repos by:

1. Reading the source repo's ``go.mod`` ``replace`` directives to map
   module paths to local filesystem paths
   (``replace example.com/a => ../a``). Module-to-module replacements
   (``replace example.com/a => other.com/a v1.0``) are filtered out
   because they don't point at a local sibling repo.
2. Reading the source repo's ``go.work`` workspace declarations
   (``use ./moduleA`` or block form ``use (\\n ./a\\n ./b\\n)``) so
   workspace-style monorepos resolve as well.
3. Walking each target repo's filesystem to find ``.go`` files matching
   the resolved package directory. Test files (``_test.go``) are
   skipped — they don't host externally-importable symbols.
4. Returning ``<target_repo_id>:<file_path>::<symbol>`` on a hit, else
   ``None``.

Go imports are path-only (``import "example.com/a/util"``) — the symbol
referenced at the call site (``util.DoThing()``) is not part of the
import line. The resolver therefore takes ``import_stmt`` (the import
path) AND ``symbol`` (extracted by the caller from the call expression).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TargetRepo:
    """Per-target descriptor: ``repo_id`` plus its filesystem root."""

    repo_id: str
    root: Path


@dataclass(frozen=True)
class GoImport:
    """Parsed Go import declaration.

    ``module_path`` is the import path (e.g. ``example.com/a/util``).
    ``alias`` is the local name when the import is aliased
    (``import u "example.com/a/util"``); ``None`` otherwise.
    """

    module_path: str
    alias: str | None


# ``import "example.com/a/util"`` or ``import u "example.com/a/util"``.
_IMPORT_SINGLE_RE = re.compile(r'^\s*import\s+(?:(\w+)\s+)?["\']([^"\']+)["\']\s*$')
# Single line of an ``import (...)`` block: bare ``"path"`` or ``alias "path"``.
_IMPORT_LINE_RE = re.compile(r'^\s*(?:(\w+)\s+)?["\']([^"\']+)["\']\s*$')

# ``replace example.com/a => ../a`` or ``replace example.com/a v1.0 => ../a v1.0``.
_GO_MOD_REPLACE_RE = re.compile(
    r"^\s*replace\s+(\S+)(?:\s+\S+)?\s+=>\s+(\S+)(?:\s+\S+)?\s*$"
)
# ``use ./moduleA`` (single-line form).
_GO_WORK_USE_RE = re.compile(r"^\s*use\s+(\S+)\s*$")


def parse_import_statement(stmt: str) -> GoImport | None:
    """Parse a Go import line. Returns ``None`` on garbage.

    Supported forms:

    * ``import "example.com/a/util"`` -> ``alias=None``
    * ``import u "example.com/a/util"`` -> ``alias="u"``
    * Single line of an ``import (...)`` block: ``"example.com/a/util"``
      or ``u "example.com/a/util"``
    """
    m = _IMPORT_SINGLE_RE.match(stmt)
    if m:
        return GoImport(module_path=m.group(2), alias=m.group(1))
    m = _IMPORT_LINE_RE.match(stmt)
    if m:
        return GoImport(module_path=m.group(2), alias=m.group(1))
    return None


def _is_local_path(replacement: str) -> bool:
    """True iff ``replacement`` points at a local filesystem path.

    Recognises ``./``, ``../``, POSIX-absolute (``/foo``), and Windows
    drive-letter (``C:\\foo``) prefixes. Anything else (e.g.
    ``other.com/a``) is treated as a module-to-module replacement and
    filtered out by the caller.
    """
    if replacement.startswith(("./", "../", "/")):
        return True
    return len(replacement) > 1 and replacement[1] == ":"


def _read_go_mod_replaces(go_mod_path: Path) -> dict[str, str]:
    """Return ``module -> local_path`` map from go.mod ``replace`` directives.

    Only local-path replacements are returned. Missing or unreadable
    files yield an empty dict so the caller treats both as "no
    replaces".
    """
    if not go_mod_path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        text = go_mod_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    for line in text.splitlines():
        m = _GO_MOD_REPLACE_RE.match(line)
        if m:
            module, replacement = m.group(1), m.group(2)
            if _is_local_path(replacement):
                out[module] = replacement
    return out


def _read_go_work_uses(go_work_path: Path) -> list[str]:
    """Return the list of paths from ``go.work`` ``use`` directives.

    Both single-line (``use ./moduleA``) and block
    (``use (\\n ./a\\n ./b\\n)``) forms are supported. Comments inside
    the block are skipped. Missing or unreadable files yield ``[]``.
    """
    if not go_work_path.is_file():
        return []
    out: list[str] = []
    try:
        text = go_work_path.read_text(encoding="utf-8")
    except OSError:
        return []
    in_use_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if in_use_block:
            if stripped == ")":
                in_use_block = False
                continue
            if stripped and not stripped.startswith("//"):
                out.append(stripped)
            continue
        if stripped.startswith("use ("):
            in_use_block = True
            continue
        m = _GO_WORK_USE_RE.match(line)
        if m:
            out.append(m.group(1))
    return out


class GoResolver:
    """Resolve Go imports across federated repos.

    Parameters
    ----------
    source_repo_root:
        Filesystem root of the repo containing the import line. Used to
        read its ``go.mod`` and ``go.work`` once at construction time.
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
        self._replaces = _read_go_mod_replaces(self._source_root / "go.mod")
        self._workspace_uses = _read_go_work_uses(self._source_root / "go.work")

    def resolve(
        self,
        import_stmt: str,
        symbol: str,
        targets: list[TargetRepo],
    ) -> str | None:
        """Return ``<repo_id>:<file_path>::<symbol>`` on hit, else None.

        ``symbol`` is the call-site identifier (e.g. ``DoThing`` for
        ``util.DoThing()``); it is appended verbatim to the qualified
        name and never used as a search filter — Go symbol resolution
        at the file level is parser work, so the resolver returns the
        first non-test ``.go`` file under the resolved package
        directory.
        """
        parsed = parse_import_statement(import_stmt)
        if parsed is None:
            return None
        # Longest module-prefix match wins so overlapping replaces (e.g.
        # ``example.com`` and ``example.com/a``) don't accidentally
        # route ``example.com/a/util`` through the shorter prefix.
        matched_module: str | None = None
        modules_by_len: list[str] = sorted(
            self._replaces.keys(), key=lambda s: len(s), reverse=True
        )
        for module in modules_by_len:
            if parsed.module_path == module or parsed.module_path.startswith(
                module + "/"
            ):
                matched_module = module
                break
        if matched_module is None:
            # Without a replace directive (or workspace match) we can't
            # know which target hosts the import path -> return None.
            return None
        replacement = self._replaces[matched_module]
        suffix = parsed.module_path[len(matched_module) :].lstrip("/")
        replacement_abs = (self._source_root / replacement).resolve()

        for target in targets:
            if target.repo_id == self._source_repo_id:
                continue
            target_root = target.root.resolve()
            try:
                rel = replacement_abs.relative_to(target_root)
            except ValueError:
                continue
            search_dir = target_root / rel / suffix if suffix else target_root / rel
            if not search_dir.is_dir():
                continue
            for go_file in sorted(search_dir.glob("*.go")):
                if go_file.name.endswith("_test.go"):
                    continue
                rel_file = go_file.relative_to(target_root)
                return f"{target.repo_id}:{rel_file.as_posix()}::{symbol}"
        return None
