"""Additional tests for incremental.py to cover collect_all_files, find_dependents, watch mode."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.incremental import (
    collect_all_files,
    find_dependents,
    full_build,
    get_all_tracked_files,
    get_changed_files,
    get_staged_and_unstaged,
    incremental_update,
    watch,
)
from better_code_review_graph.parser import EdgeInfo, NodeInfo

# ---------------------------------------------------------------------------
# collect_all_files
# ---------------------------------------------------------------------------


class TestCollectAllFiles:
    def test_collects_python_files(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "main.py").write_text("x = 1\n")
        (tmp_path / "utils.py").write_text("y = 2\n")
        (tmp_path / "readme.txt").write_text("text\n")

        with patch(
            "better_code_review_graph.incremental.get_all_tracked_files",
            return_value=["main.py", "utils.py", "readme.txt"],
        ):
            files = collect_all_files(tmp_path)

        assert "main.py" in files
        assert "utils.py" in files
        # .txt not a supported language
        assert "readme.txt" not in files

    def test_ignores_node_modules(self, tmp_path):
        (tmp_path / ".git").mkdir()
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}")

        with patch(
            "better_code_review_graph.incremental.get_all_tracked_files",
            return_value=["node_modules/pkg/index.js"],
        ):
            files = collect_all_files(tmp_path)

        assert len(files) == 0

    def test_ignores_binary_files(self, tmp_path):
        (tmp_path / ".git").mkdir()
        binary = tmp_path / "data.py"
        binary.write_bytes(b"#!/usr/bin/python\x00binary")

        with patch(
            "better_code_review_graph.incremental.get_all_tracked_files",
            return_value=["data.py"],
        ):
            files = collect_all_files(tmp_path)

        assert "data.py" not in files

    def test_fallback_to_rglob_without_git(self, tmp_path):
        (tmp_path / "app.py").write_text("print('hi')\n")

        with patch(
            "better_code_review_graph.incremental.get_all_tracked_files",
            return_value=[],
        ):
            files = collect_all_files(tmp_path)

        assert "app.py" in files

    def test_ignores_symlinks(self, tmp_path):
        (tmp_path / ".git").mkdir()
        real = tmp_path / "real.py"
        real.write_text("x = 1\n")
        link = tmp_path / "link.py"
        link.symlink_to(real)

        with patch(
            "better_code_review_graph.incremental.get_all_tracked_files",
            return_value=["real.py", "link.py"],
        ):
            files = collect_all_files(tmp_path)

        assert "real.py" in files
        assert "link.py" not in files

    def test_skips_missing_files(self, tmp_path):
        (tmp_path / ".git").mkdir()

        with patch(
            "better_code_review_graph.incremental.get_all_tracked_files",
            return_value=["nonexistent.py"],
        ):
            files = collect_all_files(tmp_path)

        assert len(files) == 0


# ---------------------------------------------------------------------------
# find_dependents
# ---------------------------------------------------------------------------


class TestFindDependents:
    def test_finds_importers(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        store.upsert_node(
            NodeInfo(
                kind="File",
                name="/repo/utils.py",
                file_path="/repo/utils.py",
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="helper",
                file_path="/repo/utils.py",
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="File",
                name="/repo/main.py",
                file_path="/repo/main.py",
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="IMPORTS_FROM",
                source="/repo/main.py",
                target="/repo/utils.py",
                file_path="/repo/main.py",
                line=1,
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/repo/main.py::run",
                target="/repo/utils.py::helper",
                file_path="/repo/main.py",
                line=5,
            )
        )
        store.commit()

        deps = find_dependents(store, "/repo/utils.py")
        assert "/repo/main.py" in deps
        store.close()

    def test_excludes_self(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        store.upsert_node(
            NodeInfo(
                kind="File",
                name="/repo/a.py",
                file_path="/repo/a.py",
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="IMPORTS_FROM",
                source="/repo/a.py",
                target="/repo/a.py",
                file_path="/repo/a.py",
                line=1,
            )
        )
        store.commit()

        deps = find_dependents(store, "/repo/a.py")
        assert "/repo/a.py" not in deps
        store.close()


# ---------------------------------------------------------------------------
# full_build edge cases
# ---------------------------------------------------------------------------


class TestFullBuildExtra:
    def test_purges_stale_files(self, tmp_path):
        (tmp_path / ".git").mkdir()
        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        # Pre-populate with a file
        store.upsert_node(
            NodeInfo(
                kind="File",
                name=str(tmp_path / "old.py"),
                file_path=str(tmp_path / "old.py"),
                line_start=1,
                line_end=10,
                language="python",
            )
        )
        store.commit()

        # Now build with no files
        with patch(
            "better_code_review_graph.incremental.get_all_tracked_files",
            return_value=[],
        ):
            result = full_build(tmp_path, store)

        assert result["files_parsed"] == 0
        # Old file should be purged
        nodes = store.get_nodes_by_file(str(tmp_path / "old.py"))
        assert len(nodes) == 0
        store.close()

    def test_handles_parse_errors(self, tmp_path):
        (tmp_path / ".git").mkdir()
        py_file = tmp_path / "bad.py"
        py_file.write_text("valid python\n")

        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        with patch(
            "better_code_review_graph.incremental.get_all_tracked_files",
            return_value=["bad.py"],
        ):
            with patch("better_code_review_graph.incremental.CodeParser") as MockParser:
                parser_inst = MockParser.return_value
                parser_inst.detect_language.return_value = "python"
                parser_inst.parse_bytes.side_effect = RuntimeError("parse error")
                result = full_build(tmp_path, store)

        assert len(result["errors"]) == 1
        assert "parse error" in result["errors"][0]["error"]
        store.close()

    def test_handles_os_error(self, tmp_path):
        (tmp_path / ".git").mkdir()
        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        # File that exists in listing but can't be read
        with patch(
            "better_code_review_graph.incremental.get_all_tracked_files",
            return_value=["noread.py"],
        ):
            with patch(
                "better_code_review_graph.incremental.collect_all_files",
                return_value=["noread.py"],
            ):
                result = full_build(tmp_path, store)

        assert len(result["errors"]) >= 1
        store.close()


# ---------------------------------------------------------------------------
# incremental_update edge cases
# ---------------------------------------------------------------------------


class TestIncrementalUpdateExtra:
    def test_skips_ignored_files(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        result = incremental_update(
            tmp_path, store, changed_files=["node_modules/pkg/index.js"]
        )
        assert result["files_updated"] >= 1  # It counts the file but skips processing
        store.close()

    def test_skips_unsupported_language(self, tmp_path):
        (tmp_path / "readme.txt").write_text("text\n")
        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        result = incremental_update(tmp_path, store, changed_files=["readme.txt"])
        assert result["files_updated"] >= 1
        store.close()

    def test_skips_unchanged_hash(self, tmp_path):
        py_file = tmp_path / "stable.py"
        py_file.write_text("x = 1\n")
        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        # First update
        result1 = incremental_update(tmp_path, store, changed_files=["stable.py"])
        assert result1["total_nodes"] > 0

        # Second update without changing file should skip (hash match)
        result2 = incremental_update(tmp_path, store, changed_files=["stable.py"])
        # Should still succeed
        assert result2["files_updated"] >= 1
        store.close()

    def test_incremental_with_parse_error(self, tmp_path):
        py_file = tmp_path / "err.py"
        py_file.write_text("def broken():\n    pass\n")
        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        with patch("better_code_review_graph.incremental.CodeParser") as MockParser:
            parser_inst = MockParser.return_value
            parser_inst.detect_language.return_value = "python"
            parser_inst.parse_bytes.side_effect = RuntimeError("parse fail")
            result = incremental_update(tmp_path, store, changed_files=["err.py"])

        assert len(result["errors"]) == 1
        store.close()


# ---------------------------------------------------------------------------
# Git operations edge cases
# ---------------------------------------------------------------------------


class TestGitOperationsExtra:
    @patch("better_code_review_graph.incremental.subprocess.run")
    def test_get_changed_files_file_not_found(self, mock_run, tmp_path):
        mock_run.side_effect = FileNotFoundError("git not found")
        result = get_changed_files(tmp_path)
        assert result == []

    @patch("better_code_review_graph.incremental.subprocess.run")
    def test_get_staged_timeout(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired("git", 30)
        result = get_staged_and_unstaged(tmp_path)
        assert result == []

    @patch("better_code_review_graph.incremental.subprocess.run")
    def test_get_staged_file_not_found(self, mock_run, tmp_path):
        mock_run.side_effect = FileNotFoundError("git not found")
        result = get_staged_and_unstaged(tmp_path)
        assert result == []

    @patch("better_code_review_graph.incremental.subprocess.run")
    def test_get_all_tracked_timeout(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired("git", 30)
        result = get_all_tracked_files(tmp_path)
        assert result == []

    @patch("better_code_review_graph.incremental.subprocess.run")
    def test_get_all_tracked_file_not_found(self, mock_run, tmp_path):
        mock_run.side_effect = FileNotFoundError("git not found")
        result = get_all_tracked_files(tmp_path)
        assert result == []

    @patch("better_code_review_graph.incremental.subprocess.run")
    def test_get_staged_short_lines_skipped(self, mock_run, tmp_path):
        """Lines shorter than 4 chars should be skipped."""
        mock_run.return_value = MagicMock(returncode=0, stdout="AB\n M file.py\n")
        result = get_staged_and_unstaged(tmp_path)
        assert "file.py" in result


# ---------------------------------------------------------------------------
# Watch mode
# ---------------------------------------------------------------------------


class TestWatchMode:
    def test_watch_starts_and_stops(self, tmp_path):
        (tmp_path / ".git").mkdir()
        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        captured_handler = {}

        class FakeObserver:
            def schedule(self, handler, path, recursive=False):
                captured_handler["handler"] = handler

            def start(self):
                pass

            def stop(self):
                pass

            def join(self):
                pass

        with patch("watchdog.observers.Observer", return_value=FakeObserver()):
            with patch("time.sleep", side_effect=KeyboardInterrupt()):
                watch(tmp_path, store)

        # Verify we captured the handler
        assert "handler" in captured_handler
        handler = captured_handler["handler"]

        # Test handler methods directly
        # Create a real python file
        test_py = tmp_path / "test_watch.py"
        test_py.write_text("def watched():\n    pass\n")

        # Test _should_handle
        assert handler._should_handle(str(test_py)) is True
        assert handler._should_handle(str(tmp_path / "node_modules" / "a.js")) is False
        assert handler._should_handle(str(tmp_path / "readme.txt")) is False
        # Path outside repo
        assert handler._should_handle("/totally/outside/path.py") is False

        # Test on_modified with directory (should be ignored)
        dir_event = MagicMock()
        dir_event.is_directory = True
        handler.on_modified(dir_event)

        # Test on_created with directory
        handler.on_created(dir_event)

        # Test on_deleted with directory
        handler.on_deleted(dir_event)

        # Test on_deleted with tracked file
        del_event = MagicMock()
        del_event.is_directory = False
        del_event.src_path = str(test_py)
        handler.on_deleted(del_event)

        # Test on_deleted with ignored file
        ignored_event = MagicMock()
        ignored_event.is_directory = False
        ignored_event.src_path = str(tmp_path / "node_modules" / "pkg" / "index.js")
        handler.on_deleted(ignored_event)

        # Test on_deleted with file outside repo
        outside_event = MagicMock()
        outside_event.is_directory = False
        outside_event.src_path = "/totally/outside.py"
        handler.on_deleted(outside_event)

        # Test _update_file with real file
        update_py = tmp_path / "update_me.py"
        update_py.write_text("x = 42\n")
        handler._update_file(str(update_py))

        # Test _update_file with missing file
        handler._update_file(str(tmp_path / "missing.py"))

        # Test _update_file with binary file
        bin_file = tmp_path / "binary.py"
        bin_file.write_bytes(b"\x00binary")
        handler._update_file(str(bin_file))

        # Test _schedule and _flush
        handler._schedule(str(update_py))
        assert str(update_py) in handler._pending or handler._timer is not None
        # Cancel any pending timer
        if handler._timer:
            handler._timer.cancel()
        handler._flush()

        # Test _update_file with parse error (via symlink)
        if not (tmp_path / "link.py").exists():
            try:
                (tmp_path / "link.py").symlink_to(test_py)
                handler._update_file(str(tmp_path / "link.py"))
            except OSError:
                pass

        store.close()

    def test_on_modified_triggers_schedule(self, tmp_path):
        """on_modified should schedule an update for handled files."""
        (tmp_path / ".git").mkdir()
        py_file = tmp_path / "mod.py"
        py_file.write_text("y = 1\n")

        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))

        captured_handler = {}

        class FakeObserver:
            def schedule(self, handler, path, recursive=False):
                captured_handler["handler"] = handler

            def start(self):
                pass

            def stop(self):
                pass

            def join(self):
                pass

        with patch("watchdog.observers.Observer", return_value=FakeObserver()):
            with patch("time.sleep", side_effect=KeyboardInterrupt()):
                watch(tmp_path, store)

        handler = captured_handler["handler"]
        event = MagicMock()
        event.is_directory = False
        event.src_path = str(py_file)

        handler.on_modified(event)
        assert str(py_file) in handler._pending
        if handler._timer:
            handler._timer.cancel()

        handler.on_created(event)
        if handler._timer:
            handler._timer.cancel()

        store.close()


# ---------------------------------------------------------------------------
# __main__.py
# ---------------------------------------------------------------------------


class TestMainModule:
    def test_main_module_calls_cli(self):
        with patch("better_code_review_graph.cli.main"):
            # Importing __main__ triggers main()
            import importlib

            import better_code_review_graph.__main__  # noqa: F401

            # Reload to trigger the call
            with patch("better_code_review_graph.cli.main") as mock_main:
                importlib.reload(
                    __import__(
                        "better_code_review_graph.__main__", fromlist=["__main__"]
                    )
                )
                mock_main.assert_called_once()
