"""Tier-2 fallback resolver (Phase 2 Task 8).

For languages without a dedicated resolver, attempt a best-effort match
by suffix scanning each target repo's source tree. Heuristic only —
intended for prototype federated graphs where one or two languages
appear that we don't yet have a dedicated parser/resolver for (Ruby,
PHP, C#, Swift, Scala, C/C++, ...).

The strategy:

1. Pull the longest qualified-name token (dotted, double-colon, or
   slash-separated) out of the raw import line.
2. Treat the last segment as the imported symbol name (unless the
   caller passes ``symbol`` explicitly — required for Go-like languages
   whose import line is path-only and the symbol comes from the call
   site).
3. Treat the leading segments as a relative file-path suffix and
   suffix-match each target repo's source files (``.py``, ``.ts``,
   ``.go``, ``.rs``, ``.java``, ``.rb``, ``.php``, ``.cs``, ``.swift``,
   ``.scala``, ``.cpp`` family).
4. Return the first hit per target, formatted as
   ``<repo_id>:<file>::<symbol>``.

The :func:`rglob` walk stops at the first matching file in each target
to keep performance bounded for large monorepos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ._types import TargetRepo

__all__ = [
    "FallbackResolver",
    "GenericImport",
    "TargetRepo",
    "parse_generic_qualified",
]


@dataclass(frozen=True)
class GenericImport:
    """Best-effort parse of a generic identifier-style import.

    ``qualified`` holds the longest dotted / double-colon / slash token
    pulled from the raw statement (e.g. ``"com.example.Util"``,
    ``"foo::bar::baz"``, or ``"foo/bar/baz"``).
    """

    qualified: str


# Match a single qualified token: word chars joined by `.`, `::`, or `/`.
# At least one separator is required so single identifiers don't match.
_GENERIC_QUALIFIED_RE = re.compile(r"(\w+(?:[.:/]+\w+)+)")


def parse_generic_qualified(stmt: str) -> GenericImport | None:
    """Pull the longest qualified token from ``stmt``.

    Recognises three flavours of separator: ``.`` (Java/Kotlin/C# /
    Scala / Swift), ``::`` (Rust/C++/Ruby constants/PHP namespaces),
    and ``/`` (Ruby ``require`` / PHP ``use`` paths). Multiple
    candidates in one line resolve to the longest by character count
    so a ``require_relative 'foo/bar'`` keeps ``foo/bar`` instead of
    a stray ``require_relative`` keyword fragment.

    Returns ``None`` for unqualified strings (no separator).
    """
    matches: list[str] = _GENERIC_QUALIFIED_RE.findall(stmt)
    if not matches:
        return None
    matches.sort(key=len, reverse=True)
    return GenericImport(qualified=matches[0])


# Common source-file extensions across mainstream languages we don't
# yet have a dedicated resolver for. ``.py``/``.ts`` etc are included
# for completeness — the dispatcher routes those to language-specific
# resolvers, but a tier-2 caller passing ``source_lang="python"`` to
# the fallback directly would still get a sensible suffix match.
_SOURCE_EXTS = (
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".rb",
    ".php",
    ".cs",
    ".swift",
    ".scala",
    ".cpp",
    ".cc",
    ".cxx",
    ".c",
    ".h",
    ".hpp",
    ".hxx",
)


class FallbackResolver:
    """Suffix-match resolver for tier-2 languages.

    Parameters
    ----------
    source_repo_root:
        Filesystem root of the repo containing the import line. Stored
        only so the resolver behaves symmetrically with language
        resolvers (it does not actually read the source repo — fallback
        is parser-shape agnostic).
    source_repo_id:
        Logical id of the source repo. Targets sharing this id are
        skipped during :meth:`resolve` so a target list including
        ``self`` never produces a self-referential edge.
    """

    def __init__(self, source_repo_root: Path, source_repo_id: str) -> None:
        self._source_root = source_repo_root.resolve()
        self._source_repo_id = source_repo_id

    def resolve(
        self,
        import_stmt: str,
        targets: list[TargetRepo],
        *,
        symbol: str | None = None,
    ) -> str | None:
        """Return ``<repo_id>:<file>::<symbol>`` on hit, else ``None``.

        ``symbol`` overrides the auto-derived last segment of the
        qualified name. Required when the import line is path-only
        (Go-like) and the actual symbol lives at the call site.
        """
        parsed = parse_generic_qualified(import_stmt)
        if parsed is None:
            return None
        # Split on any of the supported separators; collapse runs of
        # `::` or `..` so consecutive separators don't yield empty
        # segments.
        segments = [s for s in re.split(r"[.:/]+", parsed.qualified) if s]
        if not segments:  # pragma: no cover -- defensive; regex guarantees ≥1 segment
            return None
        candidate_symbol = symbol or segments[-1]
        # Suffix-match the full qualified token as a path. This works
        # for slash-style (``foo/bar`` -> ``foo/bar.rb`` matches
        # ``lib/foo/bar.rb``) and dotted/colon style alike
        # (``com.example.Util`` -> ``com/example/Util.java`` matches
        # ``src/main/java/com/example/Util.java``). The trailing
        # segment is treated as both the file basename AND the default
        # symbol; callers with stronger info pass ``symbol`` to
        # override the symbol while keeping the file match.
        path_parts = segments
        for target in targets:
            if target.repo_id == self._source_repo_id:
                continue
            target_root = target.root.resolve()
            for ext in _SOURCE_EXTS:
                expected_suffix = "/".join(path_parts) + ext
                # rglob is the cheapest way to walk every source file
                # of an extension; for prototype federated graphs the
                # target trees stay small enough for this to be fine.
                for candidate in target_root.rglob(f"*{ext}"):
                    if candidate.as_posix().endswith(expected_suffix):
                        rel = candidate.resolve().relative_to(target_root)
                        return f"{target.repo_id}:{rel.as_posix()}::{candidate_symbol}"
        return None
