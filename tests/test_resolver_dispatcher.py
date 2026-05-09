"""Tests for the cross-repo resolver dispatcher (Phase 2 Task 8).

Covers :func:`better_code_review_graph.resolver.resolve_cross_repo_imports`:

* Dispatch table — Python / TypeScript / JavaScript / Go / Rust / Java
  / Kotlin all route to the expected resolver class.
* Case-insensitive ``source_lang`` handling.
* Tier-2 fallback for unknown languages.
* Go-specific ``symbol`` plumbing — without a symbol the dispatcher
  returns ``None`` because the call-site identifier is required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from better_code_review_graph.resolver import (
    FallbackResolver,
    GoResolver,
    JavaResolver,
    PythonResolver,
    RustResolver,
    TargetRepo,
    TypeScriptResolver,
    resolve_cross_repo_imports,
)

# ---------------------------------------------------------------------------
# Fixture: minimal source repos so each resolver constructor succeeds.
# ---------------------------------------------------------------------------


def _make_source_repo(tmp_path: Path) -> Path:
    """Create an empty repo dir; resolver constructors only need it to exist."""
    src = tmp_path / "source_repo"
    src.mkdir()
    return src


def _make_target(tmp_path: Path, name: str = "target_repo") -> TargetRepo:
    root = tmp_path / name
    root.mkdir()
    return TargetRepo(repo_id=f"{name}_id", root=root)


# ---------------------------------------------------------------------------
# Dispatch table — verifies the correct resolver class is instantiated and
# its ``resolve`` method is invoked. We patch the class on the dispatcher
# module so we can both assert the call and short-circuit the actual walk.
# ---------------------------------------------------------------------------


def test_dispatcher_routes_python(tmp_path: Path) -> None:
    """``source_lang='python'`` instantiates ``PythonResolver`` and forwards."""
    source = _make_source_repo(tmp_path)
    target = _make_target(tmp_path)
    with patch(
        "better_code_review_graph.resolver.PythonResolver",
        wraps=PythonResolver,
    ) as cls:
        result = resolve_cross_repo_imports(
            "from lib_a import x",
            "python",
            source,
            "source_id",
            [target],
        )
    cls.assert_called_once_with(source, "source_id")
    assert result is None  # no pyproject = no declared dep -> None


def test_dispatcher_routes_typescript(tmp_path: Path) -> None:
    """``source_lang='typescript'`` routes to ``TypeScriptResolver``."""
    source = _make_source_repo(tmp_path)
    target = _make_target(tmp_path)
    with patch(
        "better_code_review_graph.resolver.TypeScriptResolver",
        wraps=TypeScriptResolver,
    ) as cls:
        resolve_cross_repo_imports(
            "import { x } from '@/lib/util'",
            "typescript",
            source,
            "source_id",
            [target],
        )
    cls.assert_called_once_with(source, "source_id")


def test_dispatcher_routes_javascript_to_typescript(tmp_path: Path) -> None:
    """``source_lang='javascript'`` shares the TypeScript resolver."""
    source = _make_source_repo(tmp_path)
    target = _make_target(tmp_path)
    with patch(
        "better_code_review_graph.resolver.TypeScriptResolver",
        wraps=TypeScriptResolver,
    ) as cls:
        resolve_cross_repo_imports(
            "import { x } from 'lib/util'",
            "javascript",
            source,
            "source_id",
            [target],
        )
    cls.assert_called_once_with(source, "source_id")


def test_dispatcher_routes_go(tmp_path: Path) -> None:
    """``source_lang='go'`` routes to ``GoResolver`` and forwards ``symbol``."""
    source = _make_source_repo(tmp_path)
    target = _make_target(tmp_path)
    with patch(
        "better_code_review_graph.resolver.GoResolver",
        wraps=GoResolver,
    ) as cls:
        result = resolve_cross_repo_imports(
            'import "example.com/a/util"',
            "go",
            source,
            "source_id",
            [target],
            symbol="DoThing",
        )
    cls.assert_called_once_with(source, "source_id")
    # No go.mod replace -> resolver returns None even with symbol.
    assert result is None


def test_dispatcher_routes_rust(tmp_path: Path) -> None:
    """``source_lang='rust'`` routes to ``RustResolver``."""
    source = _make_source_repo(tmp_path)
    target = _make_target(tmp_path)
    with patch(
        "better_code_review_graph.resolver.RustResolver",
        wraps=RustResolver,
    ) as cls:
        resolve_cross_repo_imports(
            "use foo::util::do_thing;",
            "rust",
            source,
            "source_id",
            [target],
        )
    cls.assert_called_once_with(source, "source_id")


def test_dispatcher_routes_java(tmp_path: Path) -> None:
    """``source_lang='java'`` routes to ``JavaResolver``."""
    source = _make_source_repo(tmp_path)
    target = _make_target(tmp_path)
    with patch(
        "better_code_review_graph.resolver.JavaResolver",
        wraps=JavaResolver,
    ) as cls:
        resolve_cross_repo_imports(
            "import com.example.a.Util;",
            "java",
            source,
            "source_id",
            [target],
        )
    cls.assert_called_once_with(source, "source_id")


def test_dispatcher_routes_kotlin_to_java(tmp_path: Path) -> None:
    """``source_lang='kotlin'`` shares the Java resolver."""
    source = _make_source_repo(tmp_path)
    target = _make_target(tmp_path)
    with patch(
        "better_code_review_graph.resolver.JavaResolver",
        wraps=JavaResolver,
    ) as cls:
        resolve_cross_repo_imports(
            "import com.example.a.Util",
            "kotlin",
            source,
            "source_id",
            [target],
        )
    cls.assert_called_once_with(source, "source_id")


def test_dispatcher_falls_back_for_unknown_lang(tmp_path: Path) -> None:
    """``source_lang='ruby'`` (not in the table) routes to ``FallbackResolver``."""
    source = _make_source_repo(tmp_path)
    target = _make_target(tmp_path)
    with patch(
        "better_code_review_graph.resolver.FallbackResolver",
        wraps=FallbackResolver,
    ) as cls:
        resolve_cross_repo_imports(
            "require 'foo/bar'",
            "ruby",
            source,
            "source_id",
            [target],
        )
    cls.assert_called_once_with(source, "source_id")


def test_dispatcher_lang_is_case_insensitive(tmp_path: Path) -> None:
    """``'Python'`` and ``'PYTHON'`` both hit the python resolver."""
    source = _make_source_repo(tmp_path)
    target = _make_target(tmp_path)
    for variant in ("Python", "PYTHON", "  python  "):
        with patch(
            "better_code_review_graph.resolver.PythonResolver",
            wraps=PythonResolver,
        ) as cls:
            resolve_cross_repo_imports(
                "from lib import x",
                variant,
                source,
                "source_id",
                [target],
            )
        cls.assert_called_once_with(source, "source_id")


def test_dispatcher_go_without_symbol_returns_none(tmp_path: Path) -> None:
    """Go cannot resolve without a symbol — dispatcher short-circuits to None."""
    source = _make_source_repo(tmp_path)
    target = _make_target(tmp_path)
    with patch(
        "better_code_review_graph.resolver.GoResolver",
        wraps=GoResolver,
    ) as cls:
        result = resolve_cross_repo_imports(
            'import "example.com/a/util"',
            "go",
            source,
            "source_id",
            [target],
            # symbol omitted on purpose.
        )
    assert result is None
    # GoResolver should NOT have been instantiated when symbol is missing.
    cls.assert_not_called()
