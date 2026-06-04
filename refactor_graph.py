import sys

def refactor():
    with open('src/better_code_review_graph/graph.py', 'r') as f:
        lines = f.readlines()

    start_line = -1
    end_line = -1
    for i, line in enumerate(lines):
        if 'def _run_alembic_upgrade(self) -> None:' in line:
            start_line = i
        if start_line != -1 and 'def _read_alembic_version(self) -> str | None:' in line:
            end_line = i
            break

    if start_line == -1 or end_line == -1:
        print(f"Could not find boundaries: start={start_line}, end={end_line}")
        return

    new_methods = """    def _run_alembic_upgrade(self) -> None:
        \"\"\"Bring ``self.db_path`` to alembic head before legacy bootstrap.

        Four cases are handled:

        * Empty DB (no tables) — alembic creates everything from scratch.
        * Legacy DB created by Phase 1's ``executescript(_SCHEMA_SQL)`` +
          ``_ensure_summary_columns`` (so it already has ``nodes``/``edges``/
          ``metadata`` but no ``alembic_version`` table) — we stamp it to
          revision ``002`` before upgrading so the baseline ``CREATE TABLE``
          statements are skipped.
        * DB already managed by alembic — ``upgrade("head")`` is a no-op.
        * DB recorded at a revision the package does not ship (user
          fast-forwarded by hand, or the package was downgraded).  We
          re-raise as a :class:`RuntimeError` with a human-readable
          recovery hint instead of leaking an opaque
          ``alembic.util.exc.CommandError``.

        Imported lazily so ``alembic`` (and its SQLAlchemy dependency) are
        only loaded when a ``GraphStore`` is actually instantiated.
        \"\"\"
        cfg, command, ScriptDirectory, CommandError = self._get_alembic_config()

        if self._handle_downgrade_request():
            return

        self._maybe_stamp_legacy_db(cfg, command)
        self._maybe_take_backup_before_upgrade(cfg, ScriptDirectory)

        try:
            command.upgrade(cfg, "head")
        except CommandError as exc:
            self._handle_alembic_command_error(cfg, ScriptDirectory, exc)

    def _get_alembic_config(self):
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.util.exc import CommandError

        migrations_dir = _resolve_migrations_dir()
        cfg = Config()
        cfg.set_main_option("script_location", str(migrations_dir))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")
        return cfg, command, ScriptDirectory, CommandError

    def _handle_downgrade_request(self) -> bool:
        if os.environ.get(_DOWNGRADE_ENV_VAR) == "1":
            self._restore_pre_2_0_backup()
            return True
        return False

    def _maybe_stamp_legacy_db(self, cfg, command) -> None:
        existing = {
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "nodes" in existing:
            needs_stamp = "alembic_version" not in existing
            if not needs_stamp:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM alembic_version"
                ).fetchone()
                needs_stamp = row[0] == 0
            if needs_stamp:
                command.stamp(cfg, "002")

    def _maybe_take_backup_before_upgrade(self, cfg, ScriptDirectory) -> None:
        current_rev = self._read_alembic_version()
        target_rev = ScriptDirectory.from_config(cfg).get_current_head()
        if _crosses_breaking_boundary(current_rev, target_rev):
            self._take_pre_2_0_backup()

    def _handle_alembic_command_error(self, cfg, ScriptDirectory, exc) -> None:
        import sqlite3
        recorded: str | None
        try:
            row = self._conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            recorded = row[0] if row else None
        except sqlite3.Error:
            recorded = None
        head = ScriptDirectory.from_config(cfg).get_current_head()
        raise RuntimeError(
            f"Graph DB at {self.db_path} reports alembic revision "
            f"{recorded!r} which is not shipped with this version of "
            f"better-code-review-graph (head={head!r}). Either downgrade "
            "the package or recreate the DB."
        ) from exc

    # ------------------------------------------------------------------
    # Phase 3 Task 1 — backup / restore helpers
    # ------------------------------------------------------------------

"""
    new_lines = new_methods.splitlines(keepends=True)

    # Replace old method with new methods
    lines[start_line:end_line] = new_lines

    with open('src/better_code_review_graph/graph.py', 'w') as f:
        f.writelines(lines)

if __name__ == "__main__":
    refactor()
