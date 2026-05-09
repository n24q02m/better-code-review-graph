"""Cross-repo symbol resolver dispatcher (Phase 2 Task 8).

Routes :func:`resolve_cross_repo_imports` to the appropriate
language-specific resolver, with a generic suffix-match fallback for
tier-2 languages without dedicated support.

The canonical :class:`TargetRepo` dataclass lives in
:mod:`better_code_review_graph.resolver._types` and is re-exported by
this module and by every language resolver. Downstream callers should
import from this module (``from better_code_review_graph.resolver
import TargetRepo, resolve_cross_repo_imports``) to avoid coupling to a
specific resolver.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ._types import TargetRepo
from .fallback import FallbackResolver
from .go import GoResolver
from .java import JavaResolver
from .python import PythonResolver
from .rust import RustResolver
from .typescript import TypeScriptResolver

# Source language hint -> resolver class *attribute name on this module*.
# We dereference the attribute at call time (rather than caching the
# class object) so test patches on
# ``better_code_review_graph.resolver.PythonResolver`` (etc.) are
# honoured by the dispatcher.
#
# JavaScript reuses TypeScript because the import syntax and project
# layout (tsconfig paths + workspaces) are identical. Kotlin reuses
# Java because Maven/Gradle module structure is shared and the
# JavaResolver already walks ``src/main/kotlin``.
_RESOLVERS: dict[str, str] = {
    "python": "PythonResolver",
    "typescript": "TypeScriptResolver",
    "javascript": "TypeScriptResolver",
    "go": "GoResolver",
    "rust": "RustResolver",
    "java": "JavaResolver",
    "kotlin": "JavaResolver",
}


def resolve_cross_repo_imports(
    import_stmt: str,
    source_lang: str,
    source_repo_root: Path,
    source_repo_id: str,
    targets: list[TargetRepo],
    *,
    symbol: str | None = None,
) -> str | None:
    """Resolve a cross-repo import statement.

    Dispatches based on ``source_lang`` (lower-cased and stripped).
    Falls back to the suffix-match :class:`FallbackResolver` when no
    language-specific resolver is registered.

    Parameters
    ----------
    import_stmt:
        The raw import line as captured by the parser
        (``"from lib_a.utils import retry"``, ``"import \"foo/bar\""``,
        ``"use foo::bar::Baz;"``, ...).
    source_lang:
        Language hint (case-insensitive). Maps to a tier-1 resolver
        class via the dispatch table; unknown values route to
        ``FallbackResolver``.
    source_repo_root, source_repo_id:
        Forwarded verbatim to the resolver constructor.
    targets:
        Federated repo targets. The resolver skips any target whose id
        matches ``source_repo_id`` so self-references can't sneak in.
    symbol:
        Required by Go (whose imports are path-only — the symbol comes
        from the call site) and by the fallback resolver when the
        caller has stronger information than the trailing segment of
        the qualified name. Ignored by the other tier-1 resolvers.
    """
    lang = source_lang.lower().strip()
    cls_name = _RESOLVERS.get(lang)
    module = sys.modules[__name__]
    if cls_name is None:
        fallback_cls = module.FallbackResolver
        resolver = fallback_cls(source_repo_root, source_repo_id)
        return resolver.resolve(import_stmt, targets, symbol=symbol)
    resolver_cls = getattr(module, cls_name)
    if cls_name == "GoResolver":
        # Go uniquely requires the symbol param — without it we cannot
        # build the qualified name, so short-circuit to None rather
        # than hand a placeholder back to the caller.
        if symbol is None:
            return None
        return resolver_cls(source_repo_root, source_repo_id).resolve(
            import_stmt, symbol, targets
        )
    resolver = resolver_cls(source_repo_root, source_repo_id)
    return resolver.resolve(import_stmt, targets)


__all__ = [
    "FallbackResolver",
    "GoResolver",
    "JavaResolver",
    "PythonResolver",
    "RustResolver",
    "TargetRepo",
    "TypeScriptResolver",
    "resolve_cross_repo_imports",
]
