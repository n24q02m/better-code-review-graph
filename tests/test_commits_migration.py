"""Tests for the 006_commits_table alembic migration + backfill helper.

Revision ``006`` is purely additive — it creates the ``commits`` table
and the ``idx_commits_repo_time`` index from spec section 5.4. The
backfill helper ``federation.backfill_commits_for_repo`` walks
``git log --first-parent`` and bulk-inserts rows so the table is
populated on the next graph build.

Test coverage:

* Schema invariants (1-3): table + columns + index land on upgrade.
* Round-trip (4): upgrade -> downgrade -> upgrade leaves no orphans.
* Insert acceptance (5): the table accepts the canonical INSERT shape.
* FK enforcement (6): ``PRAGMA foreign_keys=ON`` rejects unknown repo_id.
* Backfill happy path (7): real ``git init`` + N commits -> N rows.
* First-parent semantics (8): merge collapses to mainline.
* Idempotency (9): running backfill twice yields the same row count.
* No-git short-circuit (10): non-git dir returns 0 without raising.
* Root commit (11): no-parent commit lands with ``parent_sha IS NULL``.
* End-to-end via ``build_or_update_graph`` (12): federated multi-root
  build populates ``commits`` for every registered root.
"""

from __future__ import annotations

import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from better_code_review_graph.federation import (
    RepoRegistry,
    backfill_commits_for_repo,
)
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.tools import build_or_update_graph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alembic_config_for(db_path: Path) -> Config:
    """Build an Alembic Config bound to ``db_path`` using the project ini."""
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _table_columns(db_path: Path, table: str) -> dict[str, tuple]:
    """Return ``PRAGMA table_info`` rows keyed by column name."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {
        name: (typ, notnull, dflt, pk) for (_cid, name, typ, notnull, dflt, pk) in rows
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


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``git`` in ``repo`` with stable identity flags + quiet output.

    The ``-c`` overrides isolate the test from the operator's global git
    config (no GPG signing, no ambient committer identity, fixed
    default branch name) so the suite is reproducible on any host.
    """
    return subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "-c",
            "init.defaultBranch=main",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


def _git_init_with_commits(repo_root: Path, count: int) -> list[str]:
    """``git init`` ``repo_root`` and create ``count`` linear commits.

    Returns the list of commit SHAs in chronological (oldest-first)
    order so callers can assert on the exact lineage.

    Each commit's file content embeds the absolute repo path so two
    repos initialised in the same second under different paths produce
    distinct SHAs. Without this, git's deterministic SHA derivation
    (author + timestamp + tree) collapses commits across sibling
    fixtures into a single SHA, and the ``commits`` table's
    ``INSERT OR IGNORE`` then skips the second repo's rows.
    """
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init")
    shas: list[str] = []
    for i in range(count):
        (repo_root / f"file_{i}.txt").write_text(f"contents {i} for {repo_root}\n")
        _git(repo_root, "add", f"file_{i}.txt")
        _git(repo_root, "commit", "-m", f"commit {i} in {repo_root.name}")
        sha = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
        shas.append(sha)
    return shas


@pytest.fixture
def repo_with_db(tmp_path: Path) -> tuple[Path, Path, list[str]]:
    """Build a real git repo containing a CRG-style ``graph.db`` location.

    Layout mirrors production: ``<repo>/.code-review-graph/graph.db``.
    Returns ``(db_path, repo_root, commit_shas)``.
    """
    repo_root = tmp_path / "myrepo"
    shas = _git_init_with_commits(repo_root, count=3)
    crg_dir = repo_root / ".code-review-graph"
    crg_dir.mkdir()
    db_path = crg_dir / "graph.db"
    return db_path, repo_root, shas


# ---------------------------------------------------------------------------
# (1) commits table created — primary key + NOT NULL + nullable shape
# ---------------------------------------------------------------------------


def test_006_creates_commits_table(repo_with_db: tuple[Path, Path, list[str]]) -> None:
    """``commits`` exists post-upgrade with the spec section 5.4 column shape."""
    db_path, _repo, _shas = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    cols = _table_columns(db_path, "commits")
    assert cols, "commits table missing after upgrade"

    # ``sha`` — TEXT, PRIMARY KEY, NOT NULL.
    sha_typ, sha_notnull, _sha_dflt, sha_pk = cols["sha"]
    assert sha_typ.upper() == "TEXT"
    assert sha_pk == 1, f"sha must be primary key, got pk={sha_pk}"
    # SQLite marks PRIMARY KEY columns as NOT NULL implicitly only for
    # INTEGER PRIMARY KEY; for TEXT we declared NOT NULL explicitly.
    assert sha_notnull == 1

    # ``repo_id`` — TEXT, NOT NULL.
    repo_typ, repo_notnull, _repo_dflt, repo_pk = cols["repo_id"]
    assert repo_typ.upper() == "TEXT"
    assert repo_notnull == 1, f"repo_id must be NOT NULL, got notnull={repo_notnull}"
    assert repo_pk == 0

    # ``parent_sha`` — TEXT, NULLable.
    parent_typ, parent_notnull, _parent_dflt, parent_pk = cols["parent_sha"]
    assert parent_typ.upper() == "TEXT"
    assert parent_notnull == 0, "parent_sha must be NULLable"
    assert parent_pk == 0

    # ``timestamp`` — INTEGER, NOT NULL.
    ts_typ, ts_notnull, _ts_dflt, ts_pk = cols["timestamp"]
    assert ts_typ.upper() == "INTEGER"
    assert ts_notnull == 1, "timestamp must be NOT NULL"
    assert ts_pk == 0

    # ``message`` — TEXT, NULLable.
    msg_typ, msg_notnull, _msg_dflt, msg_pk = cols["message"]
    assert msg_typ.upper() == "TEXT"
    assert msg_notnull == 0, "message must be NULLable"
    assert msg_pk == 0


# ---------------------------------------------------------------------------
# (2) idx_commits_repo_time index created on (repo_id, timestamp)
# ---------------------------------------------------------------------------


def test_006_creates_repo_time_index(
    repo_with_db: tuple[Path, Path, list[str]],
) -> None:
    """``idx_commits_repo_time`` exists post-upgrade with the spec column order."""
    db_path, _repo, _shas = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    indexes = _index_names(db_path)
    assert "idx_commits_repo_time" in indexes, (
        f"idx_commits_repo_time missing; got {sorted(indexes)}"
    )

    with closing(sqlite3.connect(str(db_path))) as conn:
        cols = conn.execute("PRAGMA index_info('idx_commits_repo_time')").fetchall()
    # Each row: (seqno, cid, name)
    indexed_cols = [r[2] for r in cols]
    assert indexed_cols == ["repo_id", "timestamp"], (
        f"index column order should be (repo_id, timestamp); got {indexed_cols}"
    )


# ---------------------------------------------------------------------------
# (3) Round-trip upgrade -> downgrade -> upgrade leaves no orphans
# ---------------------------------------------------------------------------


def test_006_round_trip_upgrade_downgrade_upgrade(
    repo_with_db: tuple[Path, Path, list[str]],
) -> None:
    """upgrade(head) -> downgrade("005") -> upgrade(head) is clean.

    Pins both directions and ensures the index is dropped before the
    table on the way down so SQLite does not leave dangling metadata.
    """
    db_path, _repo, _shas = repo_with_db
    cfg = _alembic_config_for(db_path)

    # Up — table + index land.
    command.upgrade(cfg, "head")
    assert "commits" in _table_columns(db_path, "commits") or _table_columns(
        db_path, "commits"
    )
    assert "idx_commits_repo_time" in _index_names(db_path)

    # Down to 005 — table + index gone, prior columns untouched.
    command.downgrade(cfg, "005")
    assert _table_columns(db_path, "commits") == {}, (
        "commits table leaked through downgrade"
    )
    assert "idx_commits_repo_time" not in _index_names(db_path)
    # Phase 3 Task 6 columns survive.
    assert "valid_from_sha" in _table_columns(db_path, "nodes")
    assert "valid_to_sha" in _table_columns(db_path, "edges")

    # Up again — table + index restored.
    command.upgrade(cfg, "head")
    assert _table_columns(db_path, "commits"), "commits table missing after re-upgrade"
    assert "idx_commits_repo_time" in _index_names(db_path)


# ---------------------------------------------------------------------------
# (4) Table accepts the canonical INSERT shape
# ---------------------------------------------------------------------------


def test_commits_table_accepts_inserts(
    repo_with_db: tuple[Path, Path, list[str]],
) -> None:
    """A canonical 5-column INSERT round-trips as inserted."""
    db_path, _repo, _shas = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    sample_sha = "a" * 40
    parent_sha = "b" * 40

    with closing(sqlite3.connect(str(db_path))) as conn:
        # Seed a repos row first so the FK target exists. We don't need
        # FK enforcement on for this test (default OFF) but the row
        # also pins the column shape against the registry table.
        conn.execute(
            "INSERT INTO repos (repo_id, path, remote_url, last_indexed_sha, "
            "first_indexed_at, last_indexed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("repo-id", "/some/path", None, None, 0, 0),
        )
        conn.execute(
            "INSERT INTO commits (sha, repo_id, parent_sha, timestamp, message) "
            "VALUES (?, ?, ?, ?, ?)",
            (sample_sha, "repo-id", parent_sha, 1700_000_000, "subject line"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT sha, repo_id, parent_sha, timestamp, message "
            "FROM commits WHERE sha = ?",
            (sample_sha,),
        ).fetchone()

    assert row == (sample_sha, "repo-id", parent_sha, 1700_000_000, "subject line")


# ---------------------------------------------------------------------------
# (5) Foreign-key enforcement when PRAGMA foreign_keys = ON
# ---------------------------------------------------------------------------


def test_commits_repo_id_foreign_key_constraint(
    repo_with_db: tuple[Path, Path, list[str]],
) -> None:
    """With FKs enabled, INSERT against unknown ``repo_id`` raises IntegrityError.

    SQLite enforces foreign keys only when ``PRAGMA foreign_keys = ON``
    is issued per-connection (off by default). The migration declares
    the constraint so this contract holds wherever the operator opts in.
    """
    db_path, _repo, _shas = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO commits (sha, repo_id, parent_sha, timestamp, message) "
                "VALUES (?, ?, ?, ?, ?)",
                ("c" * 40, "no-such-repo", None, 0, "orphan"),
            )


# ---------------------------------------------------------------------------
# (6) Backfill happy path — real git init + 3 commits -> 3 rows
# ---------------------------------------------------------------------------


def test_backfill_commits_for_repo_populates_table(
    repo_with_db: tuple[Path, Path, list[str]],
) -> None:
    """3 linear commits -> 3 rows in ``commits``, all tagged with our repo_id."""
    db_path, repo_root, shas = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    store = GraphStore(str(db_path))
    try:
        registry = RepoRegistry(store)
        repo_id = registry.add(repo_root)
        inserted = backfill_commits_for_repo(store, repo_id, repo_root)
        assert inserted == 3, f"expected 3 inserts, got {inserted}"

        rows = store._conn.execute(
            "SELECT sha, repo_id, parent_sha, timestamp, message "
            "FROM commits WHERE repo_id = ? ORDER BY timestamp",
            (repo_id,),
        ).fetchall()
    finally:
        store.close()

    assert len(rows) == 3
    seen_shas = {r["sha"] for r in rows}
    assert seen_shas == set(shas), (
        f"backfilled SHAs {seen_shas} should match git history {set(shas)}"
    )
    # All rows must carry our repo_id and a non-empty subject line.
    for r in rows:
        assert r["repo_id"] == repo_id
        assert r["message"]
        assert isinstance(r["timestamp"], int)


# ---------------------------------------------------------------------------
# (7) First-parent semantics: merges collapse to mainline only
# ---------------------------------------------------------------------------


def test_backfill_commits_first_parent_only(tmp_path: Path) -> None:
    """A merged feature branch contributes only the merge commit + mainline.

    Build a topology:

        m0 -- m1 ----------- M (merge)
                \\          /
                 f0 ------/

    ``git log --first-parent`` from M visits {M, m1, m0} only — f0 is on
    the second-parent side and is excluded. We assert the backfill
    matches that 3-commit set, not the 4-commit full history.
    """
    repo_root = tmp_path / "merge_repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    # m0
    (repo_root / "m.txt").write_text("m0\n")
    _git(repo_root, "add", "m.txt")
    _git(repo_root, "commit", "-m", "m0")
    m0 = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    # m1
    (repo_root / "m.txt").write_text("m1\n")
    _git(repo_root, "add", "m.txt")
    _git(repo_root, "commit", "-m", "m1")
    m1 = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    # feature branch off m0 with one commit f0
    _git(repo_root, "checkout", "-b", "feature", m0)
    (repo_root / "f.txt").write_text("f0\n")
    _git(repo_root, "add", "f.txt")
    _git(repo_root, "commit", "-m", "f0")
    f0 = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    # back to main, merge with --no-ff to force a real merge commit
    _git(repo_root, "checkout", "main")
    _git(repo_root, "merge", "--no-ff", "feature", "-m", "merge feature")
    merge_sha = _git(repo_root, "rev-parse", "HEAD").stdout.strip()

    crg_dir = repo_root / ".code-review-graph"
    crg_dir.mkdir()
    db_path = crg_dir / "graph.db"
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    store = GraphStore(str(db_path))
    try:
        registry = RepoRegistry(store)
        repo_id = registry.add(repo_root)
        inserted = backfill_commits_for_repo(store, repo_id, repo_root)
        assert inserted == 3, (
            f"expected 3 first-parent commits (m0, m1, merge), got {inserted}"
        )

        shas = {
            r["sha"]
            for r in store._conn.execute(
                "SELECT sha FROM commits WHERE repo_id = ?", (repo_id,)
            ).fetchall()
        }
    finally:
        store.close()

    assert shas == {m0, m1, merge_sha}, (
        f"expected mainline only; got {shas} (f0 leaked: {f0 in shas})"
    )
    assert f0 not in shas, "feature-branch commit must not appear via first-parent"


# ---------------------------------------------------------------------------
# (8) Idempotency — INSERT OR IGNORE means re-run = no duplicates
# ---------------------------------------------------------------------------


def test_backfill_commits_idempotent(
    repo_with_db: tuple[Path, Path, list[str]],
) -> None:
    """Running the backfill twice yields the same row count, second pass = 0."""
    db_path, repo_root, shas = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    store = GraphStore(str(db_path))
    try:
        registry = RepoRegistry(store)
        repo_id = registry.add(repo_root)

        first = backfill_commits_for_repo(store, repo_id, repo_root)
        second = backfill_commits_for_repo(store, repo_id, repo_root)

        assert first == len(shas)
        assert second == 0, "second call must be a noop via INSERT OR IGNORE"

        total = store._conn.execute(
            "SELECT COUNT(*) AS c FROM commits WHERE repo_id = ?", (repo_id,)
        ).fetchone()
    finally:
        store.close()
    assert total["c"] == len(shas)


# ---------------------------------------------------------------------------
# (9) Non-git directory short-circuits to 0 without raising
# ---------------------------------------------------------------------------


def test_backfill_commits_no_git_returns_zero(tmp_path: Path) -> None:
    """Directory with no ``.git`` returns 0 (no exception, no rows)."""
    no_git = tmp_path / "plain_dir"
    no_git.mkdir()
    db_path = no_git / "graph.db"
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    store = GraphStore(str(db_path))
    try:
        # We can't add() into the registry because RepoRegistry doesn't
        # inspect ``.git`` — it's the backfill helper that short-circuits.
        registry = RepoRegistry(store)
        repo_id = registry.add(no_git)
        assert backfill_commits_for_repo(store, repo_id, no_git) == 0
        # No rows landed.
        count = store._conn.execute("SELECT COUNT(*) AS c FROM commits").fetchone()
    finally:
        store.close()
    assert count["c"] == 0


# ---------------------------------------------------------------------------
# (10) Orphan root commit -> parent_sha IS NULL
# ---------------------------------------------------------------------------


def test_backfill_commits_handles_orphan_root_commit(tmp_path: Path) -> None:
    """The root commit (no parents) lands with ``parent_sha`` NULL.

    A single-commit repo has exactly one row whose ``parent_sha`` is
    ``NULL`` because git's ``%P`` placeholder emits the empty string
    for orphan commits.
    """
    repo_root = tmp_path / "orphan_repo"
    shas = _git_init_with_commits(repo_root, count=1)
    assert len(shas) == 1
    crg_dir = repo_root / ".code-review-graph"
    crg_dir.mkdir()
    db_path = crg_dir / "graph.db"
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    store = GraphStore(str(db_path))
    try:
        registry = RepoRegistry(store)
        repo_id = registry.add(repo_root)
        inserted = backfill_commits_for_repo(store, repo_id, repo_root)
        assert inserted == 1
        row = store._conn.execute(
            "SELECT sha, parent_sha FROM commits WHERE repo_id = ?",
            (repo_id,),
        ).fetchone()
    finally:
        store.close()

    assert row["sha"] == shas[0]
    assert row["parent_sha"] is None, (
        f"root commit must have parent_sha IS NULL, got {row['parent_sha']!r}"
    )


# ---------------------------------------------------------------------------
# (11) Subprocess failure path — git binary missing -> 0 (best-effort)
# ---------------------------------------------------------------------------


def test_backfill_commits_handles_subprocess_failure(
    repo_with_db: tuple[Path, Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subprocess OSError is caught and the helper returns 0 instead of raising.

    Pins the best-effort contract documented in the helper's docstring:
    a missing ``git`` binary or a transient ``git`` failure on a single
    root must not abort a federated build.
    """
    db_path, repo_root, _shas = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    from better_code_review_graph import federation as fed

    def _boom(*_a, **_kw):
        raise OSError("git not on PATH")

    monkeypatch.setattr(fed.subprocess, "run", _boom)

    store = GraphStore(str(db_path))
    try:
        registry = RepoRegistry(store)
        repo_id = registry.add(repo_root)
        assert backfill_commits_for_repo(store, repo_id, repo_root) == 0
    finally:
        store.close()


def test_backfill_commits_handles_nonzero_returncode(
    repo_with_db: tuple[Path, Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-zero ``git`` exit (corrupt repo) -> helper returns 0, no rows."""
    db_path, repo_root, _shas = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    from better_code_review_graph import federation as fed

    class _FakeProc:
        returncode = 128
        stdout = ""

    monkeypatch.setattr(fed.subprocess, "run", lambda *_a, **_kw: _FakeProc())

    store = GraphStore(str(db_path))
    try:
        registry = RepoRegistry(store)
        repo_id = registry.add(repo_root)
        assert backfill_commits_for_repo(store, repo_id, repo_root) == 0
        count = store._conn.execute("SELECT COUNT(*) AS c FROM commits").fetchone()
    finally:
        store.close()
    assert count["c"] == 0


def test_backfill_commits_skips_malformed_lines(
    repo_with_db: tuple[Path, Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lines missing NUL columns or with non-int timestamps are skipped silently.

    Defensive coverage of the two ``continue`` branches in the parser
    loop. We feed the helper hand-crafted output containing one valid
    row, one truncated row (missing columns), and one row with a
    non-decimal timestamp; only the valid row should land.
    """
    db_path, repo_root, _shas = repo_with_db
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    from better_code_review_graph import federation as fed

    valid_sha = "d" * 40
    parent_sha = "e" * 40
    fake_stdout = "\n".join(
        [
            # Valid: 4 NUL-separated columns, integer timestamp.
            f"{valid_sha}\x00{parent_sha}\x00100\x00valid subject",
            # Malformed: only 2 columns.
            "deadbeef\x00onlytwo",
            # Malformed: non-int timestamp.
            "f" * 40 + "\x00" + parent_sha + "\x00not_a_number\x00bad ts",
        ]
    )

    class _FakeProc:
        returncode = 0
        stdout = fake_stdout

    monkeypatch.setattr(fed.subprocess, "run", lambda *_a, **_kw: _FakeProc())

    store = GraphStore(str(db_path))
    try:
        registry = RepoRegistry(store)
        repo_id = registry.add(repo_root)
        inserted = backfill_commits_for_repo(store, repo_id, repo_root)
        assert inserted == 1, f"expected only the well-formed row, got {inserted}"
        rows = store._conn.execute(
            "SELECT sha, message FROM commits WHERE repo_id = ?", (repo_id,)
        ).fetchall()
    finally:
        store.close()

    assert len(rows) == 1
    assert rows[0]["sha"] == valid_sha
    assert rows[0]["message"] == "valid subject"


# ---------------------------------------------------------------------------
# (12) End-to-end via build_or_update_graph(roots=[...])
# ---------------------------------------------------------------------------


def test_full_build_federated_backfills_commits_per_repo(tmp_path: Path) -> None:
    """Multi-root federated build populates ``commits`` for every registered root.

    Two real git repos under a workspace; ``build_or_update_graph`` is
    invoked with both as ``roots``. After the build, the ``commits``
    table must hold rows for both repos (each with the matching
    ``repo_id``).
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    (workspace / ".code-review-graph").mkdir()

    repo_a = workspace / "repo_a"
    repo_a_shas = _git_init_with_commits(repo_a, count=2)
    # Add a tiny Python file so the parser pass has something to chew
    # on (the federated build still walks files; we only care about
    # the commits side-effect, but we keep the parser happy to avoid
    # noise in the ``errors`` array).
    (repo_a / "main.py").write_text("def f():\n    return 1\n")
    _git(repo_a, "add", "main.py")
    _git(repo_a, "commit", "-m", "add main.py")
    repo_a_shas.append(_git(repo_a, "rev-parse", "HEAD").stdout.strip())

    repo_b = workspace / "repo_b"
    repo_b_shas = _git_init_with_commits(repo_b, count=2)
    (repo_b / "main.py").write_text("def g():\n    return 2\n")
    _git(repo_b, "add", "main.py")
    _git(repo_b, "commit", "-m", "add main.py")
    repo_b_shas.append(_git(repo_b, "rev-parse", "HEAD").stdout.strip())

    result = build_or_update_graph(
        full_rebuild=True,
        repo_root=str(workspace),
        roots=[str(repo_a), str(repo_b)],
    )
    assert result["status"] == "ok", result

    db_path = workspace / ".code-review-graph" / "graph.db"
    store = GraphStore(str(db_path))
    try:
        # Group the rows by repo_id and count.
        rows = store._conn.execute(
            "SELECT repo_id, COUNT(*) AS c FROM commits GROUP BY repo_id"
        ).fetchall()
        per_repo = {r["repo_id"]: r["c"] for r in rows}

        registry = RepoRegistry(store)
        a_id = registry.add(repo_a)
        b_id = registry.add(repo_b)
    finally:
        store.close()

    assert a_id in per_repo, f"repo_a commits missing; got {per_repo}"
    assert b_id in per_repo, f"repo_b commits missing; got {per_repo}"
    assert per_repo[a_id] == len(repo_a_shas), (
        f"repo_a expected {len(repo_a_shas)} commits, got {per_repo[a_id]}"
    )
    assert per_repo[b_id] == len(repo_b_shas), (
        f"repo_b expected {len(repo_b_shas)} commits, got {per_repo[b_id]}"
    )
