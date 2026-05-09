"""Tests for the Python cross-repo resolver (Phase 2 Task 3).

Covers :mod:`better_code_review_graph.resolver.python`:

* ``parse_import_statement`` — turns ``from X import Y`` / ``import X.Y``
  source lines into a structured :class:`PythonImport`.
* ``_read_dependencies`` — extracts and normalises top-level deps from
  ``[project.dependencies]`` in ``pyproject.toml``.
* ``PythonResolver.resolve`` — gates cross-repo edges by declared deps,
  walks PEP 420 namespace packages under each target repo, and returns
  ``<repo_id>:<file_path>::<symbol>`` qualified names on a hit.
"""

from __future__ import annotations

from pathlib import Path

from better_code_review_graph.resolver.python import (
    PythonImport,
    PythonResolver,
    TargetRepo,
    _read_dependencies,
    parse_import_statement,
)

# ---------------------------------------------------------------------------
# parse_import_statement
# ---------------------------------------------------------------------------


def test_parse_import_from_form() -> None:
    """``from lib_a.utils import retry`` -> module + name."""
    parsed = parse_import_statement("from lib_a.utils import retry")
    assert parsed == PythonImport(module="lib_a.utils", name="retry")


def test_parse_import_bare_form() -> None:
    """``import lib_a.utils`` -> module=lib_a, name=utils (last component)."""
    parsed = parse_import_statement("import lib_a.utils")
    assert parsed == PythonImport(module="lib_a", name="utils")


def test_parse_import_bare_top_level_only() -> None:
    """``import lib_a`` (no dot) -> module=lib_a, name=None."""
    parsed = parse_import_statement("import lib_a")
    assert parsed == PythonImport(module="lib_a", name=None)


def test_parse_import_garbage() -> None:
    """Non-import strings return None."""
    assert parse_import_statement("def foo(): pass") is None
    assert parse_import_statement("") is None
    assert parse_import_statement("    ") is None
    assert parse_import_statement("# from lib import x") is None


# ---------------------------------------------------------------------------
# _read_dependencies
# ---------------------------------------------------------------------------


def test_read_dependencies_normalizes_names(tmp_path: Path) -> None:
    """Lowercase + dash->underscore for PEP 503-ish normalisation."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        'name = "consumer"\n'
        'version = "0.0.0"\n'
        'dependencies = ["Some-Pkg>=1.0", "another_pkg", "third.pkg"]\n',
        encoding="utf-8",
    )
    deps = _read_dependencies(pyproject)
    assert deps == {"some_pkg", "another_pkg", "third.pkg"}


def test_read_dependencies_missing_file(tmp_path: Path) -> None:
    """Missing pyproject -> empty set, no exception."""
    deps = _read_dependencies(tmp_path / "nope.toml")
    assert deps == set()


def test_read_dependencies_invalid_toml(tmp_path: Path) -> None:
    """Garbled TOML -> empty set (caller treats as 'no declared deps')."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("this is not valid toml [[\n", encoding="utf-8")
    deps = _read_dependencies(pyproject)
    assert deps == set()


def test_read_dependencies_no_project_table(tmp_path: Path) -> None:
    """TOML without ``[project]`` is parsed but yields no deps."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.ruff]\nline-length = 88\n", encoding="utf-8")
    deps = _read_dependencies(pyproject)
    assert deps == set()


# ---------------------------------------------------------------------------
# PythonResolver.resolve — fixture builders
# ---------------------------------------------------------------------------


def _build_repo_a(tmp_path: Path) -> Path:
    """Create ``repo_a/src/lib_a/utils.py`` with a ``retry`` symbol."""
    repo_a = tmp_path / "repo_a"
    pkg = repo_a / "src" / "lib_a"
    pkg.mkdir(parents=True)
    (pkg / "utils.py").write_text("def retry():\n    pass\n", encoding="utf-8")
    # PEP 420 namespace package — no __init__.py at lib_a/.
    return repo_a


def _build_repo_b(tmp_path: Path, deps: list[str]) -> Path:
    """Create ``repo_b`` with a pyproject declaring ``deps``."""
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    deps_str = ", ".join(f'"{d}"' for d in deps)
    (repo_b / "pyproject.toml").write_text(
        f'[project]\nname = "repo_b"\nversion = "0.0.0"\ndependencies = [{deps_str}]\n',
        encoding="utf-8",
    )
    src = repo_b / "src" / "app"
    src.mkdir(parents=True)
    (src / "main.py").write_text(
        "from lib_a.utils import retry\n\nretry()\n",
        encoding="utf-8",
    )
    return repo_b


# ---------------------------------------------------------------------------
# PythonResolver.resolve — behaviour
# ---------------------------------------------------------------------------


def test_resolver_finds_target_via_namespace_package(tmp_path: Path) -> None:
    """The plan-required 2-repo fixture: cross-repo dep + namespace package."""
    repo_a = _build_repo_a(tmp_path)
    repo_b = _build_repo_b(tmp_path, deps=["lib_a"])

    resolver = PythonResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "from lib_a.utils import retry",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:src/lib_a/utils.py::retry"


def test_resolver_returns_none_for_undeclared_dep(tmp_path: Path) -> None:
    """No cross-repo edge unless the import top-level is in [project.dependencies]."""
    repo_a = _build_repo_a(tmp_path)
    # repo_b declares NO deps, so the import is not gated through.
    repo_b = _build_repo_b(tmp_path, deps=[])

    resolver = PythonResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "from lib_a.utils import retry",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_for_garbage_import(tmp_path: Path) -> None:
    """Unparseable import line -> None even with valid targets."""
    repo_a = _build_repo_a(tmp_path)
    repo_b = _build_repo_b(tmp_path, deps=["lib_a"])

    resolver = PythonResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    assert (
        resolver.resolve(
            "this is not an import",
            targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
        )
        is None
    )


def test_resolver_finds_via_init_py(tmp_path: Path) -> None:
    """When ``module/__init__.py`` exists instead of ``module.py``, still resolves."""
    repo_a = tmp_path / "repo_a"
    pkg = repo_a / "src" / "lib_a" / "utils"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("def retry():\n    pass\n", encoding="utf-8")
    repo_b = _build_repo_b(tmp_path, deps=["lib_a"])

    resolver = PythonResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "from lib_a.utils import retry",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:src/lib_a/utils/__init__.py::retry"


def test_resolver_skips_self_repo(tmp_path: Path) -> None:
    """A target with the same repo_id as source is skipped (no self-references)."""
    repo_a = _build_repo_a(tmp_path)
    repo_b = _build_repo_b(tmp_path, deps=["lib_a"])

    resolver = PythonResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_a_id",  # same as target below -> must be skipped
    )
    qualified = resolver.resolve(
        "from lib_a.utils import retry",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_when_no_target_has_file(tmp_path: Path) -> None:
    """Declared dep but the file isn't in any target -> None."""
    # Empty repo_a — no lib_a directory at all.
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    repo_b = _build_repo_b(tmp_path, deps=["lib_a"])

    resolver = PythonResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "from lib_a.utils import retry",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_handles_dotted_modules_correctly(tmp_path: Path) -> None:
    """``from a.b.c import d`` walks ``a/b/c.py``."""
    repo_a = tmp_path / "repo_a"
    pkg = repo_a / "src" / "a" / "b"
    pkg.mkdir(parents=True)
    (pkg / "c.py").write_text("def d():\n    pass\n", encoding="utf-8")

    repo_b = _build_repo_b(tmp_path, deps=["a"])

    resolver = PythonResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "from a.b.c import d",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:src/a/b/c.py::d"


def test_resolver_falls_back_to_bare_root_layout(tmp_path: Path) -> None:
    """Repos without ``src/`` layout still resolve from the repo root."""
    repo_a = tmp_path / "repo_a"
    pkg = repo_a / "lib_a"
    pkg.mkdir(parents=True)
    (pkg / "utils.py").write_text("def retry():\n    pass\n", encoding="utf-8")

    repo_b = _build_repo_b(tmp_path, deps=["lib_a"])

    resolver = PythonResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "from lib_a.utils import retry",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:lib_a/utils.py::retry"


def test_resolver_bare_import_returns_qualified_name(tmp_path: Path) -> None:
    """``import lib_a.utils`` parses as module=lib_a, name=utils -> resolves to package init/module."""
    repo_a = tmp_path / "repo_a"
    pkg = repo_a / "src" / "lib_a"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    repo_b = _build_repo_b(tmp_path, deps=["lib_a"])

    resolver = PythonResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import lib_a",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    # ``import lib_a`` with no dot has name=None; resolver falls back to
    # the last module component ("lib_a") as the symbol.
    assert qualified == "repo_a_id:src/lib_a/__init__.py::lib_a"
