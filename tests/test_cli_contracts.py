"""CLI contract tests verifying local-first CLI subcommands for CRG.

Tests cover:
- graph (build, embed, stats, export, import, summarize)
- query (query, search, impact, large_functions, spot_check, renamed_in_diff, diff)
- review (context, delta)
- security (scan, report, suppress, rule_list)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

from better_code_review_graph.cli import main


class TestCLIGraphContract:
    def test_cli_graph_stats(self, capsys):
        payload = {
            "status": "ok",
            "total_nodes": 42,
            "total_edges": 84,
            "files_count": 5,
        }
        with (
            patch(
                "better_code_review_graph.tools.list_graph_stats", return_value=payload
            ) as mock_stats,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "graph",
                    "stats",
                    "--repo-root",
                    "/tmp/repo",
                ],
            ),
        ):
            rc = main()

        mock_stats.assert_called_once_with(repo_root="/tmp/repo")
        out = capsys.readouterr().out
        assert rc == 0
        assert json.loads(out) == payload

    def test_cli_graph_export(self, capsys):
        payload = {"status": "ok", "format": "crg", "nodes_count": 10}
        with (
            patch(
                "better_code_review_graph.tools.export_graph_dispatch",
                return_value=payload,
            ) as mock_exp,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "graph",
                    "export",
                    "--format",
                    "crg",
                    "--output-path",
                    "/tmp/out.crg",
                ],
            ),
        ):
            rc = main()

        mock_exp.assert_called_once_with(
            format="crg", output_path="/tmp/out.crg", repo_root=None
        )
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload

    def test_cli_graph_import(self, capsys):
        payload = {"status": "ok", "imported_nodes": 10}
        with (
            patch(
                "better_code_review_graph.tools.import_graph_dispatch",
                return_value=payload,
            ) as mock_imp,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "graph",
                    "import",
                    "--input-path",
                    "/tmp/in.crg",
                ],
            ),
        ):
            rc = main()

        mock_imp.assert_called_once_with(import_path="/tmp/in.crg", repo_root=None)
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload

    def test_cli_graph_summarize(self, capsys):
        payload = {"status": "ok", "summarized": 3}
        with (
            patch(
                "better_code_review_graph.tools.summarize_graph_dispatch",
                return_value=payload,
            ) as mock_summarize,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "graph",
                    "summarize",
                    "--max-nodes",
                    "10",
                ],
            ),
        ):
            rc = main()

        mock_summarize.assert_called_once_with(repo_root=None, max_nodes=10)
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload


class TestCLIQueryContract:
    def test_cli_query_pattern(self, capsys):
        payload = {
            "pattern": "callers_of",
            "target": "main",
            "results": [{"name": "entry"}],
        }
        with (
            patch(
                "better_code_review_graph.tools.query_graph", return_value=payload
            ) as mock_q,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "query",
                    "query",
                    "--pattern",
                    "callers_of",
                    "--target",
                    "main",
                ],
            ),
        ):
            rc = main()

        mock_q.assert_called_once_with(
            pattern="callers_of",
            target="main",
            repo_root=None,
            repo="",
            languages=None,
            as_of="",
        )
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload

    def test_cli_query_search(self, capsys):
        payload = {"query": "auth", "results": [{"name": "authenticate"}]}
        with (
            patch(
                "better_code_review_graph.tools.semantic_search_nodes",
                return_value=payload,
            ) as mock_s,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "query",
                    "search",
                    "--search-query",
                    "auth",
                    "--limit",
                    "10",
                ],
            ),
        ):
            rc = main()

        mock_s.assert_called_once_with(
            query="auth",
            repo_root=None,
            limit=10,
            kind=None,
            repo="",
            as_of="",
        )
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload

    def test_cli_query_impact(self, capsys):
        payload = {"changed_files": ["app.py"], "impacted_files": ["main.py"]}
        with (
            patch(
                "better_code_review_graph.tools.get_impact_radius", return_value=payload
            ) as mock_imp,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "query",
                    "impact",
                    "--changed-files",
                    "app.py",
                    "auth.py",
                    "--max-depth",
                    "2",
                ],
            ),
        ):
            rc = main()

        mock_imp.assert_called_once_with(
            changed_files=["app.py", "auth.py"],
            base="HEAD~1",
            repo_root=None,
            max_depth=2,
            max_results=500,
            max_payload_bytes=500_000,
            repo="",
            as_of="",
        )
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload

    def test_cli_query_large_functions(self, capsys):
        payload = {"results": [{"name": "huge_fn", "lines": 150}]}
        with (
            patch(
                "better_code_review_graph.tools.find_large_functions",
                return_value=payload,
            ) as mock_lf,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "query",
                    "large_functions",
                    "--min-lines",
                    "100",
                ],
            ),
        ):
            rc = main()

        mock_lf.assert_called_once_with(
            min_lines=100,
            kind="function",
            file_path_pattern=None,
            repo_root=None,
            limit=50,
            repo="",
        )
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload


class TestCLIReviewContract:
    def test_cli_review_context(self, capsys):
        payload = {"summary": "1 file changed", "impacted_nodes": []}
        with (
            patch(
                "better_code_review_graph.tools.get_review_context",
                return_value=payload,
            ) as mock_rc,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "review",
                    "context",
                    "--changed-files",
                    "src/mod.py",
                    "--base",
                    "main",
                ],
            ),
        ):
            rc = main()

        mock_rc.assert_called_once_with(
            changed_files=["src/mod.py"],
            base="main",
            repo_root=None,
            max_depth=2,
            repo="",
            languages=None,
        )
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload

    def test_cli_review_delta(self, capsys):
        payload = {
            "status": "ok",
            "from_sha": "abc",
            "to_sha": "def",
            "nodes_added": [],
        }
        with (
            patch(
                "better_code_review_graph.tools.review_delta", return_value=payload
            ) as mock_rd,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "review",
                    "delta",
                    "--from-sha",
                    "abc",
                    "--to-sha",
                    "def",
                ],
            ),
        ):
            rc = main()

        mock_rd.assert_called_once_with(
            from_sha="abc",
            to_sha="def",
            repo_root=None,
            repo="",
        )
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload


class TestCLISecurityContract:
    def test_cli_security_scan(self, capsys):
        payload = {"status": "ok", "total": 0, "findings": []}
        with (
            patch(
                "better_code_review_graph.tools.security_scan", return_value=payload
            ) as mock_ss,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "security",
                    "scan",
                    "--engine",
                    "heuristic",
                    "--repo-root",
                    "/tmp/repo",
                ],
            ),
        ):
            rc = main()

        mock_ss.assert_called_once_with(engine="heuristic", repo_root="/tmp/repo")
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload

    def test_cli_security_report(self, capsys):
        payload = {"status": "ok", "sarif": {"version": "2.1.0"}}
        with (
            patch(
                "better_code_review_graph.tools.security_report", return_value=payload
            ) as mock_sr,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "security",
                    "report",
                    "--format",
                    "sarif",
                ],
            ),
        ):
            rc = main()

        mock_sr.assert_called_once_with(format="sarif", repo_root=None)
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload

    def test_cli_security_suppress(self, capsys):
        payload = {"status": "ok", "suppressions": ["CRG001"]}
        with (
            patch(
                "better_code_review_graph.tools.security_suppress", return_value=payload
            ) as mock_sup,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "security",
                    "suppress",
                    "--rule-id",
                    "CRG001",
                ],
            ),
        ):
            rc = main()

        mock_sup.assert_called_once_with(rule_id="CRG001", remove=False, repo_root=None)
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload

    def test_cli_security_rule_list(self, capsys):
        payload = {"engine": "heuristic", "rules": []}
        with (
            patch(
                "better_code_review_graph.tools.security_rule_list",
                return_value=payload,
            ) as mock_rl,
            patch.object(
                sys,
                "argv",
                [
                    "better-code-review-graph",
                    "security",
                    "rule_list",
                    "--engine",
                    "heuristic",
                ],
            ),
        ):
            rc = main()

        mock_rl.assert_called_once_with(engine="heuristic")
        assert rc == 0
        assert json.loads(capsys.readouterr().out) == payload

    def test_cli_error_exits_nonzero(self, capsys):
        payload = {"error": "Repository not found"}
        with (
            patch(
                "better_code_review_graph.tools.list_graph_stats", return_value=payload
            ),
            patch.object(sys, "argv", ["better-code-review-graph", "graph", "stats"]),
        ):
            rc = main()

        assert rc == 1
        assert "Repository not found" in capsys.readouterr().out


def test_bundled_skills_use_local_cli_without_mcp_tool_calls():
    skills_root = Path(__file__).resolve().parents[1] / "skills"
    skill_files = sorted(skills_root.glob("*/SKILL.md"))

    assert len(skill_files) == 6
    mcp_call = re.compile(r"`(?:graph|query|review|security|help)\([^`]*\)`")
    bare_subcommand = re.compile(r"`(?:graph|query|review|security|config)\s")
    for skill_file in skill_files:
        content = skill_file.read_text(encoding="utf-8")
        assert "better-code-review-graph" in content, skill_file
        assert not mcp_call.findall(content), skill_file
        assert not bare_subcommand.findall(content), skill_file


def test_readme_installs_local_cli_before_optional_mcp_adapter():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
        encoding="utf-8"
    )

    local_cli = readme.index("For OMP and other local coding harnesses")
    optional_mcp = readme.index("MCP stdio remains a secondary protocol adapter")
    assert local_cli < optional_mcp
    assert re.search(r"do\s+not require an MCP server mapping", readme)
