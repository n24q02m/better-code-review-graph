"""Tests for Phase 3 Task 1 — pre-flight backup-before-migrate hook.

The Phase 3 (v2.0.0) BREAKING migration ``005_temporal_columns`` will
restructure ``nodes``/``edges`` for security-aware nodes + temporal
tracking.  Before that migration ships, we add a safety net:

1. **Backup**: when ``GraphStore.__init__`` opens a DB whose alembic
   target head is ``005`` or later AND the DB itself is at a pre-005
   revision (None / 001 / 002 / 003 / 004), a ``shutil.copy2`` of the
   DB file is taken to ``<db>.pre-2.0.bak`` BEFORE
   ``command.upgrade(cfg, "head")`` runs.  Idempotent — if the backup
   already exists (prior partial run), it is not overwritten.

2. **Downgrade**: when ``CRG_DOWNGRADE_TO_1_X=1`` is set in the
   environment and a ``<db>.pre-2.0.bak`` exists, the current DB is
   archived to ``<db>.post-2.0.archived`` and the backup is restored
   in place; the alembic upgrade is then skipped (the restored DB is
   at v1.x revision and that's the user's intent).  If the env var is
   set but no backup exists, a clear :class:`RuntimeError` is raised.

These tests must work BEFORE migration 005 ships: we monkeypatch
``ScriptDirectory.get_current_head`` to return ``"005"`` to simulate
the post-005 world.  Today's real head is still pre-005 (currently
``004`` after Phase 3 Task 2 added ``security_tags``), so the hook
is a no-op on the production code path until the BREAKING migration
lands.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

import better_code_review_graph.graph as graph_mod
from better_code_review_graph.graph import GraphStore


def _alembic_config_for(db_path: Path) -> Config:
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _stamp(db_path: Path, revision: str) -> None:
    """Bring a fresh DB up through alembic to ``revision``."""
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, revision)


# The session-scoped autouse fixture in ``tests/conftest.py``
# (``_session_git_tempdir``) initialises a git repo at the pytest
# basetemp so every per-test ``tmp_path`` walks up to ``.git`` cleanly.
# Migration 005 therefore resolves ``git rev-parse HEAD`` end-to-end
# without per-module fixtures.


def _current_revision(db_path: Path) -> str | None:
    with closing(sqlite3.connect(str(db_path))) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if row is None:
            return None
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return rev[0] if rev else None


def _force_target_head(monkeypatch: pytest.MonkeyPatch, head: str) -> None:
    """Make ``ScriptDirectory.get_current_head`` report ``head`` everywhere
    ``graph._run_alembic_upgrade`` resolves it.

    The hook reads the target head via ``ScriptDirectory.from_config(cfg).get_current_head()``;
    we patch the unbound method so every fresh ``ScriptDirectory`` instance
    that ``_run_alembic_upgrade`` builds reports the simulated head.
    """
    monkeypatch.setattr(
        ScriptDirectory, "get_current_head", lambda self: head, raising=True
    )


# ---------------------------------------------------------------------------
# (1) Backup created when crossing rev 005
# ---------------------------------------------------------------------------


def test_backup_created_when_crossing_rev_005(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DB at rev 002, simulated head at 005 → backup file produced.

    We bring a real DB to revision ``002`` via alembic so it has the
    Phase 1/2 schema rows alembic records, then monkeypatch
    ``get_current_head`` to ``"005"`` so the hook believes a BREAKING
    migration is about to run.  The hook must copy the DB to
    ``<db>.pre-2.0.bak`` BEFORE the upgrade is attempted.

    Because the simulated head ``005`` is not a revision alembic can
    resolve, the upgrade itself will fail — that's fine for this test:
    we assert the backup was created (timing: BEFORE upgrade) and let
    the failure propagate.
    """
    db_path = tmp_path / "graph.db"
    _stamp(db_path, "002")
    assert _current_revision(db_path) == "002"

    backup_path = db_path.with_suffix(".pre-2.0.bak")
    assert not backup_path.exists()

    _force_target_head(monkeypatch, "005")

    # The hook reads ``ScriptDirectory.get_current_head()`` and sees
    # ``"005"``, so it takes a backup before invoking
    # ``command.upgrade(cfg, "head")``.  alembic itself resolves
    # "head" via its own internal walk of the script directory and
    # will land at the real shipped head ("003"), which is fine for
    # this assertion: the backup file must exist regardless of where
    # the upgrade ended up.
    store = GraphStore(db_path)
    try:
        assert backup_path.exists(), (
            f"backup {backup_path} should be created when target head crosses 005"
        )
        # Backup contents match the rev-002 DB (the source of the copy).
        with closing(sqlite3.connect(str(backup_path))) as conn:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert row[0] == "002", f"backup should preserve rev 002; got {row[0]!r}"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# (2) Backup skipped when DB already at 005 or above
# ---------------------------------------------------------------------------


def test_backup_skipped_when_already_at_005_or_above(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DB already at rev 005 — no backup needed (we're past the boundary).

    We synthesize a DB that alembic considers at revision ``005`` by
    stamping (without running a real migration) and then patch
    ``get_current_head`` to ``"005"`` so target == current.  The hook
    must NOT create a backup file.
    """
    db_path = tmp_path / "graph.db"
    _stamp(db_path, "head")  # bring schema up
    # Forge alembic_version to "005" so the hook sees current_rev=="005"
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("UPDATE alembic_version SET version_num = '005'")
        conn.commit()

    backup_path = db_path.with_suffix(".pre-2.0.bak")
    assert not backup_path.exists()

    _force_target_head(monkeypatch, "005")

    # GraphStore will fail at command.upgrade("head") because alembic
    # can't resolve revision 005; the relevant assertion is whether the
    # backup was attempted before the failure.  Either path (success or
    # raise) must NOT produce a backup.
    try:
        store = GraphStore(db_path)
        store.close()
    except Exception:
        pass

    assert not backup_path.exists(), (
        "backup must not be created when DB is already at/past rev 005"
    )


# ---------------------------------------------------------------------------
# (3) Backup skipped when target below 005
# ---------------------------------------------------------------------------


def test_backup_taken_on_real_head_005_chain(tmp_path: Path) -> None:
    """DB at rev 001, real head at ``005`` — backup IS taken (boundary crossed).

    No monkeypatch — Phase 3 Task 6 lands the real BREAKING migration
    at revision ``005``. The hook fires for any DB at a pre-005
    revision because ``GraphStore`` will walk it up through the
    ``005_temporal_columns`` migration. This pins the real-world
    upgrade path: the fixture's autouse ``_init_git`` makes the
    backfill succeed end-to-end, so the chain runs to head and the
    backup file remains on disk afterwards.
    """
    db_path = tmp_path / "graph.db"
    _stamp(db_path, "001")
    assert _current_revision(db_path) == "001"

    backup_path = db_path.with_suffix(".pre-2.0.bak")
    assert not backup_path.exists()

    store = GraphStore(db_path)
    try:
        # GraphStore brought the DB through 001 -> 005 (head). The hook
        # snapshotted the rev-001 state to ``<db>.pre-2.0.bak`` BEFORE
        # the upgrade chain ran.
        head = ScriptDirectory.from_config(
            _alembic_config_for(db_path)
        ).get_current_head()
        # Phase 3 Task 7 added revision 006 (commits table). Future
        # additive revisions move the head forward; the BREAKING
        # boundary remains at 005, so the backup behaviour pinned by
        # this test does not change. We assert the chain reached the
        # current head (whatever revision it points at) rather than
        # hard-coding a numeric value that would have to be bumped on
        # every additive migration.
        assert head is not None and head >= "005"
        assert _current_revision(db_path) == head
    finally:
        store.close()

    assert backup_path.exists(), (
        "backup must be created when crossing the BREAKING 005 boundary"
    )
    # Backup preserves the pre-upgrade rev-001 state.
    with closing(sqlite3.connect(str(backup_path))) as conn:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row[0] == "001", (
        f"backup should preserve the rev-001 state captured before upgrade; got {row[0]!r}"
    )


# ---------------------------------------------------------------------------
# (4) Backup is idempotent (existing file not overwritten)
# ---------------------------------------------------------------------------


def test_backup_idempotent_if_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-existing backup file is preserved, not overwritten.

    Simulates a re-run after a partial / failed migration: a backup is
    already on disk from the first attempt.  Opening the DB again must
    NOT replace the old backup with a copy of the (potentially partially
    migrated) current DB.
    """
    db_path = tmp_path / "graph.db"
    _stamp(db_path, "002")

    backup_path = db_path.with_suffix(".pre-2.0.bak")
    sentinel = b"OLD-BACKUP-MARKER"
    backup_path.write_bytes(sentinel)
    assert backup_path.read_bytes() == sentinel

    _force_target_head(monkeypatch, "005")

    store = GraphStore(db_path)
    try:
        # Old backup preserved verbatim — idempotent.
        assert backup_path.read_bytes() == sentinel, (
            "existing backup must not be overwritten on subsequent runs"
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# (5) Downgrade env var restores backup
# ---------------------------------------------------------------------------


def test_downgrade_env_var_restores_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``CRG_DOWNGRADE_TO_1_X=1`` + backup exists → restore + archive current.

    Setup:
      * DB at simulated post-005 state (real head, but contents
        immaterial — we're going to overwrite the file anyway).
      * Backup file marker = "BACKUP".
      * Env var set.

    Expected outcome:
      * ``<db>.post-2.0.archived`` contains the v2 (current) DB.
      * ``<db>`` itself contains the backup marker.
      * The alembic upgrade is skipped (backup is at v1.x).
    """
    db_path = tmp_path / "graph.db"
    _stamp(db_path, "002")  # creates a real v1.x-shaped DB

    # Take a real backup of the current rev-002 state (so the "restore"
    # produces a usable DB), then bump current to head to simulate v2 state.
    import shutil

    backup_path = db_path.with_suffix(".pre-2.0.bak")
    shutil.copy2(db_path, backup_path)

    # Bump current DB to head — pretend we're at v2. We compare against
    # the real head reported by alembic (currently ``004`` after Phase 3
    # Task 2; will roll forward as future pre-005 migrations land) so this
    # assertion does not need to be touched on every additive bump.
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")
    v2_rev = _current_revision(db_path)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert v2_rev == head

    # Sanity: backup is still at 002.
    with closing(sqlite3.connect(str(backup_path))) as conn:
        bkp_rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert bkp_rev == "002"

    archived_path = db_path.with_suffix(".post-2.0.archived")
    assert not archived_path.exists()

    monkeypatch.setenv("CRG_DOWNGRADE_TO_1_X", "1")

    store = GraphStore(db_path)
    try:
        # Restored DB is at the backup revision (002), not head.
        assert _current_revision(db_path) == "002", (
            "DB should now contain the v1.x backup state"
        )
        # The v2 state was preserved on disk for recovery.
        assert archived_path.exists()
        with closing(sqlite3.connect(str(archived_path))) as conn:
            arch_rev = conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        assert arch_rev == v2_rev, (
            f"archived file should contain the v2 state ({v2_rev}); got {arch_rev!r}"
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# (6) Downgrade env var without backup raises
# ---------------------------------------------------------------------------


def test_downgrade_env_var_without_backup_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Env var set but no backup exists → :class:`RuntimeError`.

    Cannot silently fall through to a forward-upgrade — the user
    explicitly asked for a downgrade and we have nothing to restore.
    """
    db_path = tmp_path / "graph.db"
    _stamp(db_path, "head")

    backup_path = db_path.with_suffix(".pre-2.0.bak")
    assert not backup_path.exists()

    monkeypatch.setenv("CRG_DOWNGRADE_TO_1_X", "1")

    with pytest.raises(RuntimeError) as excinfo:
        GraphStore(db_path)

    msg = str(excinfo.value)
    assert "backup" in msg.lower(), (
        f"error message should mention the missing backup: {msg!r}"
    )
    assert str(backup_path) in msg, (
        f"error message should name the expected backup path: {msg!r}"
    )


# ---------------------------------------------------------------------------
# (7) Downgrade env var unset → no restore (default flow)
# ---------------------------------------------------------------------------


def test_downgrade_env_var_unset_does_not_restore(tmp_path: Path) -> None:
    """Backup file present but env var unset → default forward-flow runs.

    The mere presence of a backup file from a prior aborted run must
    not trigger a restore on its own; the user has to explicitly opt
    in via ``CRG_DOWNGRADE_TO_1_X=1``.
    """
    db_path = tmp_path / "graph.db"
    _stamp(db_path, "002")

    backup_path = db_path.with_suffix(".pre-2.0.bak")
    sentinel = b"BACKUP-SHOULD-BE-IGNORED"
    backup_path.write_bytes(sentinel)

    archived_path = db_path.with_suffix(".post-2.0.archived")
    assert not archived_path.exists()

    # Env var deliberately unset (covered by sandboxed test env).
    store = GraphStore(db_path)
    try:
        # DB advanced normally to head.
        assert _current_revision(db_path) is not None
        # Archive file never created — no restore happened.
        assert not archived_path.exists(), (
            "archive must not be created when env var is unset"
        )
        # Backup file untouched.
        assert backup_path.read_bytes() == sentinel
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Module reference smoke (keeps the import marked used by linters and
# pins the symbol the implementation must export — moves with the code).
# ---------------------------------------------------------------------------


def test_graph_module_exposes_graphstore() -> None:
    assert hasattr(graph_mod, "GraphStore")


# ---------------------------------------------------------------------------
# Edge-case coverage: defensive branches in the helpers
# ---------------------------------------------------------------------------


def test_downgrade_replaces_existing_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An archive file from a prior aborted downgrade gets replaced.

    Covers the ``archived_path.unlink()`` branch in
    ``_restore_pre_2_0_backup``: if the user is running a second
    downgrade attempt (e.g. after an interrupted shutdown), the
    stale archive on disk must be removed before
    ``os.replace(db, archived)`` runs (Windows ``os.replace`` errors
    if the destination already exists across some filesystems).
    """
    db_path = tmp_path / "graph.db"
    _stamp(db_path, "002")

    backup_path = db_path.with_suffix(".pre-2.0.bak")
    import shutil as _shutil

    _shutil.copy2(db_path, backup_path)

    # Pre-existing archive from a prior aborted attempt.
    archived_path = db_path.with_suffix(".post-2.0.archived")
    archived_path.write_bytes(b"STALE-ARCHIVE")
    assert archived_path.exists()

    monkeypatch.setenv("CRG_DOWNGRADE_TO_1_X", "1")

    store = GraphStore(db_path)
    try:
        # Restore succeeded despite the pre-existing archive: the stale
        # archive was unlinked, the v2 (current) state moved into its
        # place, and the backup restored over the live db.
        assert _current_revision(db_path) == "002"
        assert archived_path.exists()
        # The new archive is NOT the stale marker — the old one was
        # unlinked and replaced with the v2 state.
        assert archived_path.read_bytes() != b"STALE-ARCHIVE"
    finally:
        store.close()


def test_take_backup_silent_no_op_when_db_path_missing(tmp_path: Path) -> None:
    """``_take_pre_2_0_backup`` is a no-op when the main DB file is missing.

    Scenario: a memory-only test path or a virtual filesystem where the
    on-disk file simply does not exist.  We synthesize this by opening
    a ``GraphStore`` against a fresh tmp file and then deleting the file
    (and any pre-2.0 backup the upgrade hook just produced) before
    invoking the helper directly.

    Now that revision ``005`` is the real shipped head, opening a fresh
    DB triggers the backup hook automatically (current=None < 005).
    We therefore have to clear the backup file too before re-invoking
    the helper, so the assertion "the helper produced no NEW backup"
    has a clean baseline.

    The helper must NOT raise — defensive guard for code paths that
    re-enter ``_run_alembic_upgrade`` from atypical bootstraps.
    """
    db_path = tmp_path / "graph.db"
    store = GraphStore(db_path)
    try:
        backup_path = db_path.with_suffix(".pre-2.0.bak")
        # Delete the live file (closing the sqlite connection first so
        # Windows lets us drop the inode).
        store._conn.close()
        db_path.unlink()
        assert not db_path.exists()

        # The upgrade hook produced a backup at first open; remove it
        # so we can assert the direct call below is a clean no-op.
        if backup_path.exists():
            backup_path.unlink()
        assert not backup_path.exists()

        # Direct call — no exception, no backup file.
        store._take_pre_2_0_backup()
        assert not backup_path.exists()
    finally:
        # Reopen the connection so the closing context manager doesn't
        # double-close on a now-invalid handle.
        store._conn = sqlite3.connect(":memory:")
        store.close()


def test_crosses_breaking_boundary_helper() -> None:
    """Exercise the pure boundary-detection helper directly.

    The helper drives a load-bearing branch in production code so we
    pin its exact contract here: only the (current_rev < 005, target_rev >= 005)
    quadrant returns True.  ``None`` for current means fresh DB →
    crosses (when target is at/past 005).  ``None`` for target is
    treated as "alembic doesn't know" and never crosses.
    """
    from better_code_review_graph.graph import _crosses_breaking_boundary

    # Pre-005 DB about to upgrade to 005+: triggers backup.
    assert _crosses_breaking_boundary(None, "005") is True
    assert _crosses_breaking_boundary("001", "005") is True
    assert _crosses_breaking_boundary("002", "005") is True
    assert _crosses_breaking_boundary("003", "005") is True
    assert _crosses_breaking_boundary("004", "005") is True
    assert _crosses_breaking_boundary("002", "006") is True
    # Already at/past 005: no backup needed.
    assert _crosses_breaking_boundary("005", "005") is False
    assert _crosses_breaking_boundary("005", "006") is False
    assert _crosses_breaking_boundary("006", "006") is False
    # Target below 005: no backup needed (current head today).
    assert _crosses_breaking_boundary(None, "003") is False
    assert _crosses_breaking_boundary("001", "002") is False
    assert _crosses_breaking_boundary("002", "003") is False
    # Target unknown: defensive False.
    assert _crosses_breaking_boundary(None, None) is False
    assert _crosses_breaking_boundary("002", None) is False
