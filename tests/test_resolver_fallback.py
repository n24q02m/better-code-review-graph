"""Tests for the tier-2 fallback resolver (Phase 2 Task 8).

Covers :mod:`better_code_review_graph.resolver.fallback`:

* :func:`parse_generic_qualified` — extracts the longest qualified
  token from a raw import line, recognising dotted, double-colon and
  slash separators.
* :class:`FallbackResolver.resolve` — suffix-matches the qualified
  token against each target repo's source tree, skips the source repo,
  and threads through an explicit ``symbol`` override when provided.
"""

from __future__ import annotations

from pathlib import Path

from better_code_review_graph.resolver import (
    TargetRepo,
    resolve_cross_repo_imports,
)
from better_code_review_graph.resolver.fallback import (
    FallbackResolver,
    GenericImport,
    parse_generic_qualified,
)

# ---------------------------------------------------------------------------
# parse_generic_qualified
# ---------------------------------------------------------------------------


def test_parse_generic_qualified_dot_notation() -> None:
    """``import com.example.Util`` extracts ``com.example.Util``."""
    parsed = parse_generic_qualified("import com.example.Util")
    assert parsed == GenericImport(qualified="com.example.Util")


def test_parse_generic_qualified_double_colon() -> None:
    """``use foo::bar::baz`` extracts ``foo::bar::baz``."""
    parsed = parse_generic_qualified("use foo::bar::baz")
    assert parsed == GenericImport(qualified="foo::bar::baz")


def test_parse_generic_qualified_slash() -> None:
    """``require 'foo/bar/baz'`` extracts ``foo/bar/baz``."""
    parsed = parse_generic_qualified("require 'foo/bar/baz'")
    assert parsed == GenericImport(qualified="foo/bar/baz")


def test_parse_generic_qualified_picks_longest() -> None:
    """Multiple qualified tokens in one string -> longest wins."""
    # ``a.b`` (3 chars) vs ``foo.bar.baz`` (11 chars) -> longest wins.
    parsed = parse_generic_qualified("from a.b take foo.bar.baz")
    assert parsed == GenericImport(qualified="foo.bar.baz")


def test_parse_generic_qualified_garbage() -> None:
    """Unqualified strings (no separator) return ``None``."""
    assert parse_generic_qualified("not_a_qualified_name") is None
    assert parse_generic_qualified("") is None
    assert parse_generic_qualified("just words here") is None


# ---------------------------------------------------------------------------
# FallbackResolver.resolve — fixture builders
# ---------------------------------------------------------------------------


def _build_ruby_target(tmp_path: Path) -> Path:
    """Create ``repo_a/lib/foo/bar.rb`` with a ``Bar`` class."""
    repo_a = tmp_path / "repo_a"
    pkg = repo_a / "lib" / "foo"
    pkg.mkdir(parents=True)
    (pkg / "bar.rb").write_text("class Bar\nend\n", encoding="utf-8")
    return repo_a


def _build_source_repo(tmp_path: Path) -> Path:
    """Create an empty source repo (fallback doesn't read source config)."""
    repo = tmp_path / "source"
    repo.mkdir()
    return repo


# ---------------------------------------------------------------------------
# FallbackResolver.resolve — behaviour
# ---------------------------------------------------------------------------


def test_fallback_resolver_finds_via_suffix_match(tmp_path: Path) -> None:
    """Plan-required spec: tier-2 fixture with Ruby file resolves via suffix.

    Build ``repo_a/lib/foo/bar.rb``, source repo with no resolver
    registered for ``"ruby"``. Calling ``resolve_cross_repo_imports``
    routes to the fallback and returns the suffix-matched qualified
    name with the explicit ``symbol`` override.
    """
    repo_a = _build_ruby_target(tmp_path)
    source = _build_source_repo(tmp_path)
    qualified = resolve_cross_repo_imports(
        "require 'foo/bar'",
        "ruby",
        source,
        "source_id",
        [TargetRepo(repo_id="repo_a_id", root=repo_a)],
        symbol="Bar",
    )
    assert qualified == "repo_a_id:lib/foo/bar.rb::Bar"


def test_fallback_resolver_skips_self_repo(tmp_path: Path) -> None:
    """A target whose ``repo_id`` matches the source is skipped."""
    repo_a = _build_ruby_target(tmp_path)
    source = _build_source_repo(tmp_path)
    resolver = FallbackResolver(source, "repo_a_id")
    qualified = resolver.resolve(
        "require 'foo/bar'",
        [TargetRepo(repo_id="repo_a_id", root=repo_a)],
        symbol="Bar",
    )
    assert qualified is None


def test_fallback_resolver_returns_none_when_no_match(tmp_path: Path) -> None:
    """No matching file in any target -> ``None``."""
    repo_a = _build_ruby_target(tmp_path)
    source = _build_source_repo(tmp_path)
    resolver = FallbackResolver(source, "source_id")
    qualified = resolver.resolve(
        "require 'nonexistent/path'",
        [TargetRepo(repo_id="repo_a_id", root=repo_a)],
        symbol="Whatever",
    )
    assert qualified is None


def test_fallback_resolver_uses_symbol_kwarg_when_provided(tmp_path: Path) -> None:
    """Explicit ``symbol`` override beats the auto-derived last segment."""
    repo_a = _build_ruby_target(tmp_path)
    source = _build_source_repo(tmp_path)
    resolver = FallbackResolver(source, "source_id")
    # Without ``symbol`` the parser would treat ``bar`` as the symbol;
    # passing ``"Bar"`` overrides that to use the actual class name.
    qualified = resolver.resolve(
        "require 'foo/bar'",
        [TargetRepo(repo_id="repo_a_id", root=repo_a)],
        symbol="Bar",
    )
    assert qualified == "repo_a_id:lib/foo/bar.rb::Bar"

    # Without the kwarg the symbol falls back to the last segment.
    qualified_default = resolver.resolve(
        "require 'foo/bar'",
        [TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified_default == "repo_a_id:lib/foo/bar.rb::bar"


def test_fallback_resolver_returns_none_for_unparseable_stmt(tmp_path: Path) -> None:
    """Statement with no qualified token at all -> ``None``."""
    repo_a = _build_ruby_target(tmp_path)
    source = _build_source_repo(tmp_path)
    resolver = FallbackResolver(source, "source_id")
    qualified = resolver.resolve(
        "no qualified token here",
        [TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None
