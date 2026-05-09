"""Tests for the cross-repo federation registry (Phase 2 Task 2).

Covers :mod:`better_code_review_graph.federation`:

* ``derive_repo_id`` — deterministic, path-derived identifier.
* ``RepoRegistry.add`` — persists a repo to the ``repos`` table, idempotent
  on re-add, honours user overrides.
* ``RepoRegistry.assign`` — maps a filesystem path back to its owning
  repo_id (longest-match-wins) and raises when no registered root is an
  ancestor.
* ``RepoRegistry`` reload — pre-existing rows are picked up on init so
  subsequent builds don't need to re-``add()``.
* ``RepoRegistry.update_last_indexed_sha`` — round-trips the commit SHA
  to the ``repos.last_indexed_sha`` column.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from better_code_review_graph.federation import (
    RepoRegistry,
    derive_repo_id,
)
from better_code_review_graph.graph import GraphStore

# ---------------------------------------------------------------------------
# derive_repo_id
# ---------------------------------------------------------------------------


def test_derive_repo_id_stable(tmp_path: Path) -> None:
    """Same path -> same id; different paths -> different ids."""
    a = tmp_path / "repo-a"
    b = tmp_path / "repo-b"
    a.mkdir()
    b.mkdir()

    id_a1 = derive_repo_id(a)
    id_a2 = derive_repo_id(a)
    id_b = derive_repo_id(b)

    assert id_a1 == id_a2, "derive_repo_id must be deterministic for the same path"
    assert id_a1 != id_b, "different paths must produce different ids"


def test_derive_repo_id_basename_format(tmp_path: Path) -> None:
    """Format: ``<basename>-<8 lowercase hex chars>``."""
    repo = tmp_path / "my-cool-repo"
    repo.mkdir()

    rid = derive_repo_id(repo)

    assert rid.startswith("my-cool-repo-"), f"unexpected prefix: {rid!r}"
    suffix = rid[len("my-cool-repo-") :]
    assert re.fullmatch(r"[0-9a-f]{8}", suffix), (
        f"suffix must be 8 lowercase hex chars, got {suffix!r}"
    )


def test_derive_repo_id_handles_root_path() -> None:
    """Filesystem-root and dot-only paths normalise to the ``root-`` prefix."""
    rid_root = derive_repo_id(Path("/"))
    assert rid_root.startswith("root-"), f"got {rid_root!r}"
    suffix = rid_root[len("root-") :]
    assert re.fullmatch(r"[0-9a-f]{8}", suffix)


# ---------------------------------------------------------------------------
# RepoRegistry.add — persistence and idempotency
# ---------------------------------------------------------------------------


def test_repo_registry_add_persists_to_repos_table(tmp_path: Path) -> None:
    """``RepoRegistry.add`` writes a row into the ``repos`` table."""
    db_path = tmp_path / "graph.db"
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    store = GraphStore(db_path)
    try:
        registry = RepoRegistry(store)
        repo_id = registry.add(repo_dir, remote_url="https://example.com/r.git")

        row = store._conn.execute(
            "SELECT repo_id, path, remote_url, last_indexed_sha, "
            "first_indexed_at, last_indexed_at FROM repos WHERE repo_id = ?",
            (repo_id,),
        ).fetchone()
        assert row is not None, "row should exist after add()"
        assert row["repo_id"] == repo_id
        assert row["path"] == str(repo_dir.resolve())
        assert row["remote_url"] == "https://example.com/r.git"
        assert row["last_indexed_sha"] is None
        assert isinstance(row["first_indexed_at"], int)
        assert isinstance(row["last_indexed_at"], int)
        assert row["first_indexed_at"] == row["last_indexed_at"], (
            "first/last must coincide on the very first insert"
        )
    finally:
        store.close()


def test_repo_registry_add_is_idempotent(tmp_path: Path) -> None:
    """Re-adding the same path returns the same id and only bumps last_indexed_at."""
    db_path = tmp_path / "graph.db"
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    store = GraphStore(db_path)
    try:
        registry = RepoRegistry(store)
        rid_first = registry.add(repo_dir)
        first_row = store._conn.execute(
            "SELECT first_indexed_at, last_indexed_at FROM repos WHERE repo_id = ?",
            (rid_first,),
        ).fetchone()
        first_at = first_row["first_indexed_at"]

        # Force the wall clock to advance so last_indexed_at can change.
        import time

        time.sleep(1.05)

        rid_second = registry.add(repo_dir)
        second_row = store._conn.execute(
            "SELECT first_indexed_at, last_indexed_at FROM repos WHERE repo_id = ?",
            (rid_second,),
        ).fetchone()

        assert rid_first == rid_second, "idempotent re-add must return the same id"
        assert second_row["first_indexed_at"] == first_at, (
            "first_indexed_at must be preserved across idempotent re-add"
        )
        assert second_row["last_indexed_at"] >= first_at, (
            "last_indexed_at must move forward (or stay) on re-add"
        )

        # And there is exactly one row for this repo_id.
        count = store._conn.execute(
            "SELECT COUNT(*) FROM repos WHERE repo_id = ?", (rid_first,)
        ).fetchone()[0]
        assert count == 1
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Reload semantics
# ---------------------------------------------------------------------------


def test_repo_registry_loads_existing_on_init(tmp_path: Path) -> None:
    """Pre-populated ``repos`` rows are visible on a freshly constructed registry."""
    db_path = tmp_path / "graph.db"
    repo_dir = tmp_path / "preloaded"
    repo_dir.mkdir()
    file_inside = repo_dir / "src" / "thing.py"
    file_inside.parent.mkdir(parents=True)
    file_inside.write_text("# hi\n", encoding="utf-8")

    store = GraphStore(db_path)
    try:
        # Inject a row directly; bypass RepoRegistry.add to simulate an
        # earlier process having populated the table.
        store._conn.execute(
            "INSERT INTO repos (repo_id, path, remote_url, last_indexed_sha, "
            "first_indexed_at, last_indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "preloaded-12345678",
                str(repo_dir.resolve()),
                None,
                None,
                111,
                222,
            ),
        )
        store._conn.commit()

        # Fresh registry — must load the existing row, no add() needed.
        registry = RepoRegistry(store)
        assigned = registry.assign(file_inside)
        assert assigned == "preloaded-12345678"

        entries = registry.entries()
        assert len(entries) == 1
        assert entries[0].repo_id == "preloaded-12345678"
        assert entries[0].first_indexed_at == 111
        assert entries[0].last_indexed_at == 222
    finally:
        store.close()


# ---------------------------------------------------------------------------
# assign()
# ---------------------------------------------------------------------------


def test_repo_registry_assign_returns_correct_repo(tmp_path: Path) -> None:
    """Files under each registered root get the correct repo_id."""
    db_path = tmp_path / "graph.db"
    repo_a = tmp_path / "alpha"
    repo_b = tmp_path / "beta"
    repo_a.mkdir()
    repo_b.mkdir()
    file_a = repo_a / "src" / "a.py"
    file_b = repo_b / "lib" / "b.py"
    file_a.parent.mkdir(parents=True)
    file_b.parent.mkdir(parents=True)
    file_a.write_text("a\n", encoding="utf-8")
    file_b.write_text("b\n", encoding="utf-8")

    store = GraphStore(db_path)
    try:
        registry = RepoRegistry(store)
        rid_a = registry.add(repo_a)
        rid_b = registry.add(repo_b)
        assert rid_a != rid_b

        assert registry.assign(file_a) == rid_a
        assert registry.assign(file_b) == rid_b
    finally:
        store.close()


def test_repo_registry_assign_raises_when_unregistered(tmp_path: Path) -> None:
    """Files outside every registered root surface a clear ``ValueError``."""
    db_path = tmp_path / "graph.db"
    repo = tmp_path / "registered"
    outside = tmp_path / "elsewhere"
    repo.mkdir()
    outside.mkdir()
    stray = outside / "stray.py"
    stray.write_text("x\n", encoding="utf-8")

    store = GraphStore(db_path)
    try:
        registry = RepoRegistry(store)
        registry.add(repo)

        with pytest.raises(ValueError, match="No registered repo"):
            registry.assign(stray)
    finally:
        store.close()


def test_repo_registry_assign_longest_match_wins(tmp_path: Path) -> None:
    """Nested registration: file under child repo resolves to child id.

    Both insertion orders (parent-then-child and child-then-parent) are
    exercised so the longest-match-wins logic does not depend on dict
    iteration order.
    """
    db_path = tmp_path / "graph.db"
    parent = tmp_path / "outer"
    child = parent / "vendor" / "fork"
    child.mkdir(parents=True)
    nested_file = child / "src" / "deep.py"
    nested_file.parent.mkdir(parents=True)
    nested_file.write_text("deep\n", encoding="utf-8")

    parent_only_file = parent / "top.py"
    parent_only_file.write_text("top\n", encoding="utf-8")

    store = GraphStore(db_path)
    try:
        registry = RepoRegistry(store)
        # Insertion order: parent first.
        rid_parent = registry.add(parent)
        rid_child = registry.add(child)
        assert rid_parent != rid_child

        assert registry.assign(nested_file) == rid_child
        assert registry.assign(parent_only_file) == rid_parent
    finally:
        store.close()

    # Reverse insertion order: child first, then parent. Triggers the
    # branch where a shallower root is encountered AFTER a deeper one
    # has already been chosen as best — verifies the comparison is
    # iteration-order-independent.
    db_path2 = tmp_path / "graph2.db"
    store2 = GraphStore(db_path2)
    try:
        registry2 = RepoRegistry(store2)
        rid_child2 = registry2.add(child)
        rid_parent2 = registry2.add(parent)
        assert rid_child2 != rid_parent2

        assert registry2.assign(nested_file) == rid_child2
        assert registry2.assign(parent_only_file) == rid_parent2
    finally:
        store2.close()


# ---------------------------------------------------------------------------
# User overrides
# ---------------------------------------------------------------------------


def test_repo_registry_user_override(tmp_path: Path) -> None:
    """``repo_id_map`` overrides the derived id for matching paths."""
    db_path = tmp_path / "graph.db"
    repo = tmp_path / "overridden"
    repo.mkdir()

    store = GraphStore(db_path)
    try:
        registry = RepoRegistry(
            store,
            repo_id_map={repo: "custom-id"},
        )
        rid = registry.add(repo)
        assert rid == "custom-id", "user override must take precedence"

        # The custom id is what's persisted, and assign() agrees.
        row = store._conn.execute(
            "SELECT repo_id FROM repos WHERE repo_id = ?", ("custom-id",)
        ).fetchone()
        assert row is not None

        file_inside = repo / "x.py"
        file_inside.write_text("x\n", encoding="utf-8")
        assert registry.assign(file_inside) == "custom-id"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# update_last_indexed_sha
# ---------------------------------------------------------------------------


def test_repo_registry_update_last_indexed_sha(tmp_path: Path) -> None:
    """``update_last_indexed_sha`` round-trips through the ``repos`` table."""
    db_path = tmp_path / "graph.db"
    repo = tmp_path / "shaful"
    repo.mkdir()

    store = GraphStore(db_path)
    try:
        registry = RepoRegistry(store)
        rid = registry.add(repo)

        registry.update_last_indexed_sha(rid, "deadbeef1234")

        row = store._conn.execute(
            "SELECT last_indexed_sha FROM repos WHERE repo_id = ?", (rid,)
        ).fetchone()
        assert row["last_indexed_sha"] == "deadbeef1234"

        # In-memory entry mirrors the DB.
        entries = {e.repo_id: e for e in registry.entries()}
        assert entries[rid].last_indexed_sha == "deadbeef1234"

        # Unknown repo_id raises clearly.
        with pytest.raises(ValueError, match="Unknown repo_id"):
            registry.update_last_indexed_sha("does-not-exist", "abc")
    finally:
        store.close()
