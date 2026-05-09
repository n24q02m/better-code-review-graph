"""Tests for the TypeScript cross-repo resolver (Phase 2 Task 4).

Covers :mod:`better_code_review_graph.resolver.typescript`:

* ``parse_import_statement`` — turns ``import { x } from 'mod'`` /
  ``import x from 'mod'`` / ``import * as ns from 'mod'`` /
  ``import 'mod'`` source lines into a :class:`TypeScriptImport`.
* ``_read_tsconfig_paths`` — extracts ``compilerOptions.paths`` mapping
  from ``tsconfig.json`` (tolerates ``//`` line comments commonly used
  in TypeScript config files).
* ``_read_workspaces`` — extracts ``workspaces`` from ``package.json``
  in either array form (``["packages/*"]``) or object form
  (``{"packages": [...]}``).
* ``_expand_alias`` — applies tsconfig path mapping to an import module
  to produce candidate filesystem paths.
* ``TypeScriptResolver.resolve`` — walks each target repo's workspace
  roots applying tsconfig path mapping and returns
  ``<repo_id>:<file_path>::<symbol>`` qualified names on a hit.
"""

from __future__ import annotations

from pathlib import Path

from better_code_review_graph.resolver.typescript import (
    TargetRepo,
    TypeScriptImport,
    TypeScriptResolver,
    _expand_alias,
    _read_tsconfig_paths,
    _read_workspaces,
    parse_import_statement,
)

# ---------------------------------------------------------------------------
# parse_import_statement
# ---------------------------------------------------------------------------


def test_parse_import_named_form() -> None:
    """``import { foo } from 'mod'`` -> module='mod', name='foo'."""
    parsed = parse_import_statement("import { foo } from 'mod'")
    assert parsed == TypeScriptImport(module="mod", name="foo")


def test_parse_import_named_form_multi_symbol() -> None:
    """First named symbol wins for multi-symbol named imports."""
    parsed = parse_import_statement("import { foo, bar, baz } from 'mod'")
    assert parsed == TypeScriptImport(module="mod", name="foo")


def test_parse_import_default_form() -> None:
    """``import foo from 'mod'`` -> module='mod', name='foo'."""
    parsed = parse_import_statement("import foo from 'mod'")
    assert parsed == TypeScriptImport(module="mod", name="foo")


def test_parse_import_namespace_form() -> None:
    """``import * as ns from 'mod'`` -> module='mod', name='ns'."""
    parsed = parse_import_statement("import * as ns from 'mod'")
    assert parsed == TypeScriptImport(module="mod", name="ns")


def test_parse_import_side_effect() -> None:
    """``import 'mod'`` -> module='mod', name=None (no symbol)."""
    parsed = parse_import_statement("import 'mod'")
    assert parsed == TypeScriptImport(module="mod", name=None)


def test_parse_import_double_quotes() -> None:
    """Double-quoted module specifiers work the same as single-quoted ones."""
    parsed = parse_import_statement('import { foo } from "mod"')
    assert parsed == TypeScriptImport(module="mod", name="foo")


def test_parse_import_with_trailing_semicolon() -> None:
    """Trailing semicolons are tolerated."""
    parsed = parse_import_statement("import { foo } from 'mod';")
    assert parsed == TypeScriptImport(module="mod", name="foo")


def test_parse_import_garbage() -> None:
    """Non-import strings return None."""
    assert parse_import_statement("function foo() {}") is None
    assert parse_import_statement("") is None
    assert parse_import_statement("    ") is None
    assert parse_import_statement("// import { x } from 'mod'") is None
    assert parse_import_statement("const x = 1") is None


# ---------------------------------------------------------------------------
# _read_tsconfig_paths
# ---------------------------------------------------------------------------


def test_read_tsconfig_paths_handles_comments(tmp_path: Path) -> None:
    """tsconfig with ``//`` line comments parses correctly."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(
        """{
  // Project root tsconfig
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/foo/*": ["packages/foo/*"]  // workspace alias
    }
  }
}
""",
        encoding="utf-8",
    )
    paths = _read_tsconfig_paths(tsconfig)
    assert paths == {"@/foo/*": ["packages/foo/*"]}


def test_read_tsconfig_paths_string_value_normalised_to_list(tmp_path: Path) -> None:
    """Single-string path target normalises to a one-element list."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(
        '{"compilerOptions": {"paths": {"@/foo": "packages/foo"}}}',
        encoding="utf-8",
    )
    paths = _read_tsconfig_paths(tsconfig)
    assert paths == {"@/foo": ["packages/foo"]}


def test_read_tsconfig_paths_missing_file(tmp_path: Path) -> None:
    """Missing tsconfig -> empty dict, no exception."""
    paths = _read_tsconfig_paths(tmp_path / "nope.json")
    assert paths == {}


def test_read_tsconfig_paths_invalid_json(tmp_path: Path) -> None:
    """Malformed JSON -> empty dict (caller treats as 'no paths')."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text("this is not json {{{", encoding="utf-8")
    paths = _read_tsconfig_paths(tsconfig)
    assert paths == {}


def test_read_tsconfig_paths_no_compiler_options(tmp_path: Path) -> None:
    """tsconfig without ``compilerOptions`` -> empty dict."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text('{"include": ["src/**/*"]}', encoding="utf-8")
    paths = _read_tsconfig_paths(tsconfig)
    assert paths == {}


# ---------------------------------------------------------------------------
# _read_workspaces
# ---------------------------------------------------------------------------


def test_read_workspaces_array_form(tmp_path: Path) -> None:
    """``"workspaces": ["packages/*"]`` -> ['packages/*']."""
    pkg = tmp_path / "package.json"
    pkg.write_text(
        '{"name": "root", "workspaces": ["packages/*", "apps/*"]}',
        encoding="utf-8",
    )
    assert _read_workspaces(pkg) == ["packages/*", "apps/*"]


def test_read_workspaces_object_form(tmp_path: Path) -> None:
    """``"workspaces": {"packages": [...]}`` -> the inner list."""
    pkg = tmp_path / "package.json"
    pkg.write_text(
        '{"name": "root", "workspaces": {"packages": ["packages/*"]}}',
        encoding="utf-8",
    )
    assert _read_workspaces(pkg) == ["packages/*"]


def test_read_workspaces_missing_file(tmp_path: Path) -> None:
    """Missing package.json -> empty list."""
    assert _read_workspaces(tmp_path / "nope.json") == []


def test_read_workspaces_invalid_json(tmp_path: Path) -> None:
    """Malformed JSON -> empty list."""
    pkg = tmp_path / "package.json"
    pkg.write_text("not json {{{", encoding="utf-8")
    assert _read_workspaces(pkg) == []


def test_read_workspaces_absent_field(tmp_path: Path) -> None:
    """package.json without ``workspaces`` -> empty list."""
    pkg = tmp_path / "package.json"
    pkg.write_text('{"name": "root", "version": "0.0.0"}', encoding="utf-8")
    assert _read_workspaces(pkg) == []


def test_read_workspaces_object_form_no_packages_key(tmp_path: Path) -> None:
    """Object form without ``packages`` key -> empty list."""
    pkg = tmp_path / "package.json"
    pkg.write_text(
        '{"name": "root", "workspaces": {"nohoist": ["**/react-native"]}}',
        encoding="utf-8",
    )
    assert _read_workspaces(pkg) == []


# ---------------------------------------------------------------------------
# _expand_alias
# ---------------------------------------------------------------------------


def test_expand_alias_with_glob() -> None:
    """``@/foo/*`` -> ``packages/foo/*`` rewrites the suffix."""
    candidates = _expand_alias(
        "@/foo/utils",
        {"@/foo/*": ["packages/foo/*"]},
    )
    assert candidates == ["packages/foo/utils"]


def test_expand_alias_exact_match() -> None:
    """Exact (non-glob) alias maps to the literal target list."""
    candidates = _expand_alias("~lib", {"~lib": ["lib"]})
    assert candidates == ["lib"]


def test_expand_alias_no_match_returns_module_as_is() -> None:
    """Module without a matching alias is returned unchanged."""
    candidates = _expand_alias(
        "lodash",
        {"@/foo/*": ["packages/foo/*"]},
    )
    assert candidates == ["lodash"]


def test_expand_alias_empty_paths() -> None:
    """Empty paths dict -> module returned as-is."""
    assert _expand_alias("anything", {}) == ["anything"]


def test_expand_alias_glob_target_without_star() -> None:
    """Glob alias mapped to a non-glob target still works (joined with /)."""
    candidates = _expand_alias(
        "@/foo/utils",
        {"@/foo/*": ["packages/foo"]},
    )
    assert candidates == ["packages/foo/utils"]


def test_expand_alias_multi_target() -> None:
    """Multiple target paths produce multiple candidates."""
    candidates = _expand_alias(
        "@/foo/utils",
        {"@/foo/*": ["packages/foo/*", "vendor/foo/*"]},
    )
    assert candidates == ["packages/foo/utils", "vendor/foo/utils"]


# ---------------------------------------------------------------------------
# TypeScriptResolver.resolve — fixture builders
# ---------------------------------------------------------------------------


def _build_repo_a_with_workspaces(tmp_path: Path) -> Path:
    """Create ``repo_a`` with ``packages/foo/utils.ts`` and yarn workspaces."""
    repo_a = tmp_path / "repo_a"
    pkg = repo_a / "packages" / "foo"
    pkg.mkdir(parents=True)
    (pkg / "utils.ts").write_text(
        "export function bar() { return 1 }\n",
        encoding="utf-8",
    )
    (repo_a / "package.json").write_text(
        '{"name": "repo_a", "workspaces": ["packages/*"]}',
        encoding="utf-8",
    )
    return repo_a


def _build_repo_b_with_alias(tmp_path: Path) -> Path:
    """Create ``repo_b`` with tsconfig path alias to ``packages/foo/*``."""
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "tsconfig.json").write_text(
        """{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/foo/*": ["packages/foo/*"]
    }
  }
}
""",
        encoding="utf-8",
    )
    (repo_b / "package.json").write_text(
        '{"name": "repo_b", "workspaces": ["packages/*"]}',
        encoding="utf-8",
    )
    return repo_b


# ---------------------------------------------------------------------------
# TypeScriptResolver.resolve — behaviour
# ---------------------------------------------------------------------------


def test_resolver_finds_workspace_target(tmp_path: Path) -> None:
    """The plan-required 2-repo monorepo fixture (test 13).

    repo_a has ``packages/foo/utils.ts::bar`` plus yarn workspaces.
    repo_b has tsconfig ``"@/foo/*": ["packages/foo/*"]`` plus workspaces.
    Parsing ``import { bar } from '@/foo/utils'`` against repo_a should
    yield ``repo_a_id:packages/foo/utils.ts::bar``.
    """
    repo_a = _build_repo_a_with_workspaces(tmp_path)
    repo_b = _build_repo_b_with_alias(tmp_path)

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import { bar } from '@/foo/utils'",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:packages/foo/utils.ts::bar"


def test_resolver_finds_via_index_ts(tmp_path: Path) -> None:
    """Module that resolves to a directory uses ``index.ts``."""
    repo_a = tmp_path / "repo_a"
    pkg = repo_a / "packages" / "foo" / "utils"
    pkg.mkdir(parents=True)
    (pkg / "index.ts").write_text(
        "export function bar() {}\n",
        encoding="utf-8",
    )
    (repo_a / "package.json").write_text(
        '{"name": "repo_a", "workspaces": ["packages/*"]}',
        encoding="utf-8",
    )
    repo_b = _build_repo_b_with_alias(tmp_path)

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import { bar } from '@/foo/utils'",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:packages/foo/utils/index.ts::bar"


def test_resolver_finds_via_tsx_extension(tmp_path: Path) -> None:
    """``.tsx`` files (React component) are also matched."""
    repo_a = tmp_path / "repo_a"
    pkg = repo_a / "packages" / "ui"
    pkg.mkdir(parents=True)
    (pkg / "Button.tsx").write_text(
        "export function Button() {}\n",
        encoding="utf-8",
    )
    (repo_a / "package.json").write_text(
        '{"name": "repo_a", "workspaces": ["packages/*"]}',
        encoding="utf-8",
    )
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "tsconfig.json").write_text(
        '{"compilerOptions": {"paths": {"@/ui/*": ["packages/ui/*"]}}}',
        encoding="utf-8",
    )
    (repo_b / "package.json").write_text(
        '{"name": "repo_b", "workspaces": ["packages/*"]}',
        encoding="utf-8",
    )

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import { Button } from '@/ui/Button'",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:packages/ui/Button.tsx::Button"


def test_resolver_skips_self_repo(tmp_path: Path) -> None:
    """A target with the same repo_id as source is skipped."""
    repo_a = _build_repo_a_with_workspaces(tmp_path)
    repo_b = _build_repo_b_with_alias(tmp_path)

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_a_id",  # same as target -> skip
    )
    qualified = resolver.resolve(
        "import { bar } from '@/foo/utils'",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_when_no_target_has_file(tmp_path: Path) -> None:
    """No target contains the file -> None."""
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    repo_b = _build_repo_b_with_alias(tmp_path)

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import { bar } from '@/foo/utils'",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_for_side_effect_import(tmp_path: Path) -> None:
    """``import 'reflect-metadata'`` has no symbol -> None."""
    repo_a = _build_repo_a_with_workspaces(tmp_path)
    repo_b = _build_repo_b_with_alias(tmp_path)

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import 'reflect-metadata'",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_for_garbage_import(tmp_path: Path) -> None:
    """Unparseable line -> None even with valid targets."""
    repo_a = _build_repo_a_with_workspaces(tmp_path)
    repo_b = _build_repo_b_with_alias(tmp_path)

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "this is not an import",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_finds_via_d_ts_declaration(tmp_path: Path) -> None:
    """Declaration files (``.d.ts``) are also matched as a fallback."""
    repo_a = tmp_path / "repo_a"
    pkg = repo_a / "packages" / "types"
    pkg.mkdir(parents=True)
    (pkg / "index.d.ts").write_text(
        "export type Foo = string\n",
        encoding="utf-8",
    )
    (repo_a / "package.json").write_text(
        '{"name": "repo_a", "workspaces": ["packages/*"]}',
        encoding="utf-8",
    )
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "tsconfig.json").write_text(
        '{"compilerOptions": {"paths": {"@/types/*": ["packages/types/*"]}}}',
        encoding="utf-8",
    )
    (repo_b / "package.json").write_text(
        '{"name": "repo_b", "workspaces": ["packages/*"]}',
        encoding="utf-8",
    )

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import { Foo } from '@/types/index'",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:packages/types/index.d.ts::Foo"


def test_resolver_falls_back_to_bare_root_when_no_workspaces(tmp_path: Path) -> None:
    """Targets without ``workspaces`` declaration still search ``target_root``."""
    repo_a = tmp_path / "repo_a"
    (repo_a / "lib").mkdir(parents=True)
    (repo_a / "lib" / "utils.ts").write_text(
        "export function bar() {}\n",
        encoding="utf-8",
    )
    # No package.json on repo_a -> bare-root fallback only.
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "tsconfig.json").write_text(
        '{"compilerOptions": {"paths": {"@/lib/*": ["lib/*"]}}}',
        encoding="utf-8",
    )

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import { bar } from '@/lib/utils'",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:lib/utils.ts::bar"


def test_resolver_default_import_resolves(tmp_path: Path) -> None:
    """``import bar from '@/foo/utils'`` (default form) also resolves."""
    repo_a = _build_repo_a_with_workspaces(tmp_path)
    repo_b = _build_repo_b_with_alias(tmp_path)

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import bar from '@/foo/utils'",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:packages/foo/utils.ts::bar"


def test_resolver_namespace_import_resolves(tmp_path: Path) -> None:
    """``import * as utils from '@/foo/utils'`` resolves with the namespace name."""
    repo_a = _build_repo_a_with_workspaces(tmp_path)
    repo_b = _build_repo_b_with_alias(tmp_path)

    resolver = TypeScriptResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import * as utils from '@/foo/utils'",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:packages/foo/utils.ts::utils"
