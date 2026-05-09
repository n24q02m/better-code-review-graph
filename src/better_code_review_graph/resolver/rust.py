"""Rust cross-repo symbol resolver (Phase 2 Task 6).

Resolves Rust ``use crate_name::module::Symbol;`` style imports across
federated Cargo workspaces by:

1. Reading the source crate's ``Cargo.toml`` ``[dependencies]`` table
   for path keys (``foo = { path = "../foo" }``) — only path-based deps
   resolve cross-repo. Registry deps (``serde = "1.0"``) and git deps
   (``bar = { git = "..." }``) are filtered out because they don't
   point at a local sibling repo.
2. Reading ``[workspace.members]`` to identify workspace member crates
   when the source repo is itself a workspace root. Members are
   matched against the imported crate name via each member's
   ``[package] name`` field.
3. Walking each target repo's ``src/`` (Rust convention: ``src/lib.rs``,
   ``src/<module>.rs``, or ``src/<module>/mod.rs``) to find a matching
   ``.rs`` file.
4. Returning ``<target_repo_id>:<file>::<symbol>`` on a hit, else
   ``None``.

Single-repo (non-federated) mode is unaffected: when ``targets`` is
empty or no match is found, the resolver returns ``None`` and the
caller leaves the edge as a within-repo bare reference.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ._types import TargetRepo  # re-exported for backwards compatibility

__all__ = [
    "RustResolver",
    "RustUse",
    "TargetRepo",
    "parse_use_statement",
]


@dataclass(frozen=True)
class RustUse:
    """Parsed Rust ``use`` statement.

    ``crate`` is the leading path segment (the crate name as imported,
    e.g. ``foo`` from ``use foo::util::do_thing;``). ``module_path`` is
    the list of module segments between the crate and the final symbol
    (``["util"]`` for the example). ``symbol`` is the final segment
    (``do_thing``) and is what gets attached to the qualified-name
    output.
    """

    crate: str
    module_path: list[str]
    symbol: str


# ``use foo::util::do_thing;`` / ``pub use foo::Bar;`` / ``use foo::Bar as Baz;``
# Capture the ``::``-separated path; the ``as <alias>`` clause is
# accepted but discarded (only the original symbol matters for cross-
# repo resolution). The trailing ``;`` is optional so callers may strip
# it before passing the line in.
_USE_STMT_RE = re.compile(r"^\s*(?:pub\s+)?use\s+([\w:]+)\s*(?:as\s+\w+)?\s*;?\s*$")


def parse_use_statement(stmt: str) -> RustUse | None:
    """Parse a Rust ``use`` declaration. Returns ``None`` on garbage.

    Supported forms:

    * ``use foo::util::do_thing;`` -> ``crate='foo'``,
      ``module_path=['util']``, ``symbol='do_thing'``
    * ``use foo::Bar;`` -> ``crate='foo'``, ``module_path=[]``,
      ``symbol='Bar'``
    * ``pub use foo::util::do_thing;`` (re-export) — same parse.
    * ``use foo::Bar as Baz;`` — alias is dropped; we keep the
      original ``crate`` / ``symbol`` since the cross-repo edge points
      at the real definition.

    ``self::`` / ``super::`` / ``crate::`` references return ``None``
    because they target the current crate and never cross repos.
    Garbage lines (comments, declarations, anything not starting with
    a ``use``) also return ``None``.
    """
    m = _USE_STMT_RE.match(stmt)
    if m is None:
        return None
    parts = m.group(1).split("::")
    if len(parts) < 2:
        return None
    if parts[0] in ("self", "super", "crate"):
        return None
    crate = parts[0]
    symbol = parts[-1]
    module = parts[1:-1]
    return RustUse(crate=crate, module_path=module, symbol=symbol)


def _read_cargo_path_deps(cargo_toml: Path) -> dict[str, str]:
    """Return ``{crate_name: relative_path}`` for path-based deps.

    Filters out registry deps (string form, ``serde = "1.0"``) and git
    deps (inline-table without a ``path`` key,
    ``bar = { git = "..." }``). Both inline-table form
    (``foo = { path = "../foo" }``) and TOML-section form
    (``[dependencies.foo]\\npath = "../foo"``) are supported via
    :mod:`tomllib`. Missing files and unparseable TOML yield an empty
    dict so the caller treats both as "no path deps".
    """
    if not cargo_toml.is_file():
        return {}
    try:
        with cargo_toml.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out: dict[str, str] = {}
    deps = data.get("dependencies") or {}
    for name, spec in deps.items():
        if isinstance(spec, dict) and "path" in spec:
            out[str(name)] = str(spec["path"])
    return out


def _read_workspace_members(cargo_toml: Path) -> list[str]:
    """Return the ``[workspace] members`` glob list.

    Missing files, unparseable TOML, missing ``[workspace]`` section,
    and missing ``members`` key all yield an empty list so callers
    treat the source repo as "not a workspace root".
    """
    if not cargo_toml.is_file():
        return []
    try:
        with cargo_toml.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    workspace = data.get("workspace") or {}
    members = workspace.get("members") or []
    return [str(m) for m in members]


class RustResolver:
    """Resolve Rust ``use`` statements across federated repos.

    Parameters
    ----------
    source_repo_root:
        Filesystem root of the repo containing the ``use`` line. Used
        to read its ``Cargo.toml`` once at construction time for both
        ``[dependencies]`` path entries and ``[workspace.members]``.
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
        cargo = self._source_root / "Cargo.toml"
        self._path_deps = _read_cargo_path_deps(cargo)
        self._workspace_members = _read_workspace_members(cargo)

    def resolve(
        self,
        use_stmt: str,
        targets: list[TargetRepo],
    ) -> str | None:
        """Return ``<repo_id>:<file_path>::<symbol>`` on hit, else ``None``."""
        parsed = parse_use_statement(use_stmt)
        if parsed is None:
            return None
        # ``[dependencies]`` path entry takes priority over workspace-
        # member fallback so a deliberately-pinned path dep is never
        # shadowed by a same-named workspace member.
        if parsed.crate in self._path_deps:
            replacement_abs: Path | None = (
                self._source_root / self._path_deps[parsed.crate]
            ).resolve()
        else:
            # Search workspace members for one whose Cargo.toml
            # ``[package] name`` matches ``parsed.crate``. The workspace
            # member's directory name is allowed to differ from the
            # crate's package name (a common Rust convention), so we
            # must read each member's Cargo.toml rather than match the
            # member glob string directly.
            replacement_abs = None
            for member_glob in self._workspace_members:
                member_dir = (self._source_root / member_glob).resolve()
                if not member_dir.is_dir():
                    continue
                member_cargo = member_dir / "Cargo.toml"
                if not member_cargo.is_file():
                    continue
                try:
                    with member_cargo.open("rb") as f:
                        member_data = tomllib.load(f)
                except (OSError, tomllib.TOMLDecodeError):
                    continue
                pkg = member_data.get("package") or {}
                if pkg.get("name") == parsed.crate:
                    replacement_abs = member_dir
                    break
            if replacement_abs is None:
                return None

        # Find which registered target contains ``replacement_abs``.
        for target in targets:
            if target.repo_id == self._source_repo_id:
                continue
            target_root = target.root.resolve()
            try:
                replacement_abs.relative_to(target_root)
            except ValueError:
                continue
            return self._walk_crate(
                target.repo_id, target_root, replacement_abs, parsed
            )
        return None

    def _walk_crate(
        self,
        repo_id: str,
        target_root: Path,
        crate_root: Path,
        parsed: RustUse,
    ) -> str | None:
        """Find ``parsed.module_path`` under ``crate_root/src``.

        Three Rust module conventions are tried in order:

        * ``src/<m>.rs`` (single-file module)
        * ``src/<m>/mod.rs`` (directory module)
        * ``src/lib.rs`` when no module path is present
          (``use foo::Sym;`` -> symbol lives at the crate root).

        Returns the qualified name on the first hit; ``None`` when no
        candidate file exists.
        """
        src_dir = crate_root / "src"
        if not src_dir.is_dir():
            return None
        if not parsed.module_path:
            lib_rs = src_dir / "lib.rs"
            if lib_rs.is_file():
                rel = lib_rs.resolve().relative_to(target_root)
                return f"{repo_id}:{rel.as_posix()}::{parsed.symbol}"
            return None
        candidate_paths = [
            # ``src/<m>.rs`` direct file form.
            src_dir.joinpath(*parsed.module_path).with_suffix(".rs"),
            # ``src/<m>/mod.rs`` directory form.
            src_dir.joinpath(*parsed.module_path) / "mod.rs",
        ]
        for path in candidate_paths:
            if path.is_file():
                rel = path.resolve().relative_to(target_root)
                return f"{repo_id}:{rel.as_posix()}::{parsed.symbol}"
        return None
