import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.incremental import (
    full_build,
    get_all_tracked_files,
    get_changed_files,
    get_db_path,
    get_staged_and_unstaged,
    incremental_update,
    watch,
)


class TestIncrementalCoverageFix:
    def test_get_changed_files_invalid_ref(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid git ref"):
            get_changed_files(tmp_path, base="-invalid")

    def test_get_all_tracked_files_missing_root(self):
        # Line 220
        assert get_all_tracked_files(Path("/non/existent/path/for/sure/123")) == []

    def test_full_build_missing_root(self):
        # Line 277
        store = MagicMock(spec=GraphStore)
        result = full_build(Path("/non/existent/path/for/sure/123"), store)
        assert result["files_parsed"] == 0

    @patch("better_code_review_graph.incremental.subprocess.run")
    def test_get_staged_and_unstaged_error(self, mock_run, tmp_path):
        # Line 171
        mock_run.return_value = MagicMock(returncode=1)
        assert get_staged_and_unstaged(tmp_path) == []

    @patch("better_code_review_graph.incremental.subprocess.run")
    def test_get_all_tracked_files_error(self, mock_run, tmp_path):
        # Line 232
        mock_run.return_value = MagicMock(returncode=1)
        assert get_all_tracked_files(tmp_path) == []

    def test_get_db_path_already_exists(self, tmp_path):
        # Line 56-57 branch
        db_dir = tmp_path / ".code-review-graph"
        db_dir.mkdir()
        path = get_db_path(tmp_path)
        assert path == db_dir / "graph.db"
        assert db_dir.is_dir()

    def test_incremental_update_path_checks(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        db_path = repo_root / "test.db"
        store = GraphStore(str(db_path))

        try:
            # Case 1: path not in repo (line 335)
            with patch(
                "better_code_review_graph.incremental.get_changed_files",
                return_value=["../outside.py"],
            ):
                result = incremental_update(repo_root, store)
                assert "../outside.py" in result["changed_files"]

            # Case 2: symlink in changed_files (line 337)
            real_file = repo_root / "real.py"
            real_file.write_text("x = 1")
            link_file = repo_root / "link.py"
            link_file.symlink_to("real.py")
            with patch(
                "better_code_review_graph.incremental.get_changed_files",
                return_value=["link.py"],
            ):
                result = incremental_update(repo_root, store)
                assert "link.py" in result["changed_files"]

            # Case 3: dependent file relative_to fails (line 342-345)
            changed_file = repo_root / "changed.py"
            changed_file.write_text("import something")
            with patch(
                "better_code_review_graph.incremental.get_changed_files",
                return_value=["changed.py"],
            ):
                with patch(
                    "better_code_review_graph.incremental.find_dependents",
                    return_value=["/outside/dep.py"],
                ):
                    result = incremental_update(repo_root, store)
                    assert "/outside/dep.py" in result["dependent_files"]

            # Case 5: symlink in all_files loop (line 366)
            with patch(
                "better_code_review_graph.incremental.get_changed_files",
                return_value=["link.py"],
            ):
                # Bypass first symlink check by mocking Path.is_symlink
                with patch(
                    "pathlib.Path.is_symlink",
                    side_effect=[False, False, True, True, True],
                ):
                    result = incremental_update(repo_root, store)
                    assert "link.py" in result["changed_files"]

            # Case 6: OSError/PermissionError (line 384)
            perm_file = repo_root / "perm.py"
            perm_file.write_text("x = 1")
            with patch(
                "better_code_review_graph.incremental.get_changed_files",
                return_value=["perm.py"],
            ):
                with patch(
                    "pathlib.Path.read_bytes", side_effect=PermissionError("no read")
                ):
                    result = incremental_update(repo_root, store)
                    assert len(result["errors"]) == 1
                    assert "no read" in result["errors"][0]["error"]

        finally:
            store.close()

    def test_watch_logic_coverage(self, tmp_path):
        (tmp_path / ".git").mkdir()
        db_path = tmp_path / "test.db"
        store = GraphStore(str(db_path))
        try:
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

            # Test _should_handle symlink (line 445)
            link_py = tmp_path / "link.py"
            (tmp_path / "real.py").write_text("x=1")
            link_py.symlink_to("real.py")
            assert handler._should_handle(str(link_py)) is False

            # Test on_modified/on_created directory (line 458, 464)
            event = MagicMock()
            event.is_directory = True
            handler.on_modified(event)
            handler.on_created(event)

            # Test _update_file exception (line 523-524)
            test_py = tmp_path / "test.py"
            test_py.write_text("x = 1")
            with patch(
                "better_code_review_graph.incremental._is_binary", return_value=False
            ):
                with patch(
                    "pathlib.Path.read_bytes", side_effect=RuntimeError("unexpected")
                ):
                    handler._update_file(str(test_py))

        finally:
            store.close()

    @patch("better_code_review_graph.incremental.subprocess.run")
    def test_get_changed_files_explicit_errors(self, mock_run, tmp_path):
        # 1. FileNotFoundError (line 156)
        mock_run.side_effect = FileNotFoundError("git not found")
        assert get_changed_files(tmp_path) == []

        # 2. TimeoutExpired (line 156)
        mock_run.reset_mock()
        mock_run.side_effect = subprocess.TimeoutExpired("git", 30)
        assert get_changed_files(tmp_path) == []
