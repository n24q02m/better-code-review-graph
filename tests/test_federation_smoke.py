"""Phase 2 Task 12: end-to-end smoke tests against a 3-repo fixture.

Spins up a real multi-repo workspace (Python lib + Python app + TS app +
Go service), runs the federated build path
(``build_or_update_graph(roots=[...])``), and asserts the cross-repo
machinery actually fires:

* All registered repos land in the ``repos`` table with deterministic ids.
* Nodes are stamped with the correct ``repo_id``.
* Cross-repo ``IMPORTS_FROM`` edges from ``py_app/main.py`` to
  ``py_lib/retry.py`` are rewritten to the federated qualified name
  ``<py_lib_id>:src/py_lib/retry.py::retry``.
* The ``repo`` query filter scopes results to a single repo.
* The default (no filter) call surfaces nodes from every repo.
* :func:`incremental_update` refreshes ``last_indexed_sha`` against the
  current git ``HEAD`` when a registry is wired in.

Fixture layout (Option B from the plan, with a 4th Python app added so
there is a meaningful cross-repo edge — TS/Go don't import Python at the
source level, so we keep them as smoke for the resolver dispatcher and
add ``py_app`` as the importer of ``py_lib``):

    workspace/
    .git/                           # primary root (where the DB lives)
    .code-review-graph/
    py_lib/                         # Python library
        .git/
        pyproject.toml              # name = "py_lib"
        src/py_lib/__init__.py
        src/py_lib/retry.py         # def retry(attempts: int) -> bool
    py_app/                         # Python app, depends on py_lib
        .git/
        pyproject.toml              # dependencies = ["py_lib"]
        src/app/main.py             # from py_lib.retry import retry
    ts_app/                         # TypeScript app (smoke for dispatcher)
        package.json
        tsconfig.json
        src/index.ts
    go_service/                     # Go service (smoke for dispatcher)
        go.mod
        main.go
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from better_code_review_graph.federation import RepoRegistry
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.incremental import incremental_update
from better_code_review_graph.tools import (
    build_or_update_graph,
    semantic_search_nodes,
)

# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


def _write_py_lib(root: Path) -> None:
    """Python library repo with a single ``retry`` function."""
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "py_lib"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8",
    )
    pkg = root / "src" / "py_lib"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "retry.py").write_text(
        "def retry(attempts: int) -> bool:\n    return attempts > 0\n",
        encoding="utf-8",
    )


def _write_py_app(root: Path) -> None:
    """Python app repo that imports ``retry`` from ``py_lib``."""
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "py_app"\nversion = "0.1.0"\ndependencies = ["py_lib"]\n',
        encoding="utf-8",
    )
    pkg = root / "src" / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    # ``do_retry`` deliberately shares the substring ``retry`` so a
    # keyword search picks up both this app and ``py_lib`` — letting
    # the smoke verify that the default (no ``repo`` filter) call
    # really crosses repo boundaries.
    (pkg / "main.py").write_text(
        "from os import path\n"
        "from py_lib.retry import retry\n"
        "\n"
        "def do_retry() -> bool:\n"
        "    _ = path\n"
        "    return retry(3)\n",
        encoding="utf-8",
    )


def _write_ts_app(root: Path) -> None:
    """Minimal TypeScript app — no cross-repo imports, dispatcher smoke only."""
    root.mkdir()
    (root / ".git").mkdir()
    (root / "package.json").write_text(
        '{"name":"ts_app","version":"0.1.0"}\n', encoding="utf-8"
    )
    (root / "tsconfig.json").write_text(
        '{"compilerOptions":{"target":"ES2022","module":"ESNext"}}\n',
        encoding="utf-8",
    )
    src = root / "src"
    src.mkdir()
    (src / "index.ts").write_text(
        "export function greet(name: string): string {\n"
        "    return `hello ${name}`;\n"
        "}\n",
        encoding="utf-8",
    )


def _write_go_service(root: Path) -> None:
    """Minimal Go service — no cross-repo imports, dispatcher smoke only."""
    root.mkdir()
    (root / ".git").mkdir()
    (root / "go.mod").write_text(
        "module example.com/go_service\n\ngo 1.22\n",
        encoding="utf-8",
    )
    (root / "main.go").write_text(
        'package main\n\nfunc main() {\n\tprintln("hi")\n}\n',
        encoding="utf-8",
    )


@pytest.fixture
def federation_workspace(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Build the 4-root workspace and run a federated build.

    Yields a dict with ``workspace`` (primary root), each repo's path,
    each repo's resolved ``repo_id``, and the ``GraphStore`` left open
    for test inspection. Caller doesn't need to close the store — the
    fixture handles teardown.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    (workspace / ".code-review-graph").mkdir()

    py_lib = workspace / "py_lib"
    py_app = workspace / "py_app"
    ts_app = workspace / "ts_app"
    go_service = workspace / "go_service"

    _write_py_lib(py_lib)
    _write_py_app(py_app)
    _write_ts_app(ts_app)
    _write_go_service(go_service)

    result = build_or_update_graph(
        full_rebuild=True,
        repo_root=str(workspace),
        roots=[str(py_lib), str(py_app), str(ts_app), str(go_service)],
    )
    assert result["status"] == "ok", result

    db_path = workspace / ".code-review-graph" / "graph.db"
    store = GraphStore(str(db_path))

    # Map every registered path -> repo_id so tests can look up by name.
    rows = store._conn.execute("SELECT repo_id, path FROM repos").fetchall()
    by_path = {Path(r["path"]).resolve(): r["repo_id"] for r in rows}

    yield {
        "workspace": workspace,
        "py_lib": py_lib,
        "py_app": py_app,
        "ts_app": ts_app,
        "go_service": go_service,
        "store": store,
        "db_path": db_path,
        "build_result": result,
        "py_lib_id": by_path.get(py_lib.resolve()),
        "py_app_id": by_path.get(py_app.resolve()),
        "ts_app_id": by_path.get(ts_app.resolve()),
        "go_service_id": by_path.get(go_service.resolve()),
        "workspace_id": by_path.get(workspace.resolve()),
    }
    store.close()


# ---------------------------------------------------------------------------
# 1: build path returns OK
# ---------------------------------------------------------------------------


def test_three_repo_federation_build_succeeds(
    federation_workspace: dict[str, Any],
) -> None:
    """``build_or_update_graph(roots=[...])`` over 4 roots returns status=ok.

    The fixture itself runs the build; this test asserts the post-build
    status surface — a regression in the federated build path would
    surface as ``status='error'`` here before any deeper test fires.
    """
    result = federation_workspace["build_result"]
    assert result["status"] == "ok"
    assert result["build_type"] == "full_federated"
    # Primary workspace + 4 explicit roots = 5 entries in the result.
    assert len(result["roots"]) == 5
    # At minimum the Python files are parsed; TS/Go also count if the
    # platform has a tree-sitter parser registered for them.
    assert result["files_parsed"] >= 4


# ---------------------------------------------------------------------------
# 2: repos table persistence
# ---------------------------------------------------------------------------


def test_three_repo_federation_persists_repos_table(
    federation_workspace: dict[str, Any],
) -> None:
    """Every registered root lands in the ``repos`` table with a unique id."""
    store: GraphStore = federation_workspace["store"]

    rows = store._conn.execute(
        "SELECT repo_id, path FROM repos ORDER BY path"
    ).fetchall()
    paths = {Path(r["path"]).resolve() for r in rows}

    expected = {
        federation_workspace["workspace"].resolve(),
        federation_workspace["py_lib"].resolve(),
        federation_workspace["py_app"].resolve(),
        federation_workspace["ts_app"].resolve(),
        federation_workspace["go_service"].resolve(),
    }
    assert expected.issubset(paths), f"missing repos in registry: {expected - paths}"

    # Ids match the deterministic ``<basename>-<sha8>`` shape.
    assert federation_workspace["py_lib_id"]
    assert federation_workspace["py_lib_id"].startswith("py_lib-")
    assert federation_workspace["py_app_id"]
    assert federation_workspace["py_app_id"].startswith("py_app-")
    assert federation_workspace["ts_app_id"]
    assert federation_workspace["ts_app_id"].startswith("ts_app-")
    assert federation_workspace["go_service_id"]
    assert federation_workspace["go_service_id"].startswith("go_service-")
    # All distinct — different basenames + different paths.
    repo_ids = {
        federation_workspace["py_lib_id"],
        federation_workspace["py_app_id"],
        federation_workspace["ts_app_id"],
        federation_workspace["go_service_id"],
    }
    assert len(repo_ids) == 4


# ---------------------------------------------------------------------------
# 3: cross-repo IMPORTS_FROM edge generation
# ---------------------------------------------------------------------------


def test_three_repo_federation_emits_cross_repo_imports_from_edge(
    federation_workspace: dict[str, Any],
) -> None:
    """``from py_lib.retry import retry`` -> federated qualified target.

    Expected target shape from
    :class:`better_code_review_graph.resolver.python.PythonResolver`:
    ``<py_lib_id>:src/py_lib/retry.py::retry``.
    """
    store: GraphStore = federation_workspace["store"]
    py_lib_id: str = federation_workspace["py_lib_id"]

    rows = store._conn.execute(
        "SELECT source_qualified, target_qualified, repo_id "
        "FROM edges WHERE kind = 'IMPORTS_FROM'"
    ).fetchall()
    targets = [r["target_qualified"] for r in rows]
    expected = f"{py_lib_id}:src/py_lib/retry.py::retry"
    assert expected in targets, (
        f"cross-repo IMPORTS_FROM edge not rewritten; "
        f"expected target {expected!r} in {targets!r}"
    )


# ---------------------------------------------------------------------------
# 4: query repo filter narrows to a single repo
# ---------------------------------------------------------------------------


def test_three_repo_federation_query_with_repo_filter(
    federation_workspace: dict[str, Any],
) -> None:
    """``semantic_search_nodes(repo=py_lib_id)`` returns only py_lib hits."""
    workspace: Path = federation_workspace["workspace"]
    py_lib_id: str = federation_workspace["py_lib_id"]

    result = semantic_search_nodes(
        query="retry",
        repo_root=str(workspace),
        repo=py_lib_id,
    )

    assert result["status"] == "ok", result
    assert result["results"], "expected at least one match in py_lib"
    for n in result["results"]:
        fp = n["file_path"]
        assert "py_lib" in fp, f"unexpected non-py_lib hit: {fp!r}"
        assert "py_app" not in fp, f"py_app leaked into py_lib filter: {fp!r}"


# ---------------------------------------------------------------------------
# 5: default (no filter) returns nodes from multiple repos
# ---------------------------------------------------------------------------


def test_three_repo_federation_query_default_returns_all(
    federation_workspace: dict[str, Any],
) -> None:
    """No ``repo`` kwarg -> nodes from both py_lib and py_app are visible."""
    workspace: Path = federation_workspace["workspace"]

    result = semantic_search_nodes(
        query="retry",
        repo_root=str(workspace),
    )

    assert result["status"] == "ok", result
    file_paths = {n["file_path"] for n in result["results"]}
    has_lib = any("py_lib" in fp for fp in file_paths)
    has_app = any("py_app" in fp for fp in file_paths)
    assert has_lib and has_app, (
        f"expected matches from both py_lib and py_app, got {file_paths}"
    )


# ---------------------------------------------------------------------------
# 6: nodes carry the correct repo_id
# ---------------------------------------------------------------------------


def test_three_repo_federation_node_repo_id_persisted(
    federation_workspace: dict[str, Any],
) -> None:
    """Nodes parsed under each root carry the matching ``repo_id`` column."""
    store: GraphStore = federation_workspace["store"]
    py_lib_id: str = federation_workspace["py_lib_id"]
    py_app_id: str = federation_workspace["py_app_id"]
    py_lib: Path = federation_workspace["py_lib"]
    py_app: Path = federation_workspace["py_app"]

    # py_lib's retry.py file -> repo_id == py_lib_id.
    retry_py = (py_lib / "src" / "py_lib" / "retry.py").resolve()
    rows = store._conn.execute(
        "SELECT repo_id, name FROM nodes WHERE file_path = ?",
        (str(retry_py),),
    ).fetchall()
    assert rows, f"no nodes for {retry_py}"
    for r in rows:
        assert r["repo_id"] == py_lib_id, (
            f"py_lib node {r['name']} has wrong repo_id: {r['repo_id']!r}"
        )

    # py_app's main.py file -> repo_id == py_app_id.
    main_py = (py_app / "src" / "app" / "main.py").resolve()
    rows = store._conn.execute(
        "SELECT repo_id, name FROM nodes WHERE file_path = ?",
        (str(main_py),),
    ).fetchall()
    assert rows, f"no nodes for {main_py}"
    for r in rows:
        assert r["repo_id"] == py_app_id, (
            f"py_app node {r['name']} has wrong repo_id: {r['repo_id']!r}"
        )


# ---------------------------------------------------------------------------
# 7: incremental update refreshes last_indexed_sha
# ---------------------------------------------------------------------------


def test_three_repo_federation_last_indexed_sha_recorded(
    tmp_path: Path,
) -> None:
    """``incremental_update(... repo_registry=...)`` refreshes ``last_indexed_sha``.

    Initialises a real git repo (so ``get_head_sha`` returns a value)
    and confirms the column round-trips against ``git rev-parse HEAD``.
    """
    repo = tmp_path / "py_lib"
    _write_py_lib(repo)

    # Replace the placeholder ``.git`` dir with a real repo.
    (repo / ".git").rmdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.invalid"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head, "git rev-parse HEAD returned empty"

    crg_dir = repo / ".code-review-graph"
    crg_dir.mkdir()
    db_path = crg_dir / "graph.db"

    store = GraphStore(str(db_path))
    try:
        registry = RepoRegistry(store)
        repo_id = registry.add(repo)

        result = incremental_update(repo, store, repo_registry=registry)
        # No prior baseline -> incremental sees no changes; the registry
        # SHA is still expected to advance to HEAD on the no-op path.
        assert "files_updated" in result

        row = store._conn.execute(
            "SELECT last_indexed_sha FROM repos WHERE repo_id = ?",
            (repo_id,),
        ).fetchone()
        assert row is not None
        assert row["last_indexed_sha"] == head, (
            f"last_indexed_sha {row['last_indexed_sha']!r} != git HEAD {head!r}"
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# 8: unresolved (stdlib) imports stay as bare references
# ---------------------------------------------------------------------------


def test_three_repo_smoke_unresolved_import_stays_within_repo(
    federation_workspace: dict[str, Any],
) -> None:
    """``from os import path`` -> target stays bare, no ``<repo_id>:`` prefix.

    Stdlib modules are not registered as federated repos, so the
    cross-repo resolver must not invent a fake ``<repo_id>:`` prefix
    for them. The IMPORTS_FROM edge target should remain the bare
    module name (``os``) the parser extracted, untouched by the
    federation post-processing.
    """
    store: GraphStore = federation_workspace["store"]
    py_app: Path = federation_workspace["py_app"]

    main_py = (py_app / "src" / "app" / "main.py").resolve()
    rows = store._conn.execute(
        "SELECT target_qualified FROM edges "
        "WHERE kind = 'IMPORTS_FROM' AND source_qualified = ?",
        (str(main_py),),
    ).fetchall()
    targets = [r["target_qualified"] for r in rows]
    assert targets, f"no IMPORTS_FROM edges for {main_py}"

    # Collect every registered repo_id so we can assert the unresolved
    # edge does NOT spoof any of them.
    registered_ids = {
        federation_workspace["workspace_id"],
        federation_workspace["py_lib_id"],
        federation_workspace["py_app_id"],
        federation_workspace["ts_app_id"],
        federation_workspace["go_service_id"],
    }
    registered_ids.discard(None)

    # The ``os`` import is stdlib -> the resolver returns None, so the
    # target_qualified must stay as the bare module name (no colon
    # prefix at all) the parser emitted.
    os_targets = [t for t in targets if t == "os" or t.endswith("::os")]
    assert os_targets, (
        f"expected an unresolved 'os' IMPORTS_FROM edge, got targets={targets!r}"
    )
    for t in os_targets:
        for rid in registered_ids:
            assert not t.startswith(f"{rid}:"), (
                f"unresolved stdlib import was spoofed with repo_id prefix: "
                f"{t!r} starts with {rid!r}"
            )
