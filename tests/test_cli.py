"""Tests for the CLI module (cli.py) — serve + update."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from better_code_review_graph.cli import (
    _get_version,
    main,
)


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


class TestMainCLI:
    def test_no_command_prints_usage(self, capsys):
        with patch("sys.argv", ["better-code-review-graph"]):
            main()
        captured = capsys.readouterr()
        assert "better-code-review-graph" in captured.out
        assert "graph action=" in captured.out

    def test_version_flag(self, capsys):
        with patch("sys.argv", ["better-code-review-graph", "-v"]):
            main()
        captured = capsys.readouterr()
        assert "better-code-review-graph" in captured.out

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

    def test_update_command_no_git(self):
        """update without git repo should exit(1)."""
        with patch("sys.argv", ["better-code-review-graph", "update"]):
            with patch(
                "better_code_review_graph.incremental.find_repo_root",
                return_value=None,
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1

    def test_update_command(self, tmp_path, capsys):
        """update with a valid repo runs incremental update."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
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
        (repo / "sample.py").write_text("def foo(): pass\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo,
            capture_output=True,
            check=True,
        )

        with patch(
            "sys.argv",
            ["better-code-review-graph", "update", "--repo", str(repo)],
        ):
            main()
        # No crash = success (update runs silently)
