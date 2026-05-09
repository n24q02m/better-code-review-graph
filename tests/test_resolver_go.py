"""Tests for the Go cross-repo resolver (Phase 2 Task 5).

Covers :mod:`better_code_review_graph.resolver.go`:

* ``parse_import_statement`` — turns ``import "example.com/a/util"`` /
  ``import u "example.com/a/util"`` / single-line block form lines
  into a :class:`GoImport`.
* ``_read_go_mod_replaces`` — extracts ``replace ... => ...`` directives
  from ``go.mod``, keeping only local-path replacements.
* ``_read_go_work_uses`` — extracts ``use ./modulePath`` declarations
  from ``go.work`` (single-line + block forms).
* ``GoResolver.resolve`` — applies the replace map to map an import
  path onto a target repo's filesystem and returns
  ``<repo_id>:<file_path>::<symbol>`` qualified names on a hit.
"""

from __future__ import annotations

from pathlib import Path

from better_code_review_graph.resolver.go import (
    GoImport,
    GoResolver,
    TargetRepo,
    _read_go_mod_replaces,
    _read_go_work_uses,
    parse_import_statement,
)

# ---------------------------------------------------------------------------
# parse_import_statement
# ---------------------------------------------------------------------------


def test_parse_import_simple() -> None:
    """``import "example.com/a/util"`` -> module_path set, alias=None."""
    parsed = parse_import_statement('import "example.com/a/util"')
    assert parsed == GoImport(module_path="example.com/a/util", alias=None)


def test_parse_import_aliased() -> None:
    """``import u "example.com/a/util"`` -> alias='u'."""
    parsed = parse_import_statement('import u "example.com/a/util"')
    assert parsed == GoImport(module_path="example.com/a/util", alias="u")


def test_parse_import_inside_block() -> None:
    """A bare ``"example.com/a/util"`` (single line of an import block) parses."""
    parsed = parse_import_statement('    "example.com/a/util"')
    assert parsed == GoImport(module_path="example.com/a/util", alias=None)


def test_parse_import_aliased_inside_block() -> None:
    """``    u "example.com/a/util"`` (aliased line of an import block) parses."""
    parsed = parse_import_statement('    u "example.com/a/util"')
    assert parsed == GoImport(module_path="example.com/a/util", alias="u")


def test_parse_import_garbage() -> None:
    """Non-import strings return None."""
    assert parse_import_statement("func foo() {}") is None
    assert parse_import_statement("") is None
    assert parse_import_statement("    ") is None
    assert parse_import_statement('// import "example.com/a"') is None
    assert parse_import_statement("package main") is None


# ---------------------------------------------------------------------------
# _read_go_mod_replaces
# ---------------------------------------------------------------------------


def test_read_go_mod_replaces_local_path(tmp_path: Path) -> None:
    """``replace example.com/a => ../a`` -> {'example.com/a': '../a'}."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """module example.com/b

go 1.22

replace example.com/a => ../a
""",
        encoding="utf-8",
    )
    assert _read_go_mod_replaces(go_mod) == {"example.com/a": "../a"}


def test_read_go_mod_replaces_with_versions(tmp_path: Path) -> None:
    """``replace example.com/a v1.0 => ../a v1.0`` parses to local path."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """module example.com/b

go 1.22

replace example.com/a v1.0.0 => ../a v1.0.0
""",
        encoding="utf-8",
    )
    assert _read_go_mod_replaces(go_mod) == {"example.com/a": "../a"}


def test_read_go_mod_replaces_filters_module_to_module(tmp_path: Path) -> None:
    """Module-to-module replaces (no ./ ../ / prefix) are filtered out."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """module example.com/b

go 1.22

replace example.com/a => other.com/a v1.0.0
replace example.com/c => ../c
""",
        encoding="utf-8",
    )
    # Only the local-path replace survives.
    assert _read_go_mod_replaces(go_mod) == {"example.com/c": "../c"}


def test_read_go_mod_replaces_missing_file(tmp_path: Path) -> None:
    """Missing go.mod -> empty dict, no exception."""
    assert _read_go_mod_replaces(tmp_path / "nope.mod") == {}


def test_read_go_mod_replaces_absolute_posix_path(tmp_path: Path) -> None:
    """POSIX-absolute path (``/srv/a``) is recognised as local."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        "replace example.com/a => /srv/a\n",
        encoding="utf-8",
    )
    assert _read_go_mod_replaces(go_mod) == {"example.com/a": "/srv/a"}


def test_read_go_mod_replaces_windows_drive_path(tmp_path: Path) -> None:
    """Windows drive-letter path (``C:/code/a``) is recognised as local."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        "replace example.com/a => C:/code/a\n",
        encoding="utf-8",
    )
    assert _read_go_mod_replaces(go_mod) == {"example.com/a": "C:/code/a"}


def test_read_go_mod_replaces_ignores_unrelated_lines(tmp_path: Path) -> None:
    """Non-replace lines (require, exclude, comments) are ignored."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """module example.com/b

go 1.22

require example.com/c v1.0.0
// replace example.com/d => ../d
exclude example.com/e v1.0.0

replace example.com/a => ../a
""",
        encoding="utf-8",
    )
    assert _read_go_mod_replaces(go_mod) == {"example.com/a": "../a"}


# ---------------------------------------------------------------------------
# _read_go_work_uses
# ---------------------------------------------------------------------------


def test_read_go_work_uses_single_use(tmp_path: Path) -> None:
    """``use ./moduleA`` -> ['./moduleA']."""
    go_work = tmp_path / "go.work"
    go_work.write_text(
        """go 1.22

use ./moduleA
""",
        encoding="utf-8",
    )
    assert _read_go_work_uses(go_work) == ["./moduleA"]


def test_read_go_work_uses_block(tmp_path: Path) -> None:
    """``use (\\n  ./a\\n  ./b\\n)`` -> ['./a', './b']."""
    go_work = tmp_path / "go.work"
    go_work.write_text(
        """go 1.22

use (
  ./a
  ./b
)
""",
        encoding="utf-8",
    )
    assert _read_go_work_uses(go_work) == ["./a", "./b"]


def test_read_go_work_uses_block_with_comments(tmp_path: Path) -> None:
    """Block form skips ``//`` comment lines inside ``use (...)``."""
    go_work = tmp_path / "go.work"
    go_work.write_text(
        """go 1.22

use (
  ./a
  // skip me
  ./b
)
""",
        encoding="utf-8",
    )
    assert _read_go_work_uses(go_work) == ["./a", "./b"]


def test_read_go_work_uses_missing_file(tmp_path: Path) -> None:
    """Missing go.work -> empty list, no exception."""
    assert _read_go_work_uses(tmp_path / "nope.work") == []


def test_read_go_work_uses_combined_single_and_block(tmp_path: Path) -> None:
    """Single-line ``use`` and a block can coexist in the same file."""
    go_work = tmp_path / "go.work"
    go_work.write_text(
        """go 1.22

use ./standalone

use (
  ./a
  ./b
)
""",
        encoding="utf-8",
    )
    assert _read_go_work_uses(go_work) == ["./standalone", "./a", "./b"]


# ---------------------------------------------------------------------------
# GoResolver.resolve — fixtures + integration
# ---------------------------------------------------------------------------


def _build_repo_a_with_util(tmp_path: Path) -> Path:
    """Create ``repo_a`` with ``util/util.go`` containing ``DoThing``."""
    repo_a = tmp_path / "repo_a"
    util = repo_a / "util"
    util.mkdir(parents=True)
    (util / "util.go").write_text(
        """package util

func DoThing() {}
""",
        encoding="utf-8",
    )
    (repo_a / "go.mod").write_text(
        "module example.com/a\n\ngo 1.22\n",
        encoding="utf-8",
    )
    return repo_a


def _build_repo_b_with_replace(
    tmp_path: Path, replace_target: str = "../repo_a"
) -> Path:
    """Create ``repo_b`` with go.mod replacing ``example.com/a`` to ``../repo_a``."""
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "go.mod").write_text(
        f"""module example.com/b

go 1.22

require example.com/a v0.0.0

replace example.com/a => {replace_target}
""",
        encoding="utf-8",
    )
    return repo_b


def test_resolver_finds_via_go_mod_replace(tmp_path: Path) -> None:
    """The plan-required 2-module fixture (test 11).

    repo_a has ``util/util.go::DoThing``. repo_b has
    ``replace example.com/a => ../repo_a`` in go.mod. Resolving
    ``import "example.com/a/util"`` with symbol ``DoThing`` should
    yield ``repo_a_id:util/util.go::DoThing``.
    """
    repo_a = _build_repo_a_with_util(tmp_path)
    repo_b = _build_repo_b_with_replace(tmp_path)

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        'import "example.com/a/util"',
        symbol="DoThing",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:util/util.go::DoThing"


def test_resolver_skips_self_repo(tmp_path: Path) -> None:
    """A target sharing source's repo_id is skipped."""
    repo_a = _build_repo_a_with_util(tmp_path)
    repo_b = _build_repo_b_with_replace(tmp_path)

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_a_id",  # same as target
    )
    qualified = resolver.resolve(
        'import "example.com/a/util"',
        symbol="DoThing",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_when_no_replace_directive(tmp_path: Path) -> None:
    """Without any replace, resolver can't pick a target -> None."""
    repo_a = _build_repo_a_with_util(tmp_path)
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "go.mod").write_text(
        "module example.com/b\n\ngo 1.22\n",
        encoding="utf-8",
    )

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        'import "example.com/a/util"',
        symbol="DoThing",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_when_replace_doesnt_match_target(
    tmp_path: Path,
) -> None:
    """Replace pointing outside any target's tree -> None."""
    repo_a = _build_repo_a_with_util(tmp_path)
    # repo_b's replace points to a sibling that is NOT repo_a.
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "util").mkdir()
    repo_b = _build_repo_b_with_replace(tmp_path, replace_target="../elsewhere")

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        'import "example.com/a/util"',
        symbol="DoThing",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_skips_test_files(tmp_path: Path) -> None:
    """``_test.go`` files are excluded from the search."""
    repo_a = tmp_path / "repo_a"
    util = repo_a / "util"
    util.mkdir(parents=True)
    # Only a test file is present -> no resolvable hit.
    (util / "util_test.go").write_text(
        "package util\n\nfunc TestDoThing(t *testing.T) {}\n",
        encoding="utf-8",
    )
    (repo_a / "go.mod").write_text(
        "module example.com/a\n\ngo 1.22\n",
        encoding="utf-8",
    )
    repo_b = _build_repo_b_with_replace(tmp_path)

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        'import "example.com/a/util"',
        symbol="DoThing",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_picks_non_test_file_when_both_present(tmp_path: Path) -> None:
    """When ``util.go`` and ``util_test.go`` coexist, the non-test file wins."""
    repo_a = tmp_path / "repo_a"
    util = repo_a / "util"
    util.mkdir(parents=True)
    (util / "util.go").write_text(
        "package util\n\nfunc DoThing() {}\n",
        encoding="utf-8",
    )
    (util / "util_test.go").write_text(
        "package util\n\nfunc TestDoThing(t *testing.T) {}\n",
        encoding="utf-8",
    )
    (repo_a / "go.mod").write_text(
        "module example.com/a\n\ngo 1.22\n",
        encoding="utf-8",
    )
    repo_b = _build_repo_b_with_replace(tmp_path)

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        'import "example.com/a/util"',
        symbol="DoThing",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:util/util.go::DoThing"


def test_resolver_longest_module_prefix_wins(tmp_path: Path) -> None:
    """Overlapping replaces -> the longest module-prefix wins.

    Both ``example.com/lib`` and ``example.com/lib/special`` are
    replaced; an import of ``example.com/lib/special/sub`` must route
    through the longer prefix and land on the special tree.
    """
    repo_a = tmp_path / "repo_a"  # routed by short prefix
    (repo_a / "sub").mkdir(parents=True)
    (repo_a / "sub" / "general.go").write_text(
        "package sub\n\nfunc General() {}\n",
        encoding="utf-8",
    )
    (repo_a / "go.mod").write_text(
        "module example.com/lib\n\ngo 1.22\n", encoding="utf-8"
    )

    repo_special = tmp_path / "repo_special"  # routed by long prefix
    (repo_special / "sub").mkdir(parents=True)
    (repo_special / "sub" / "special.go").write_text(
        "package sub\n\nfunc DoThing() {}\n",
        encoding="utf-8",
    )
    (repo_special / "go.mod").write_text(
        "module example.com/lib/special\n\ngo 1.22\n",
        encoding="utf-8",
    )

    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "go.mod").write_text(
        """module example.com/b

go 1.22

replace example.com/lib => ../repo_a
replace example.com/lib/special => ../repo_special
""",
        encoding="utf-8",
    )

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        'import "example.com/lib/special/sub"',
        symbol="DoThing",
        targets=[
            TargetRepo(repo_id="repo_a_id", root=repo_a),
            TargetRepo(repo_id="repo_special_id", root=repo_special),
        ],
    )
    # Longest match -> repo_special tree.
    assert qualified == "repo_special_id:sub/special.go::DoThing"


def test_resolver_returns_none_for_garbage_import(tmp_path: Path) -> None:
    """Unparseable import line -> None even with valid targets."""
    repo_a = _build_repo_a_with_util(tmp_path)
    repo_b = _build_repo_b_with_replace(tmp_path)

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "func main() {}",
        symbol="DoThing",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_reads_go_work_at_construction(tmp_path: Path) -> None:
    """Constructing a resolver loads ``go.work`` workspace declarations.

    The current resolver primarily routes via go.mod replace, but it
    parses go.work at construction time to expose workspace uses for
    later use. This test pins the wired-up behaviour so go.work files
    are not silently skipped.
    """
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "go.mod").write_text(
        "module example.com/b\n\ngo 1.22\n",
        encoding="utf-8",
    )
    (repo_b / "go.work").write_text(
        """go 1.22

use (
  ./moduleA
  ./moduleB
)
""",
        encoding="utf-8",
    )

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    # pylint: disable=protected-access
    assert resolver._workspace_uses == ["./moduleA", "./moduleB"]


def test_resolver_returns_none_when_package_subdir_missing(tmp_path: Path) -> None:
    """Replace points at a real target tree but the package subdir
    inside it doesn't exist -> ``search_dir.is_dir()`` is False -> None.
    """
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    # No ``util/`` subdir under repo_a.
    (repo_a / "go.mod").write_text(
        "module example.com/a\n\ngo 1.22\n",
        encoding="utf-8",
    )
    repo_b = _build_repo_b_with_replace(tmp_path)

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        'import "example.com/a/util"',
        symbol="DoThing",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_read_go_mod_replaces_unreadable_returns_empty(
    tmp_path: Path, monkeypatch: object
) -> None:
    """OSError while reading go.mod -> empty dict (caller treats as 'no replaces')."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text("replace example.com/a => ../a\n", encoding="utf-8")

    def boom(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("permission denied")

    # mypy/ty: monkeypatch is a real fixture at runtime; type-only stub here.
    monkeypatch.setattr(Path, "read_text", boom)  # type: ignore[attr-defined]
    assert _read_go_mod_replaces(go_mod) == {}


def test_read_go_work_uses_unreadable_returns_empty(
    tmp_path: Path, monkeypatch: object
) -> None:
    """OSError while reading go.work -> empty list."""
    go_work = tmp_path / "go.work"
    go_work.write_text("use ./moduleA\n", encoding="utf-8")

    def boom(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", boom)  # type: ignore[attr-defined]
    assert _read_go_work_uses(go_work) == []


def test_resolver_module_path_equal_to_replace_module(tmp_path: Path) -> None:
    """When the import equals the replaced module exactly (no suffix),
    the search lands on the replacement directory itself.
    """
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir(parents=True)
    (repo_a / "lib.go").write_text(
        "package a\n\nfunc Top() {}\n",
        encoding="utf-8",
    )
    (repo_a / "go.mod").write_text(
        "module example.com/a\n\ngo 1.22\n",
        encoding="utf-8",
    )
    repo_b = _build_repo_b_with_replace(tmp_path)

    resolver = GoResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        'import "example.com/a"',
        symbol="Top",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:lib.go::Top"
