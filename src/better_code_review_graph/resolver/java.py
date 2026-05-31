"""Java cross-repo symbol resolver (Phase 2 Task 7).

Resolves Java imports across multi-module Maven and Gradle projects by:

1. Reading the source repo's ``pom.xml`` for ``<modules>`` declarations
   (Maven multi-module project) — module names are subdirectory names.
2. Reading ``settings.gradle`` / ``settings.gradle.kts`` for
   ``include 'a'`` / ``include(":a")`` declarations.
3. Walking each target repo's standard layout
   (``<module>/src/main/java/<package>/<Class>.java``) to find the
   matching source file. Kotlin sources (``src/main/kotlin/.../Class.kt``)
   are also recognised so mixed Java/Kotlin modules resolve.
4. Returning ``<target_repo_id>:<file>::<symbol>`` on a hit, else
   ``None``.

The module name is derived per Maven convention: each ``<modules>``
entry is the relative path to a module directory; that directory is
what we walk. For Gradle, ``include`` paths (``:a:b``) are mapped to
filesystem paths (``a/b``) since Gradle uses ``:`` for nested project
names.

Single-repo (non-federated) mode is unaffected: when ``targets`` is
empty or no match is found, the resolver returns ``None`` and the
caller leaves the edge as a within-repo bare reference.
"""

from __future__ import annotations

import re
import defusedxml.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ._types import TargetRepo  # re-exported for backwards compatibility

__all__ = [
    "JavaImport",
    "JavaResolver",
    "TargetRepo",
    "parse_import_statement",
]


@dataclass(frozen=True)
class JavaImport:
    """Parsed Java import statement.

    ``import com.example.a.Util;`` -> ``qualified='com.example.a.Util'``,
    ``package='com.example.a'``, ``class_name='Util'``.

    For ``import static com.example.a.Util.foo;`` the trailing
    identifier (``foo``) becomes ``class_name`` — this is intentional:
    the resolver uses ``class_name`` purely as the qualified-name
    suffix, and the package walk targets the path derived from
    ``package`` (``com/example/a/Util`` directory or
    ``com/example/a/Util.java`` is not searched — the static-member
    case naturally degrades to a no-match unless a class literally
    named ``foo`` exists in that package, which is fine).
    """

    qualified: str
    package: str
    class_name: str


# Match ``import com.example.a.Util;`` (semicolon optional so callers
# may strip it before passing the line in) and the ``import static ...``
# variant. The qualified path captures dotted identifiers only.
_IMPORT_STMT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;?\s*$")
# ``include 'a'`` / ``include('a')`` / ``include(":a")`` / single token
# in a multi-include line (``include 'a', 'b'`` matches twice). The
# leading ``:`` is optional and stripped by the caller.
_GRADLE_INCLUDE_RE = re.compile(r"""include\s*\(?\s*['"]:?([\w.\-/:]+)['"]\s*\)?""")
# pom.xml uses an XML namespace by default — register it once and try
# the namespaced query first; a non-namespaced fallback handles legacy
# POMs that omit ``xmlns``.
_MAVEN_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


def parse_import_statement(stmt: str) -> JavaImport | None:
    """Parse ``import com.example.a.Util;`` (or ``import static ...``).

    Returns ``None`` for non-import lines, comments, package
    declarations, and any qualified path without at least one ``.``
    (no package -> nothing to walk to).
    """
    m = _IMPORT_STMT_RE.match(stmt)
    if m is None:
        return None
    qualified = m.group(1)
    if "." not in qualified:
        return None
    package, _, class_name = qualified.rpartition(".")
    if not package or not class_name:
        return None
    return JavaImport(qualified=qualified, package=package, class_name=class_name)


def _read_pom_modules(pom_path: Path) -> list[str]:
    """Return ``<modules>`` entries from pom.xml.

    Tries the namespaced XPath ``m:modules/m:module`` first (per the
    Maven 4.0.0 default ``xmlns``), then falls back to the unqualified
    ``modules/module`` XPath for legacy POMs that omit ``xmlns``.
    Missing files and unparseable XML yield an empty list so the
    caller treats both as "no modules".
    """
    if not pom_path.is_file():
        return []
    try:
        tree = ET.parse(pom_path)
    except (OSError, ET.ParseError):
        return []
    root = tree.getroot()
    out: list[str] = []
    modules = root.findall("m:modules/m:module", _MAVEN_NS)
    if not modules:
        modules = root.findall("modules/module")
    for m in modules:
        if m.text:
            out.append(m.text.strip())
    return out


def _read_gradle_includes(settings_path: Path) -> list[str]:
    """Return ``include`` entries from settings.gradle / settings.gradle.kts.

    Handles ``include 'a'``, ``include('a')``, ``include(":a")``, and
    multi-name lines like ``include 'a', 'b'`` — the regex iterates
    once per quoted token. Leading ``:`` is stripped and Gradle's
    ``:`` separator (``:parent:child``) is converted to ``/`` so the
    result is a filesystem-relative path.
    """
    if not settings_path.is_file():
        return []
    try:
        text = settings_path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[str] = []
    for m in _GRADLE_INCLUDE_RE.finditer(text):
        # Strip leading ``:`` if present and convert remaining ``:`` to
        # ``/`` (Gradle uses ``:a:b`` for nested project names; the
        # filesystem path is ``a/b``).
        name = m.group(1).lstrip(":").replace(":", "/")
        out.append(name)
    return out


class JavaResolver:
    """Resolve Java imports across multi-module Maven/Gradle projects.

    Parameters
    ----------
    source_repo_root:
        Filesystem root of the repo containing the import line. Used to
        read its ``pom.xml`` and (failing that) ``settings.gradle`` /
        ``settings.gradle.kts`` once at construction time. The source's
        own module map is exposed via private attributes for the
        parser stage to consume; :meth:`resolve` itself does not use
        it because the resolver walks every target's modules.
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
        # Read source's modules list — used here for completeness (the
        # parser stage may want to know the module map). Not consumed
        # by :meth:`resolve` itself.
        self._maven_modules = _read_pom_modules(self._source_root / "pom.xml")
        self._gradle_modules: list[str] = []
        for settings in ("settings.gradle.kts", "settings.gradle"):
            path = self._source_root / settings
            if path.is_file():
                self._gradle_modules = _read_gradle_includes(path)
                break

    def resolve(
        self,
        import_stmt: str,
        targets: list[TargetRepo],
    ) -> str | None:
        """Return ``<repo_id>:<file_path>::<symbol>`` on hit, else ``None``."""
        parsed = parse_import_statement(import_stmt)
        if parsed is None:
            return None
        for target in targets:
            if target.repo_id == self._source_repo_id:
                continue
            target_root = target.root.resolve()
            target_modules = _read_pom_modules(target_root / "pom.xml")
            if not target_modules:
                # Try Gradle, preferring the kts variant when both
                # exist (matches the source-side construction order).
                for settings in ("settings.gradle.kts", "settings.gradle"):
                    settings_path = target_root / settings
                    if settings_path.is_file():
                        target_modules = _read_gradle_includes(settings_path)
                        break
            # Single-module project: walk target_root directly so flat
            # repos (no parent pom + no Gradle settings) still resolve.
            module_dirs = (
                [target_root / m for m in target_modules]
                if target_modules
                else [target_root]
            )
            for module_dir in module_dirs:
                hit = self._walk_module(target.repo_id, target_root, module_dir, parsed)
                if hit is not None:
                    return hit
        return None

    def _walk_module(
        self,
        repo_id: str,
        target_root: Path,
        module_dir: Path,
        parsed: JavaImport,
    ) -> str | None:
        """Look for ``<module>/src/main/java/<pkg>/<Class>.java`` (and friends).

        Three Java/Kotlin source layouts are tried in order:

        * ``src/main/java/<pkg>/<Class>.java``
        * ``src/main/kotlin/<pkg>/<Class>.kt``
        * ``src/test/java/<pkg>/<Class>.java``

        Within each layout the resolver probes ``.java`` first then
        ``.kt`` so a Java class always wins when both exist (a defensive
        choice — most mixed-language projects have a ``.java``
        canonical and a ``.kt`` shim, not the reverse). Returns the
        qualified name on the first hit; ``None`` when no candidate
        file exists.
        """
        package_path = parsed.package.replace(".", "/")
        for layout in ("src/main/java", "src/main/kotlin", "src/test/java"):
            file_path = module_dir / layout / package_path / f"{parsed.class_name}.java"
            if file_path.is_file():
                rel = file_path.resolve().relative_to(target_root)
                return f"{repo_id}:{rel.as_posix()}::{parsed.class_name}"
            kt_path = module_dir / layout / package_path / f"{parsed.class_name}.kt"
            if kt_path.is_file():
                rel = kt_path.resolve().relative_to(target_root)
                return f"{repo_id}:{rel.as_posix()}::{parsed.class_name}"
        return None
