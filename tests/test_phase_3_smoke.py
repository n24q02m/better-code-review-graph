"""Phase 3 Task 12 release smoke tests -- end-to-end stack on a real repo.

Pins the v2.0 BREAKING release behaviour by exercising the full Phase 3
stack against a real on-disk git repo:

1. **Full lifecycle** -- TemporalIndex supersede across two commits +
   ``query(action="diff", ...)`` modified bucket + ``review(action="delta",
   show_line_shifts=True)`` line-shift detection.
2. **Security tags persisted** -- ``security(action="scan")`` writes both
   the disk cache and the ``nodes.security_tags`` JSON column.
3. **Breaking-change banner** -- README.md links to BREAKING_CHANGES.md
   so end-users discover the migration before opening the v2.0 db.
4. **Pre-2.0 backup lifecycle** -- v1.x-shaped DB is auto-backed-up on
   first open, and ``CRG_DOWNGRADE_TO_1_X=1`` restores it.

These tests do not require any network or upstream services and run
under the standard pytest invocation. The git fixtures use real
``git init`` + ``git commit`` so the migration's ``git rev-parse HEAD``
backfill path is exercised end-to-end.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.temporal import TemporalIndex
from better_code_review_graph.tools import (
    diff_graph,
    review_delta,
    security_scan,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command with stable identity flags so it never prompts."""
    inline_identity = [
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "-c",
        "init.defaultBranch=main",
        "-c",
        "commit.gpgsign=false",
    ]
    return subprocess.run(
        ["git", *inline_identity, *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _alembic_config_for(db_path: Path) -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


@pytest.fixture
def two_commit_repo(tmp_path: Path) -> Iterator[tuple[Path, str, str]]:
    """A real git repo with two commits that move ``do_thing`` from line 10 to 42.

    Layout:
      <repo>/
      ├── .git/
      └── src/m.py    (commit 1: do_thing at line 10
                       commit 2: do_thing at line 42 + body change)

    Yields ``(repo_root, sha1, sha2)``.
    """
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "src").mkdir()

    src_v1 = (
        "# header v1\n"
        "x = 1\n"
        "y = 2\n"
        "z = 3\n"
        "a = 4\n"
        "b = 5\n"
        "c = 6\n"
        "d = 7\n"
        "e = 8\n"
        "def do_thing():\n"  # line 10
        "    return 1\n"
    )
    (repo / "src" / "m.py").write_text(src_v1, encoding="utf-8")

    _git("init", cwd=repo)
    _git("add", ".", cwd=repo)
    _git("commit", "-m", "initial", cwd=repo)
    sha1 = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()

    # Bump do_thing to line 42 with a different body.
    pre_lines = ["# v2 header"] + [f"# fill {i}" for i in range(40)]
    src_v2 = "\n".join(pre_lines) + "\ndef do_thing():\n    return 2\n"
    (repo / "src" / "m.py").write_text(src_v2, encoding="utf-8")
    _git("add", ".", cwd=repo)
    _git("commit", "-m", "shift do_thing to line 42", cwd=repo)
    sha2 = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()

    assert len(sha1) == 40 and len(sha2) == 40 and sha1 != sha2
    yield repo, sha1, sha2


def _make_function_node(
    *,
    name: str = "do_thing",
    file_path: str = "src/m.py",
    line_start: int,
    source_text: str,
) -> NodeInfo:
    return NodeInfo(
        kind="Function",
        name=name,
        file_path=file_path,
        line_start=line_start,
        line_end=line_start + 1,
        language="python",
        parent_name=None,
        params="()",
        return_type=None,
        modifiers=None,
        is_test=False,
        extra={},
        source_text=source_text,
    )


# ---------------------------------------------------------------------------
# (1) Full lifecycle: temporal supersede + diff bucket + line shift
# ---------------------------------------------------------------------------


def test_phase_3_full_lifecycle_python(
    two_commit_repo: tuple[Path, str, str],
) -> None:
    """End-to-end: 2 commits moving a function -> diff modified + line shift."""
    repo, sha1, sha2 = two_commit_repo
    crg_dir = repo / ".code-review-graph"
    crg_dir.mkdir()
    db_path = crg_dir / "graph.db"

    store = GraphStore(str(db_path))
    try:
        idx_a = TemporalIndex(store, current_sha=sha1)
        idx_a.upsert_node(
            _make_function_node(
                line_start=10,
                source_text="def do_thing():\n    return 1\n",
            )
        )
        idx_b = TemporalIndex(store, current_sha=sha2)
        result = idx_b.upsert_node(
            _make_function_node(
                line_start=42,
                source_text="def do_thing():\n    return 2\n",
            )
        )
        assert result.action == "superseded"
        assert result.closed_out_count == 1

        rows = store._conn.execute(
            "SELECT line_start, valid_from_sha, valid_to_sha FROM nodes "
            "WHERE qualified_name = 'src/m.py::do_thing' "
            "ORDER BY id"
        ).fetchall()
        assert len(rows) == 2
        # Old row: line 10, closed at sha2.
        assert rows[0]["line_start"] == 10
        assert rows[0]["valid_to_sha"] == sha2
        # New row: line 42, currently valid.
        assert rows[1]["line_start"] == 42
        assert rows[1]["valid_from_sha"] == sha2
        assert rows[1]["valid_to_sha"] is None
    finally:
        store.close()

    # ``query(action="diff", ...)`` modified bucket includes the function.
    diff = diff_graph(repo_root=str(repo), from_sha=sha1, to_sha=sha2)
    modified_qns = [r["qualified_name"] for r in diff["modified"]]
    assert "src/m.py::do_thing" in modified_qns

    # ``review(action="delta", show_line_shifts=True)`` surfaces 10 -> 42.
    delta = review_delta(
        repo_root=str(repo),
        from_sha=sha1,
        to_sha=sha2,
        show_line_shifts=True,
    )
    assert "diff" in delta and "line_shifts" in delta
    shifts = delta["line_shifts"]
    assert len(shifts) == 1
    shift = shifts[0]
    assert shift["qualified_name"] == "src/m.py::do_thing"
    assert shift["before_line"] == 10
    assert shift["after_line"] == 42


# ---------------------------------------------------------------------------
# (2) Security scan tags persist to nodes.security_tags
# ---------------------------------------------------------------------------


def test_phase_3_security_scan_tags_persisted(tmp_path: Path) -> None:
    """SQL-injection f-string in a Function node -> tag persisted on the row."""
    repo = tmp_path / "vuln-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    crg_dir = repo / ".code-review-graph"
    crg_dir.mkdir()
    db_path = crg_dir / "graph.db"

    store = GraphStore(str(db_path))
    qualified = "src/db.py::vulnerable_query"
    try:
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="vulnerable_query",
                file_path="src/db.py",
                line_start=1,
                line_end=4,
                language="python",
                source_text=(
                    "def vulnerable_query(user_id):\n"
                    '    cursor.execute(f"SELECT * FROM users WHERE id={user_id}")\n'
                ),
            )
        )
        store._conn.commit()
    finally:
        store.close()

    payload = security_scan(repo_root=str(repo), engine="heuristic")
    assert payload["engine"] == "heuristic"
    assert payload["total"] >= 1
    assert qualified in payload["tags_by_node"]
    cwe_89_tags = [
        t for t in payload["tags_by_node"][qualified] if "cwe-89" in t["rule_id"]
    ]
    assert cwe_89_tags, "heuristic scanner should fire on SQL-injection f-string"

    # Verify the tag was persisted to nodes.security_tags.
    store = GraphStore(str(db_path))
    try:
        row = store._conn.execute(
            "SELECT security_tags FROM nodes WHERE qualified_name = ?",
            (qualified,),
        ).fetchone()
        assert row is not None
        assert row["security_tags"] is not None
        decoded = json.loads(row["security_tags"])
        assert isinstance(decoded, list)
        assert any("cwe-89" in entry for entry in decoded), (
            f"expected cwe-89 tag in {decoded!r}"
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# (3) Breaking-change banner is referenced in README.md
# ---------------------------------------------------------------------------


def test_phase_3_breaking_changes_banner_referenced_in_readme() -> None:
    """README.md contains a v2.0 migration section AND links BREAKING_CHANGES.md."""
    readme_path = _REPO_ROOT / "README.md"
    breaking_path = _REPO_ROOT / "BREAKING_CHANGES.md"

    assert readme_path.is_file(), "README.md must exist at repo root"
    assert breaking_path.is_file(), "BREAKING_CHANGES.md must exist at repo root"

    readme_text = readme_path.read_text(encoding="utf-8")
    # README must surface the v2.0 migration section.
    assert "v2.0 migration" in readme_text or "v2.0.0" in readme_text, (
        "README must mention the v2.0 migration"
    )
    # README must link to BREAKING_CHANGES.md so end-users discover it.
    assert "BREAKING_CHANGES.md" in readme_text, (
        "README must link to BREAKING_CHANGES.md"
    )

    # BREAKING_CHANGES.md must include the 4 canonical sections.
    breaking_text = breaking_path.read_text(encoding="utf-8")
    for required in (
        "Schema changes",
        "Behavior changes",
        "Rollback",
        "CRG_DOWNGRADE_TO_1_X",
    ):
        assert required in breaking_text, (
            f"BREAKING_CHANGES.md missing required section / token: {required!r}"
        )


# ---------------------------------------------------------------------------
# (4) Pre-2.0 backup lifecycle: auto-backup on open + downgrade restores
# ---------------------------------------------------------------------------


def test_phase_3_pre_2_0_backup_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Open a v1.x-shaped DB -> backup created -> downgrade restores it."""
    db_path = tmp_path / "graph.db"
    backup_path = db_path.with_suffix(".pre-2.0.bak")
    archived_path = db_path.with_suffix(".post-2.0.archived")

    # Build a real v1.x-style DB (pre-005 schema -- alembic at 002).
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "002")

    with closing(sqlite3.connect(str(db_path))) as conn:
        rev_before = conn.execute("SELECT version_num FROM alembic_version").fetchone()[
            0
        ]
    assert rev_before == "002", f"setup expected rev 002, got {rev_before!r}"
    assert not backup_path.exists()

    # First open: hook should snapshot the v1.x DB and run the upgrade.
    store = GraphStore(str(db_path))
    try:
        # Backup file produced by the pre-flight hook.
        assert backup_path.exists(), "backup file must be created on first open"
        with closing(sqlite3.connect(str(backup_path))) as conn:
            backup_rev = conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        assert backup_rev == "002", (
            f"backup must preserve the pre-upgrade rev (002); got {backup_rev!r}"
        )
        # DB itself moved past the BREAKING boundary.
        with closing(sqlite3.connect(str(db_path))) as conn:
            rev_after = conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        assert rev_after >= "005", (
            f"main DB should have advanced to >=005; got {rev_after!r}"
        )
    finally:
        store.close()

    # Now opt-in to the downgrade flow: env var set + backup present.
    monkeypatch.setenv("CRG_DOWNGRADE_TO_1_X", "1")
    store = GraphStore(str(db_path))
    try:
        # The v2 state moved aside, the v1.x backup is restored in place.
        with closing(sqlite3.connect(str(db_path))) as conn:
            restored_rev = conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        assert restored_rev == "002", (
            f"restored DB should be at v1.x rev 002; got {restored_rev!r}"
        )
        # Archive of the v2 state preserved for forward-roll recovery.
        assert archived_path.exists(), (
            "v2 db should be archived to <db>.post-2.0.archived"
        )
        with closing(sqlite3.connect(str(archived_path))) as conn:
            arch_rev = conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        assert arch_rev >= "005", (
            f"archive should retain the v2 rev (>=005); got {arch_rev!r}"
        )
    finally:
        store.close()
