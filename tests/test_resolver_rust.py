"""Tests for the Rust cross-repo resolver (Phase 2 Task 6).

Covers :mod:`better_code_review_graph.resolver.rust`:

* ``parse_use_statement`` — turns Rust ``use crate::module::Symbol;``
  declarations into a :class:`RustUse`.
* ``_read_cargo_path_deps`` — extracts ``[dependencies]`` table entries
  whose value is an inline-table containing a ``path`` key.
* ``_read_workspace_members`` — extracts ``[workspace] members = [...]``
  declarations.
* ``RustResolver.resolve`` — applies path deps + workspace members to
  map a ``use`` line onto a target repo's filesystem and returns
  ``<repo_id>:<file_path>::<symbol>`` qualified names on a hit.
"""

from __future__ import annotations

from pathlib import Path

from better_code_review_graph.resolver.rust import (
    RustResolver,
    RustUse,
    TargetRepo,
    _read_cargo_path_deps,
    _read_workspace_members,
    parse_use_statement,
)

# ---------------------------------------------------------------------------
# parse_use_statement
# ---------------------------------------------------------------------------


def test_parse_use_simple() -> None:
    """``use foo::util::do_thing;`` -> crate='foo', module=['util'], symbol='do_thing'."""
    parsed = parse_use_statement("use foo::util::do_thing;")
    assert parsed == RustUse(crate="foo", module_path=["util"], symbol="do_thing")


def test_parse_use_no_module() -> None:
    """``use foo::Bar;`` -> empty module path."""
    parsed = parse_use_statement("use foo::Bar;")
    assert parsed == RustUse(crate="foo", module_path=[], symbol="Bar")


def test_parse_use_pub_re_export() -> None:
    """``pub use foo::Bar;`` (re-export) parses identically to non-pub."""
    parsed = parse_use_statement("pub use foo::Bar;")
    assert parsed == RustUse(crate="foo", module_path=[], symbol="Bar")


def test_parse_use_with_alias() -> None:
    """``use foo::Bar as Baz;`` keeps original crate/symbol; alias dropped."""
    parsed = parse_use_statement("use foo::Bar as Baz;")
    assert parsed == RustUse(crate="foo", module_path=[], symbol="Bar")


def test_parse_use_self_super_skipped() -> None:
    """Intra-crate ``self::``, ``super::``, ``crate::`` references return None."""
    assert parse_use_statement("use self::foo;") is None
    assert parse_use_statement("use super::bar;") is None
    assert parse_use_statement("use crate::baz;") is None


def test_parse_use_garbage() -> None:
    """Non-use lines return None."""
    assert parse_use_statement("fn foo() {}") is None
    assert parse_use_statement("") is None
    assert parse_use_statement("    ") is None
    assert parse_use_statement("// use foo::Bar;") is None
    assert parse_use_statement("let x = 1;") is None


def test_parse_use_no_double_colon_returns_none() -> None:
    """``use foo;`` without ``::`` separator returns None (no symbol)."""
    assert parse_use_statement("use foo;") is None


def test_parse_use_deep_module_path() -> None:
    """``use foo::a::b::c::Sym;`` collects all middle segments as module path."""
    parsed = parse_use_statement("use foo::a::b::c::Sym;")
    assert parsed == RustUse(crate="foo", module_path=["a", "b", "c"], symbol="Sym")


# ---------------------------------------------------------------------------
# _read_cargo_path_deps
# ---------------------------------------------------------------------------


def test_read_cargo_path_deps_inline_table(tmp_path: Path) -> None:
    """``foo = { path = "../foo" }`` -> {"foo": "../foo"}."""
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text(
        """[package]
name = "bar"
version = "0.1.0"

[dependencies]
foo = { path = "../foo" }
""",
        encoding="utf-8",
    )
    assert _read_cargo_path_deps(cargo) == {"foo": "../foo"}


def test_read_cargo_path_deps_section_form(tmp_path: Path) -> None:
    """``[dependencies.foo] path = "../foo"`` (TOML-section form) also parses."""
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text(
        """[package]
name = "bar"
version = "0.1.0"

[dependencies.foo]
path = "../foo"
""",
        encoding="utf-8",
    )
    assert _read_cargo_path_deps(cargo) == {"foo": "../foo"}


def test_read_cargo_path_deps_filters_registry(tmp_path: Path) -> None:
    """``serde = "1.0"`` (string form, registry dep) is filtered out."""
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text(
        """[package]
name = "bar"

[dependencies]
serde = "1.0"
foo = { path = "../foo" }
""",
        encoding="utf-8",
    )
    assert _read_cargo_path_deps(cargo) == {"foo": "../foo"}


def test_read_cargo_path_deps_filters_git(tmp_path: Path) -> None:
    """``bar = { git = "..." }`` (no path key) is filtered out."""
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text(
        """[package]
name = "bar"

[dependencies]
bar = { git = "https://github.com/x/y" }
foo = { path = "../foo" }
""",
        encoding="utf-8",
    )
    assert _read_cargo_path_deps(cargo) == {"foo": "../foo"}


def test_read_cargo_path_deps_missing_file(tmp_path: Path) -> None:
    """Missing Cargo.toml -> empty dict, no exception."""
    assert _read_cargo_path_deps(tmp_path / "nope.toml") == {}


def test_read_cargo_path_deps_malformed_toml(tmp_path: Path) -> None:
    """Unparseable TOML -> empty dict, no exception."""
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text("this is not = valid toml [[[", encoding="utf-8")
    assert _read_cargo_path_deps(cargo) == {}


def test_read_cargo_path_deps_no_dependencies_section(tmp_path: Path) -> None:
    """Cargo.toml without ``[dependencies]`` -> empty dict."""
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text('[package]\nname = "bar"\n', encoding="utf-8")
    assert _read_cargo_path_deps(cargo) == {}


# ---------------------------------------------------------------------------
# _read_workspace_members
# ---------------------------------------------------------------------------


def test_read_workspace_members_simple(tmp_path: Path) -> None:
    """``[workspace] members = ["a", "b"]`` -> ['a', 'b']."""
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text(
        """[workspace]
members = ["crate_a", "crate_b"]
""",
        encoding="utf-8",
    )
    assert _read_workspace_members(cargo) == ["crate_a", "crate_b"]


def test_read_workspace_members_missing(tmp_path: Path) -> None:
    """Cargo.toml without ``[workspace]`` -> empty list."""
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text('[package]\nname = "bar"\n', encoding="utf-8")
    assert _read_workspace_members(cargo) == []


def test_read_workspace_members_missing_file(tmp_path: Path) -> None:
    """Missing Cargo.toml -> empty list."""
    assert _read_workspace_members(tmp_path / "nope.toml") == []


def test_read_workspace_members_malformed_toml(tmp_path: Path) -> None:
    """Unparseable TOML -> empty list."""
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text("[[[invalid", encoding="utf-8")
    assert _read_workspace_members(cargo) == []


# ---------------------------------------------------------------------------
# RustResolver.resolve — fixtures + integration
# ---------------------------------------------------------------------------


def _build_foo_crate_with_util(tmp_path: Path, dirname: str = "a") -> Path:
    """Create a ``foo`` crate at ``tmp_path/<dirname>`` with src/util.rs::do_thing.

    Returns the crate root.
    """
    crate = tmp_path / dirname
    src = crate / "src"
    src.mkdir(parents=True)
    (crate / "Cargo.toml").write_text(
        """[package]
name = "foo"
version = "0.1.0"
edition = "2021"
""",
        encoding="utf-8",
    )
    (src / "util.rs").write_text(
        "pub fn do_thing() {}\n",
        encoding="utf-8",
    )
    return crate


def _build_repo_b_with_path_dep(tmp_path: Path, dep_path: str = "../a") -> Path:
    """Create ``repo_b`` with Cargo.toml [dependencies] foo = { path = dep_path }."""
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "Cargo.toml").write_text(
        f"""[package]
name = "bar"
version = "0.1.0"
edition = "2021"

[dependencies]
foo = {{ path = "{dep_path}" }}
""",
        encoding="utf-8",
    )
    return repo_b


def test_resolver_finds_via_path_dep(tmp_path: Path) -> None:
    """The plan-required 2-crate workspace fixture (test 13).

    repo_a (named ``foo`` in Cargo.toml) has src/util.rs::do_thing.
    repo_b has [dependencies] foo = { path = "../a" }.
    Resolving ``use foo::util::do_thing;`` should yield
    ``repo_a_id:src/util.rs::do_thing``.
    """
    repo_a = _build_foo_crate_with_util(tmp_path, dirname="a")
    repo_b = _build_repo_b_with_path_dep(tmp_path, dep_path="../a")

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "use foo::util::do_thing;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:src/util.rs::do_thing"


def test_resolver_finds_via_mod_rs(tmp_path: Path) -> None:
    """``use foo::util::Item;`` resolves when ``src/util/mod.rs`` exists."""
    repo_a = tmp_path / "a"
    util_dir = repo_a / "src" / "util"
    util_dir.mkdir(parents=True)
    (repo_a / "Cargo.toml").write_text(
        '[package]\nname = "foo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (util_dir / "mod.rs").write_text(
        "pub struct Item;\n",
        encoding="utf-8",
    )
    repo_b = _build_repo_b_with_path_dep(tmp_path, dep_path="../a")

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "use foo::util::Item;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:src/util/mod.rs::Item"


def test_resolver_finds_via_lib_rs(tmp_path: Path) -> None:
    """``use foo::Bar;`` (no module path) resolves to ``src/lib.rs``."""
    repo_a = tmp_path / "a"
    src = repo_a / "src"
    src.mkdir(parents=True)
    (repo_a / "Cargo.toml").write_text(
        '[package]\nname = "foo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (src / "lib.rs").write_text(
        "pub struct Bar;\n",
        encoding="utf-8",
    )
    repo_b = _build_repo_b_with_path_dep(tmp_path, dep_path="../a")

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "use foo::Bar;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:src/lib.rs::Bar"


def test_resolver_finds_workspace_member(tmp_path: Path) -> None:
    """Source repo is a workspace root with ``members = ["crate_a"]``.

    ``use crate_a::util::Foo;`` resolves to crate_a/src/util.rs even
    though crate_a is NOT listed in ``[dependencies]``.
    """
    workspace_root = tmp_path / "workspace"
    crate_a = workspace_root / "crate_a"
    src = crate_a / "src"
    src.mkdir(parents=True)
    (workspace_root / "Cargo.toml").write_text(
        """[workspace]
members = ["crate_a"]
""",
        encoding="utf-8",
    )
    (crate_a / "Cargo.toml").write_text(
        '[package]\nname = "crate_a"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (src / "util.rs").write_text(
        "pub struct Foo;\n",
        encoding="utf-8",
    )

    resolver = RustResolver(
        source_repo_root=workspace_root,
        source_repo_id="workspace_id",
    )
    qualified = resolver.resolve(
        "use crate_a::util::Foo;",
        targets=[TargetRepo(repo_id="member_repo_id", root=workspace_root)],
    )
    # Note the resolver returns paths relative to the target root (the
    # workspace_root itself in this fixture).
    assert qualified == "member_repo_id:crate_a/src/util.rs::Foo"


def test_resolver_skips_self_repo(tmp_path: Path) -> None:
    """A target sharing source's repo_id is skipped."""
    repo_a = _build_foo_crate_with_util(tmp_path, dirname="a")
    repo_b = _build_repo_b_with_path_dep(tmp_path, dep_path="../a")

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_a_id",  # same as target
    )
    qualified = resolver.resolve(
        "use foo::util::do_thing;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_when_no_match(tmp_path: Path) -> None:
    """No ``[dependencies]`` path dep + no workspace member match -> None."""
    repo_a = _build_foo_crate_with_util(tmp_path, dirname="a")
    # repo_b has no path dep referencing foo.
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "Cargo.toml").write_text(
        '[package]\nname = "bar"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "use foo::util::do_thing;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_for_self_super_crate(tmp_path: Path) -> None:
    """Intra-crate ``self::``/``super::``/``crate::`` uses don't cross-resolve."""
    repo_a = _build_foo_crate_with_util(tmp_path, dirname="a")
    repo_b = _build_repo_b_with_path_dep(tmp_path, dep_path="../a")

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    for stmt in (
        "use self::foo;",
        "use super::bar;",
        "use crate::baz;",
    ):
        qualified = resolver.resolve(
            stmt,
            targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
        )
        assert qualified is None, f"{stmt!r} should not resolve cross-repo"


def test_resolver_returns_none_for_garbage_use(tmp_path: Path) -> None:
    """Unparseable use line -> None even with valid targets."""
    repo_a = _build_foo_crate_with_util(tmp_path, dirname="a")
    repo_b = _build_repo_b_with_path_dep(tmp_path, dep_path="../a")

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "fn main() {}",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_when_path_dep_outside_targets(
    tmp_path: Path,
) -> None:
    """Path dep points to a directory not under any target's tree -> None."""
    repo_a = _build_foo_crate_with_util(tmp_path, dirname="a")
    # repo_b's path dep points to a sibling that is NOT repo_a.
    elsewhere = tmp_path / "elsewhere"
    src = elsewhere / "src"
    src.mkdir(parents=True)
    (elsewhere / "Cargo.toml").write_text(
        '[package]\nname = "foo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (src / "util.rs").write_text("pub fn do_thing() {}\n", encoding="utf-8")

    repo_b = _build_repo_b_with_path_dep(tmp_path, dep_path="../elsewhere")

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "use foo::util::do_thing;",
        # repo_a is the only registered target — replacement is in
        # ``elsewhere/`` which is not under repo_a.
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_when_module_file_missing(tmp_path: Path) -> None:
    """Path dep resolves but the requested module file is absent -> None."""
    repo_a = tmp_path / "a"
    src = repo_a / "src"
    src.mkdir(parents=True)
    (repo_a / "Cargo.toml").write_text(
        '[package]\nname = "foo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    # No util.rs / util/mod.rs / lib.rs — only an unrelated file.
    (src / "other.rs").write_text("pub fn other() {}\n", encoding="utf-8")
    repo_b = _build_repo_b_with_path_dep(tmp_path, dep_path="../a")

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "use foo::util::do_thing;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_when_lib_rs_missing(tmp_path: Path) -> None:
    """``use foo::Bar;`` with no ``src/lib.rs`` in the target -> None."""
    repo_a = tmp_path / "a"
    src = repo_a / "src"
    src.mkdir(parents=True)
    (repo_a / "Cargo.toml").write_text(
        '[package]\nname = "foo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    # Has a binary main.rs but no lib.rs.
    (src / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    repo_b = _build_repo_b_with_path_dep(tmp_path, dep_path="../a")

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "use foo::Bar;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_when_src_dir_missing(tmp_path: Path) -> None:
    """Path dep crate has no ``src/`` directory at all -> None."""
    repo_a = tmp_path / "a"
    repo_a.mkdir()
    (repo_a / "Cargo.toml").write_text(
        '[package]\nname = "foo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    repo_b = _build_repo_b_with_path_dep(tmp_path, dep_path="../a")

    resolver = RustResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "use foo::util::do_thing;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_workspace_member_missing_cargo_skipped(tmp_path: Path) -> None:
    """A listed workspace member without Cargo.toml is silently skipped.

    Pins behaviour: a stale ``members = [...]`` entry pointing at a
    deleted directory (or one without a Cargo.toml) must not crash the
    resolver — it just doesn't match.
    """
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["ghost", "real"]\n',
        encoding="utf-8",
    )
    # ghost dir doesn't exist; real exists but has no Cargo.toml.
    (workspace_root / "real").mkdir()

    resolver = RustResolver(
        source_repo_root=workspace_root,
        source_repo_id="ws_id",
    )
    qualified = resolver.resolve(
        "use ghost::util::Foo;",
        targets=[TargetRepo(repo_id="t_id", root=workspace_root)],
    )
    assert qualified is None


def test_resolver_workspace_member_with_malformed_cargo_skipped(
    tmp_path: Path,
) -> None:
    """Workspace member with malformed Cargo.toml is silently skipped.

    Resolver hits the inner ``except TOMLDecodeError -> continue`` path
    when scanning workspace members for a matching package name.
    """
    workspace_root = tmp_path / "workspace"
    crate_bad = workspace_root / "bad"
    src = crate_bad / "src"
    src.mkdir(parents=True)
    (workspace_root / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["bad"]\n',
        encoding="utf-8",
    )
    # Member's Cargo.toml is unparseable.
    (crate_bad / "Cargo.toml").write_text("[[[ not toml", encoding="utf-8")
    (src / "util.rs").write_text("pub struct Foo;\n", encoding="utf-8")

    resolver = RustResolver(
        source_repo_root=workspace_root,
        source_repo_id="ws_id",
    )
    qualified = resolver.resolve(
        # ``bad`` won't match because its Cargo.toml didn't parse.
        "use bad::util::Foo;",
        targets=[TargetRepo(repo_id="t_id", root=workspace_root)],
    )
    assert qualified is None


def test_resolver_workspace_member_skips_until_name_match(tmp_path: Path) -> None:
    """Workspace iteration skips members whose package.name doesn't match.

    Pins the inner ``for member_glob`` continue-on-mismatch path: the
    first listed member has a different package name and must be
    skipped before the second (matching) member is selected.
    """
    workspace_root = tmp_path / "workspace"
    other = workspace_root / "other"
    crate_a = workspace_root / "crate_a"
    (other / "src").mkdir(parents=True)
    (crate_a / "src").mkdir(parents=True)
    (workspace_root / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["other", "crate_a"]\n',
        encoding="utf-8",
    )
    # First member has a *different* package name -> must be skipped.
    (other / "Cargo.toml").write_text(
        '[package]\nname = "unrelated"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (other / "src" / "lib.rs").write_text("// noop\n", encoding="utf-8")
    # Second member is the real match.
    (crate_a / "Cargo.toml").write_text(
        '[package]\nname = "crate_a"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (crate_a / "src" / "util.rs").write_text(
        "pub struct Foo;\n",
        encoding="utf-8",
    )

    resolver = RustResolver(
        source_repo_root=workspace_root,
        source_repo_id="ws_id",
    )
    qualified = resolver.resolve(
        "use crate_a::util::Foo;",
        targets=[TargetRepo(repo_id="t_id", root=workspace_root)],
    )
    assert qualified == "t_id:crate_a/src/util.rs::Foo"


def test_resolver_path_dep_takes_priority_over_workspace_member(
    tmp_path: Path,
) -> None:
    """If both a path dep AND a workspace member could match, path dep wins.

    Pins resolver branch ordering: ``[dependencies]`` entry is checked
    first; workspace-member fallback only runs when no path dep matches.
    """
    repo_a = _build_foo_crate_with_util(tmp_path, dirname="a")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    # Workspace root that ALSO has [dependencies] foo = path dep + a
    # member named foo. The path dep should be picked first.
    (workspace_root / "Cargo.toml").write_text(
        """[workspace]
members = ["foo_member"]

[package]
name = "wsroot"
version = "0.1.0"

[dependencies]
foo = { path = "../a" }
""",
        encoding="utf-8",
    )
    member = workspace_root / "foo_member"
    src = member / "src"
    src.mkdir(parents=True)
    (member / "Cargo.toml").write_text(
        '[package]\nname = "foo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (src / "util.rs").write_text(
        "pub fn member_only() {}\n",  # different file body — not used
        encoding="utf-8",
    )

    resolver = RustResolver(
        source_repo_root=workspace_root,
        source_repo_id="ws_id",
    )
    qualified = resolver.resolve(
        "use foo::util::do_thing;",
        targets=[
            TargetRepo(repo_id="repo_a_id", root=repo_a),
            TargetRepo(repo_id="ws_target_id", root=workspace_root),
        ],
    )
    # Path dep -> repo_a wins, NOT the workspace member.
    assert qualified == "repo_a_id:src/util.rs::do_thing"
