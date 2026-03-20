"""Tests for the CLI module (cli.py)."""

from __future__ import annotations

import json
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.cli import (
    _get_version,
    _handle_init,
    _print_banner,
    _supports_color,
    main,
)

# ---------------------------------------------------------------------------
# _get_version
# ---------------------------------------------------------------------------


class TestGetVersion:
    def test_returns_string(self):
        version = _get_version()
        assert isinstance(version, str)
        assert len(version) > 0

    @patch(
        "better_code_review_graph.cli.pkg_version",
        side_effect=Exception("not installed"),
    )
    def test_fallback_to_dev(self, mock_ver):
        assert _get_version() == "dev"


# ---------------------------------------------------------------------------
# _supports_color
# ---------------------------------------------------------------------------


class TestSupportsColor:
    def test_no_color_env(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        assert _supports_color() is False

    def test_not_tty(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        with patch.object(sys, "stdout", new_callable=StringIO):
            assert _supports_color() is False

    def test_no_isatty_attr(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        mock_stdout = MagicMock(spec=[])  # No isatty attribute
        with patch.object(sys, "stdout", mock_stdout):
            assert _supports_color() is False


# ---------------------------------------------------------------------------
# _print_banner
# ---------------------------------------------------------------------------


class TestPrintBanner:
    def test_prints_without_error(self, capsys):
        _print_banner()
        captured = capsys.readouterr()
        assert "better-code-review-graph" in captured.out
        assert "Commands:" in captured.out


# ---------------------------------------------------------------------------
# _handle_init
# ---------------------------------------------------------------------------


class TestHandleInit:
    def test_creates_mcp_json(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        args = MagicMock()
        args.repo = str(tmp_path)
        args.dry_run = False

        _handle_init(args)

        mcp_path = tmp_path / ".mcp.json"
        assert mcp_path.exists()
        data = json.loads(mcp_path.read_text())
        assert "better-code-review-graph" in data["mcpServers"]
        captured = capsys.readouterr()
        assert "Created" in captured.out

    def test_already_configured(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        mcp_path = tmp_path / ".mcp.json"
        existing = {"mcpServers": {"better-code-review-graph": {"command": "test"}}}
        mcp_path.write_text(json.dumps(existing))

        args = MagicMock()
        args.repo = str(tmp_path)
        args.dry_run = False

        _handle_init(args)

        captured = capsys.readouterr()
        assert "Already configured" in captured.out

    def test_merges_existing_config(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        mcp_path = tmp_path / ".mcp.json"
        existing = {"mcpServers": {"other-server": {"command": "other"}}}
        mcp_path.write_text(json.dumps(existing))

        args = MagicMock()
        args.repo = str(tmp_path)
        args.dry_run = False

        _handle_init(args)

        data = json.loads(mcp_path.read_text())
        assert "other-server" in data["mcpServers"]
        assert "better-code-review-graph" in data["mcpServers"]

    def test_malformed_existing_config(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text("not json")

        args = MagicMock()
        args.repo = str(tmp_path)
        args.dry_run = False

        _handle_init(args)

        data = json.loads(mcp_path.read_text())
        assert "better-code-review-graph" in data["mcpServers"]
        captured = capsys.readouterr()
        assert "malformed" in captured.out

    def test_dry_run(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        args = MagicMock()
        args.repo = str(tmp_path)
        args.dry_run = True

        _handle_init(args)

        assert not (tmp_path / ".mcp.json").exists()
        captured = capsys.readouterr()
        assert "[dry-run]" in captured.out

    def test_auto_detect_repo(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        args = MagicMock()
        args.repo = None
        args.dry_run = False

        with patch(
            "better_code_review_graph.incremental.find_repo_root", return_value=tmp_path
        ):
            _handle_init(args)

        assert (tmp_path / ".mcp.json").exists()

    def test_fallback_to_cwd(self, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)
        args = MagicMock()
        args.repo = None
        args.dry_run = True

        with patch(
            "better_code_review_graph.incremental.find_repo_root", return_value=None
        ):
            _handle_init(args)

        captured = capsys.readouterr()
        assert "[dry-run]" in captured.out


# ---------------------------------------------------------------------------
# main() CLI entry point
# ---------------------------------------------------------------------------


class TestMainCLI:
    def test_no_command_prints_banner(self, capsys):
        with patch("sys.argv", ["better-code-review-graph"]):
            main()
        captured = capsys.readouterr()
        assert "better-code-review-graph" in captured.out

    def test_version_flag(self, capsys):
        with patch("sys.argv", ["better-code-review-graph", "-v"]):
            main()
        captured = capsys.readouterr()
        assert "better-code-review-graph" in captured.out

    def test_install_command(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        with patch(
            "sys.argv", ["better-code-review-graph", "install", "--repo", str(tmp_path)]
        ):
            main()
        assert (tmp_path / ".mcp.json").exists()

    def test_init_command(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        with patch(
            "sys.argv", ["better-code-review-graph", "init", "--repo", str(tmp_path)]
        ):
            main()
        assert (tmp_path / ".mcp.json").exists()

    def test_serve_command(self):
        with patch("sys.argv", ["better-code-review-graph", "serve"]):
            with patch("better_code_review_graph.server.serve_main") as mock_serve:
                main()
                mock_serve.assert_called_once_with(repo_root=None)

    def test_serve_command_with_repo(self):
        with patch(
            "sys.argv", ["better-code-review-graph", "serve", "--repo", "/my/repo"]
        ):
            with patch("better_code_review_graph.server.serve_main") as mock_serve:
                main()
                mock_serve.assert_called_once_with(repo_root="/my/repo")

    def test_build_command(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        py_file = tmp_path / "sample.py"
        py_file.write_text("def foo():\n    pass\n")

        with patch(
            "sys.argv", ["better-code-review-graph", "build", "--repo", str(tmp_path)]
        ):
            with patch(
                "better_code_review_graph.incremental.get_all_tracked_files",
                return_value=["sample.py"],
            ):
                main()

        captured = capsys.readouterr()
        assert "Full build" in captured.out

    def test_update_command_no_git(self, tmp_path, capsys):
        """update without git should exit(1) when find_repo_root returns None."""
        sub = tmp_path / "no_git"
        sub.mkdir()
        # Don't pass --repo so it uses find_repo_root which returns None
        with patch("sys.argv", ["better-code-review-graph", "update"]):
            with patch(
                "better_code_review_graph.incremental.find_repo_root", return_value=None
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1

    def test_update_command(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        py_file = tmp_path / "mod.py"
        py_file.write_text("x = 1\n")

        with patch(
            "sys.argv", ["better-code-review-graph", "update", "--repo", str(tmp_path)]
        ):
            with patch(
                "better_code_review_graph.incremental.get_changed_files",
                return_value=["mod.py"],
            ):
                main()

        captured = capsys.readouterr()
        assert "Incremental" in captured.out

    def test_status_command(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        with patch(
            "sys.argv", ["better-code-review-graph", "status", "--repo", str(tmp_path)]
        ):
            main()
        captured = capsys.readouterr()
        assert "Nodes:" in captured.out

    def test_watch_command(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch(
            "sys.argv", ["better-code-review-graph", "watch", "--repo", str(tmp_path)]
        ):
            with patch("better_code_review_graph.incremental.watch") as mock_watch:
                main()
                mock_watch.assert_called_once()

    def test_build_with_errors(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        py_file = tmp_path / "good.py"
        py_file.write_text("def bar():\n    pass\n")

        with patch(
            "sys.argv", ["better-code-review-graph", "build", "--repo", str(tmp_path)]
        ):
            with patch(
                "better_code_review_graph.incremental.get_all_tracked_files",
                return_value=["good.py", "missing.py"],
            ):
                main()

        captured = capsys.readouterr()
        assert "Full build" in captured.out
