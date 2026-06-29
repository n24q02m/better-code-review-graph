"""Tests for the Alembic baseline migration (Phase 2 Task 0).

These tests exercise multiple distinct paths:

* (a) Fresh DB created via ``GraphStore`` reaches alembic head and contains
  every table, index, and Phase 1 summary column from ``_SCHEMA_SQL``.
* (b) Re-initialising ``GraphStore`` on the same DB is idempotent.
* (c) ``downgrade("base")`` followed by ``upgrade("head")`` round-trips
  cleanly without orphaning tables, indexes, or columns.
* (d) A synthetic legacy DB with the Phase 1 ``_SCHEMA_SQL`` schema (no
  ``alembic_version`` table, real data rows preserved) opened via
  ``GraphStore`` reaches alembic head — exercises the auto-stamp branch
  in ``_run_alembic_upgrade``.
* (e) A DB whose ``alembic_version`` row points to a revision the package
  does not ship raises a :class:`RuntimeError` with both the unknown
  revision and the local head in the message.
* (f) ``_SCHEMA_SQL`` and the ``001_baseline``/``002`` migration chain
  produce equivalent table/index structures (parity gate).
* (g) ``_resolve_migrations_dir`` raises :class:`RuntimeError` with both
  attempted layouts in the message when neither resolves.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from better_code_review_graph.graph import (
    _SCHEMA_SQL,
    GraphStore,
    _resolve_migrations_dir,
)

# All tables and indexes that the baseline migration is expected to create.
EXPECTED_TABLES = {"nodes", "edges", "metadata"}
EXPECTED_INDEXES = {
    "idx_nodes_file",
    "idx_nodes_kind",
    "idx_nodes_qualified",
    "idx_edges_source",
    "idx_edges_target",
    "idx_edges_kind",
    "idx_edges_file",
}
SUMMARY_COLUMNS = {"summary", "summary_provider", "source_hash", "source_text"}


def _alembic_config_for(db_path: Path) -> Config:
    """Build an Alembic Config bound to ``db_path`` using the project ini."""
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _current_revision(db_path: Path) -> str | None:
    """Return the revision recorded in ``alembic_version`` (or None)."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if row is None:
            return None
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return rev[0] if rev else None


def _table_names(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(str(db_path))) as conn:
        return {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def _index_names(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(str(db_path))) as conn:
        return {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
            )
        }


def _columns(db_path: Path, table: str) -> set[str]:
    with closing(sqlite3.connect(str(db_path))) as conn:
        # Static table names from this module — safe against SQL injection.
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


_TYPE_AFFINITY_EQUIV = {
    # SQLite type affinity: FLOAT and REAL share the REAL affinity, so a
    # FLOAT column from SQLAlchemy and a REAL column from raw SQL are
    # behaviourally identical.  Normalise them for the parity comparison.
    "FLOAT": "REAL",
}


def _normalise_type(t: str) -> str:
    return _TYPE_AFFINITY_EQUIV.get(t.upper(), t.upper())


def _table_info(db_path: Path, table: str) -> list[tuple]:
    """Return PRAGMA table_info rows (name, type, notnull, dflt, pk) sorted.

    We deliberately drop the cid column from the comparison key so two
    schemas with the same columns in a different order still compare equal
    if column attributes match. Order is not part of the contract — sqlite
    column order can shift across DDL paths and that is fine for our parity
    gate.

    Type strings are normalised through ``_TYPE_AFFINITY_EQUIV`` because
    SQLAlchemy's ``Float`` renders as ``FLOAT`` while raw SQL uses ``REAL``;
    both have REAL affinity in SQLite so the columns are behaviourally
    identical.

    Special-case: an INTEGER PRIMARY KEY column in SQLite is implicitly
    NOT NULL via the PK constraint regardless of whether the DDL spelled
    out ``NOT NULL``.  PRAGMA reports notnull=0 for the raw-SQL form and
    notnull=1 for the alembic form even though they behave identically.
    We normalise PK columns to notnull=1 so the parity gate doesn't trip
    on this cosmetic difference.
    """
    with closing(sqlite3.connect(str(db_path))) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    normalised: list[tuple] = []
    for _cid, name, typ, notnull, dflt, pk in rows:
        normalised_notnull = 1 if pk else notnull
        normalised.append((name, _normalise_type(typ), normalised_notnull, dflt, pk))
    return sorted(normalised)


def _index_list(db_path: Path, table: str) -> list[tuple]:
    """Return PRAGMA index_list rows minus the auto-generated unique indexes.

    We sort by index name and strip the seq column so two equivalent
    schemas compare equal regardless of creation order.
    """
    with closing(sqlite3.connect(str(db_path))) as conn:
        rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
    # PRAGMA index_list returns (seq, name, unique, origin, partial).
    # Skip sqlite_autoindex_* (created automatically for UNIQUE/PK).
    return sorted(
        (name, unique, origin, partial)
        for (_seq, name, unique, origin, partial) in rows
        if not name.startswith("sqlite_autoindex_")
    )


def _head_revision() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    assert head is not None, "alembic must report a head revision"
    return head


# ---------------------------------------------------------------------------
# (a) fresh DB
# ---------------------------------------------------------------------------


def test_fresh_db_reaches_head_with_full_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    store = GraphStore(db_path)
    try:
        # Alembic version table reports head.
        head = _head_revision()
        assert _current_revision(db_path) == head

        # All structural tables present (alembic_version is the bookkeeping
        # table — not part of the application schema).
        tables = _table_names(db_path)
        assert EXPECTED_TABLES.issubset(tables)
        assert "alembic_version" in tables

        # All named indexes present (idx_nodes_source_hash is created by the
        # legacy `_ensure_summary_columns` helper, not by the baseline; it is
        # therefore not enforced here, but if present we tolerate it).
        idx = _index_names(db_path)
        assert EXPECTED_INDEXES.issubset(idx)

        # All four Phase 1 summary columns present.
        cols = _columns(db_path, "nodes")
        assert SUMMARY_COLUMNS.issubset(cols)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# (b) re-init idempotent
# ---------------------------------------------------------------------------


def test_reinit_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"

    store1 = GraphStore(db_path)
    try:
        first_tables = _table_names(db_path)
        first_idx = _index_names(db_path)
        first_cols = _columns(db_path, "nodes")
    finally:
        store1.close()

    store2 = GraphStore(db_path)
    try:
        assert _table_names(db_path) == first_tables
        assert _index_names(db_path) == first_idx
        assert _columns(db_path, "nodes") == first_cols
        # Still at head — no extra revision rows.
        with closing(sqlite3.connect(str(db_path))) as conn:
            count = conn.execute("SELECT COUNT(*) FROM alembic_version").fetchone()[0]
        assert count == 1
    finally:
        store2.close()


# ---------------------------------------------------------------------------
# (c) downgrade -> upgrade round-trip
# ---------------------------------------------------------------------------


def test_downgrade_then_upgrade_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    store = GraphStore(db_path)
    store.close()

    cfg = _alembic_config_for(db_path)

    # Downgrade to base — should drop nodes/edges/metadata + indexes.
    command.downgrade(cfg, "base")
    tables_after_down = _table_names(db_path)
    assert not (EXPECTED_TABLES & tables_after_down), (
        f"orphan tables after downgrade: {EXPECTED_TABLES & tables_after_down}"
    )
    indexes_after_down = _index_names(db_path)
    assert not (EXPECTED_INDEXES & indexes_after_down), (
        f"orphan indexes after downgrade: {EXPECTED_INDEXES & indexes_after_down}"
    )

    # Upgrade back to head — full schema restored.
    command.upgrade(cfg, "head")
    assert _current_revision(db_path) == _head_revision()
    assert EXPECTED_TABLES.issubset(_table_names(db_path))
    assert EXPECTED_INDEXES.issubset(_index_names(db_path))
    assert SUMMARY_COLUMNS.issubset(_columns(db_path, "nodes"))


# ---------------------------------------------------------------------------
# (d) synthetic legacy DB opened via GraphStore exercises auto-stamp branch
# ---------------------------------------------------------------------------


def test_legacy_db_via_graphstore_reaches_head_and_preserves_rows(
    tmp_path: Path,
) -> None:
    """Open a Phase 1-shaped legacy DB through ``GraphStore`` end-to-end.

    Builds a synthetic legacy DB (``executescript(_SCHEMA_SQL)`` + one real
    row) with NO ``alembic_version`` table, then opens it via
    ``GraphStore``.  This must trigger ``_run_alembic_upgrade``'s auto-stamp
    branch (lines marked "needs_stamp" in graph.py): stamp at ``002`` →
    upgrade to head → row preserved.
    """
    legacy_path = tmp_path / "legacy.db"

    # Replay Phase 1 bootstrap exactly: schema + one Function row, NO
    # alembic_version table.
    with closing(sqlite3.connect(str(legacy_path))) as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            """INSERT INTO nodes
               (kind, name, qualified_name, file_path, line_start, line_end,
                language, parent_name, params, return_type, modifiers,
                is_test, file_hash, extra, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "Function",
                "legacy_fn",
                "src/legacy.py::legacy_fn",
                "src/legacy.py",
                1,
                10,
                "python",
                None,
                "()",
                "None",
                None,
                0,
                "deadbeef",
                "{}",
                1700000000.0,
            ),
        )
        conn.commit()

    # Sanity: no alembic_version yet.
    assert _current_revision(legacy_path) is None

    # This is the production code path: opening the legacy DB triggers
    # _run_alembic_upgrade with needs_stamp=True, then upgrade("head").
    store = GraphStore(legacy_path)
    try:
        # Auto-stamp + upgrade succeeded; now at head.
        assert _current_revision(legacy_path) == _head_revision()

        # The pre-existing row is still queryable.
        row = store._conn.execute(
            "SELECT name, file_path FROM nodes WHERE qualified_name = ?",
            ("src/legacy.py::legacy_fn",),
        ).fetchone()
        assert row is not None
        assert row["name"] == "legacy_fn"
        assert row["file_path"] == "src/legacy.py"
    finally:
        store.close()


def test_legacy_db_low_level_stamp_then_upgrade(tmp_path: Path) -> None:
    """Low-level smoke check that ``alembic stamp 002`` works in isolation.

    Complements the higher-level test above (which goes through
    ``GraphStore``) by verifying that the alembic primitives do what we
    expect, independent of our stamp logic.
    """
    db_path = tmp_path / "legacy.db"

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    cfg = _alembic_config_for(db_path)
    command.stamp(cfg, "002")
    assert _current_revision(db_path) == "002"

    command.upgrade(cfg, "head")
    assert _current_revision(db_path) == _head_revision()
    assert EXPECTED_TABLES.issubset(_table_names(db_path))
    assert SUMMARY_COLUMNS.issubset(_columns(db_path, "nodes"))


# ---------------------------------------------------------------------------
# (e) unknown revision raises a clear error
# ---------------------------------------------------------------------------


def test_unknown_alembic_revision_raises_runtime_error(tmp_path: Path) -> None:
    """If ``alembic_version`` references an unshipped revision, surface it.

    We bring a DB to head normally, then forge ``alembic_version`` to point
    at a fake ``999`` revision.  Re-opening via ``GraphStore`` must raise
    :class:`RuntimeError` (not the opaque ``alembic.util.exc.CommandError``)
    with both the unknown revision and the local head spelt out so the
    operator can decide between downgrading the package and recreating
    the DB.
    """
    db_path = tmp_path / "future.db"

    # Create a healthy DB at head, then close.
    store = GraphStore(db_path)
    store.close()

    # Forge a future revision the package does not ship.
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("UPDATE alembic_version SET version_num = '999'")
        conn.commit()

    head = _head_revision()
    with pytest.raises(RuntimeError) as excinfo:
        GraphStore(db_path)

    msg = str(excinfo.value)
    assert "999" in msg, f"unknown revision should appear in message: {msg!r}"
    assert head in msg, f"local head {head!r} should appear in message: {msg!r}"
    assert str(db_path) in msg, f"db path should appear in message: {msg!r}"


# ---------------------------------------------------------------------------
# (f) _SCHEMA_SQL <-> 001+002 parity gate
# ---------------------------------------------------------------------------


def test_schema_sql_matches_alembic_migrations(tmp_path: Path) -> None:
    """``_SCHEMA_SQL`` is equivalent to the alembic state at revision ``002``.

    Builds two SQLite files: one via ``executescript(_SCHEMA_SQL)`` only,
    one via ``command.upgrade(cfg, "002")`` only.  For each application
    table, asserts ``PRAGMA table_info`` and ``PRAGMA index_list`` rows
    match.

    The comparison is intentionally pinned at ``002`` rather than
    ``head``: ``_SCHEMA_SQL`` is the legacy in-code bootstrap frozen at
    the v1.6 release line, and any new schema (Phase 2 federation
    onwards) goes through alembic only. ``003_federation`` adds
    ``repo_id`` columns + a ``repos`` table that ``_SCHEMA_SQL`` does
    NOT carry — by design — so comparing against ``head`` would
    spuriously fail for every future additive migration.

    Documented exception: ``idx_nodes_source_hash`` is created by the
    legacy ``_ensure_summary_columns`` helper, not by either path here, so
    it appears in NEITHER comparison.  If it ever appears in only one,
    that helper has been wired into the wrong path.
    """
    schema_sql_db = tmp_path / "schema_sql.db"
    alembic_db = tmp_path / "alembic.db"

    with closing(sqlite3.connect(str(schema_sql_db))) as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    cfg = _alembic_config_for(alembic_db)
    command.upgrade(cfg, "002")

    for table in sorted(EXPECTED_TABLES):
        sql_info = _table_info(schema_sql_db, table)
        alembic_info = _table_info(alembic_db, table)
        assert sql_info == alembic_info, (
            f"table_info diverges for {table!r}\n"
            f"  _SCHEMA_SQL: {sql_info}\n"
            f"  alembic:     {alembic_info}"
        )

        sql_idx = _index_list(schema_sql_db, table)
        alembic_idx = _index_list(alembic_db, table)
        assert sql_idx == alembic_idx, (
            f"index_list diverges for {table!r}\n"
            f"  _SCHEMA_SQL: {sql_idx}\n"
            f"  alembic:     {alembic_idx}"
        )

    # Documented exception: idx_nodes_source_hash must appear in NEITHER
    # path here (only in the legacy helper).
    assert "idx_nodes_source_hash" not in _index_names(schema_sql_db)
    assert "idx_nodes_source_hash" not in _index_names(alembic_db)


# ---------------------------------------------------------------------------
# (g) _resolve_migrations_dir failure mode is observable
# ---------------------------------------------------------------------------


def test_resolve_migrations_dir_returns_real_path() -> None:
    """The resolver returns a real on-disk directory containing env.py."""
    resolved = _resolve_migrations_dir()
    assert isinstance(resolved, Path)
    assert resolved.is_dir(), f"resolver returned non-directory: {resolved}"
    assert (resolved / "env.py").is_file(), (
        f"resolver returned dir without env.py: {resolved}"
    )


def test_resolve_migrations_dir_raises_when_nothing_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both layouts fail → :class:`RuntimeError` lists both attempts.

    We force the importlib.resources branch to raise ``ModuleNotFoundError``
    and redirect the source-checkout fallback at a sandbox tmp_path that
    doesn't contain ``env.py``.  The final RuntimeError must mention BOTH
    attempted paths so the failure is diagnosable.
    """
    # Block the installed-wheel resolution.
    import importlib.resources as _resources

    def _raise(name: str) -> object:
        raise ModuleNotFoundError(f"forced-missing: {name}")

    monkeypatch.setattr(_resources, "files", _raise)

    # Redirect the source-checkout fallback at a directory missing env.py.
    # We patch __file__ via a fake module path so `Path(__file__).parent.parent.parent / "migrations"`
    # lands in tmp_path/<missing>.
    fake_root = tmp_path / "src" / "better_code_review_graph"
    fake_root.mkdir(parents=True)
    fake_graph = fake_root / "graph.py"
    fake_graph.write_text("")
    # The migrations dir we WANT to be missing:
    expected_fallback = tmp_path / "migrations"
    assert not expected_fallback.exists()

    # Patch the module-level __file__ so the source fallback resolves into
    # tmp_path (where there is no migrations/env.py).
    import better_code_review_graph.graph as graph_mod

    monkeypatch.setattr(graph_mod, "__file__", str(fake_graph))

    with pytest.raises(RuntimeError) as excinfo:
        _resolve_migrations_dir()

    msg = str(excinfo.value)
    assert "forced-missing" in msg or "installed package" in msg, (
        f"installed-package attempt should appear: {msg!r}"
    )
    assert str(expected_fallback) in msg, (
        f"source-checkout attempt should appear: {msg!r}"
    )


def test_resolve_migrations_dir_falls_back_to_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the installed-wheel import fails, the source-checkout path wins.

    Forces ``importlib.resources.files`` to raise ``ModuleNotFoundError`` so
    only the source-checkout fallback can succeed; relies on the real
    repository ``migrations/env.py`` being present (this test runs from a
    source checkout, which by definition has it).
    """
    import importlib.resources as _resources

    def _raise(name: str) -> object:
        raise ModuleNotFoundError(f"forced-missing: {name}")

    monkeypatch.setattr(_resources, "files", _raise)

    resolved = _resolve_migrations_dir()
    repo_root = Path(__file__).resolve().parent.parent
    assert resolved == repo_root / "migrations"
    assert (resolved / "env.py").is_file()


def test_resolve_migrations_dir_handles_multiplexed_path_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for C1: Path(str(MultiplexedPath(...))) is junk.

    Simulates the installed-wheel layout where ``importlib.resources.files``
    returned an object whose ``__str__`` was the repr (the historical bug).
    The resolver must NOT do ``Path(str(ref))`` and must instead use
    ``ref.joinpath("env.py")`` (which returns a real ``pathlib.Path`` for
    filesystem-backed resources).  Falls through to source-checkout
    fallback on this specific test mock because the mocked joinpath
    doesn't return a real ``pathlib.Path``.
    """
    import importlib.resources as _resources

    class _FakeMultiplexedPath:
        def __init__(self, path: Path) -> None:
            self._path = path

        def __repr__(self) -> str:  # the trap
            return f"MultiplexedPath('{self._path}')"

        def __str__(self) -> str:  # __str__ falls back to repr
            return repr(self)

        def joinpath(self, name: str) -> object:
            # Return a non-Path traversable to force the fallback branch.
            return _FakeTraversable(self._path / name)

    class _FakeTraversable:
        def __init__(self, path: Path) -> None:
            self._path = path

        def is_file(self) -> bool:
            return self._path.is_file()

    fake_dir = Path(__file__).resolve().parent.parent / "migrations"

    def _files(name: str) -> object:
        return _FakeMultiplexedPath(fake_dir)

    monkeypatch.setattr(_resources, "files", _files)
    obj = _files("better_code_review_graph_migrations")
    # Some library versions had an issue where ``importlib.resources.files``
    # returned an object whose ``__str__`` was the repr (the historical bug).
    assert str(obj) == f"MultiplexedPath('{fake_dir}')"

    # Falls through installed-wheel branch (joinpath result not a Path)
    # → resolves via source-checkout fallback. Both paths exist in the
    # checkout, so we should get a working migrations dir back.
    resolved = _resolve_migrations_dir()
    assert (resolved / "env.py").is_file()


# ---------------------------------------------------------------------------
# Cross-check: `alembic current` matches MigrationContext
# ---------------------------------------------------------------------------


def test_alembic_current_via_runtime_context(tmp_path: Path) -> None:
    """``MigrationContext.get_current_revision`` agrees with our helper, AND
    ``command.current(cfg)`` reaches the same head via alembic's own logging.

    The previous version of this test only asserted that ``command.current``
    didn't raise (near-zero signal).  We now verify that the runtime-context
    revision matches ``_head_revision()`` AND that an independent
    ``ScriptDirectory`` lookup agrees, so a regression in either side surfaces
    immediately.
    """
    from sqlalchemy import create_engine

    db_path = tmp_path / "g.db"
    store = GraphStore(db_path)
    try:
        cfg = _alembic_config_for(db_path)
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            with engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                head = _head_revision()
                assert ctx.get_current_revision() == head
        finally:
            engine.dispose()

        # Cross-check via a fresh ScriptDirectory: the head reported by the
        # cfg + script API must match the one stamped in alembic_version.
        script = ScriptDirectory.from_config(cfg)
        assert script.get_current_head() == head

        # And command.current must not raise — the original near-zero
        # smoke check, retained as a regression guard against alembic API
        # shape changes.
        command.current(cfg)
    finally:
        store.close()


@pytest.mark.parametrize(
    "target",
    ["head", "001", "002"],
)
def test_alembic_upgrade_to_target(target: str, tmp_path: Path) -> None:
    """Upgrading to each named target reaches the expected revision.

    ``head`` and ``002`` both resolve to ``002`` (head is currently 002);
    ``001`` stops at the baseline.  The point of parameterising here is to
    catch regressions where an intermediate revision label fails to apply
    cleanly (e.g. someone authors a migration whose ``upgrade`` raises
    only when invoked on an empty DB).
    """
    db_path = tmp_path / f"smoke_{target}.db"
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, target)
    expected = _head_revision() if target == "head" else target
    assert _current_revision(db_path) == expected


# ---------------------------------------------------------------------------
# Coverage helper: alembic stamp branch when alembic_version exists empty
# ---------------------------------------------------------------------------


def test_legacy_db_with_empty_alembic_version_table_stamps(tmp_path: Path) -> None:
    """Edge case: ``alembic_version`` exists but has zero rows.

    This mimics an interrupted prior alembic run that created the
    bookkeeping table but never recorded a revision.  ``_run_alembic_upgrade``
    must detect this and stamp at 002 before upgrading.
    """
    db_path = tmp_path / "interrupted.db"

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.commit()

    assert _current_revision(db_path) is None

    # The empty alembic_version table mocks the "needs_stamp via empty row"
    # branch in graph.py: command.stamp(cfg, "002") fires and upgrade
    # succeeds.
    store = GraphStore(db_path)
    try:
        assert _current_revision(db_path) == _head_revision()
    finally:
        store.close()
