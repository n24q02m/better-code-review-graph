"""Tests for the Phase 3 Task 5 ``security`` MCP tool.

Covers:

* ``security_scan`` (heuristic + semgrep dispatch)
* ``security_report`` (json + sarif format)
* ``security_suppress`` (add + remove + missing rule_id)
* ``security_rule_list`` (heuristic + semgrep with/without overlay)
* server-level ``security`` action dispatcher
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.security import Tag
from better_code_review_graph.security.semgrep_engine import (
    SemgrepNotAvailable,
    SemgrepResult,
)
from better_code_review_graph.tools import (
    _load_last_scan,
    _load_suppressions,
    _save_suppressions,
    security_report,
    security_rule_list,
    security_scan,
    security_suppress,
)

# ---------------------------------------------------------------------------
# Shared fixture: a repo root with a populated GraphStore.
# ---------------------------------------------------------------------------


def _make_repo_with_node(
    tmp_path: Path,
    *,
    name: str = "vulnerable_query",
    file_path: str = "src/db.py",
    source_text: str | None = None,
    language: str = "python",
    kind: str = "Function",
) -> tuple[Path, str]:
    """Materialise a repo root + a single Function node + return (root, qname)."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    crg_dir = tmp_path / ".code-review-graph"
    crg_dir.mkdir(exist_ok=True)
    db_path = crg_dir / "graph.db"

    # Default to an obvious SQL-injection sink so the heuristic scanner fires.
    if source_text is None:
        source_text = (
            "def vulnerable_query(user_id):\n"
            '    cursor.execute(f"SELECT * FROM users WHERE id={user_id}")\n'
        )

    store = GraphStore(db_path)
    try:
        store.upsert_node(
            NodeInfo(
                kind=kind,
                name=name,
                file_path=file_path,
                line_start=1,
                line_end=10,
                language=language,
                source_text=source_text,
            )
        )
        store._conn.commit()
    finally:
        store.close()
    qualified = f"{file_path}::{name}"
    return tmp_path, qualified


# ---------------------------------------------------------------------------
# security_scan
# ---------------------------------------------------------------------------


def test_security_scan_heuristic_default(tmp_path: Path) -> None:
    """A SQL-injection f-string in a Function node produces ``HIGH`` finding."""
    root, qname = _make_repo_with_node(tmp_path)
    payload = security_scan(repo_root=str(root))
    assert payload["engine"] == "heuristic"
    assert payload["total"] >= 1
    assert payload["by_severity"].get("HIGH", 0) >= 1
    assert qname in payload["tags_by_node"]
    tag_entries = payload["tags_by_node"][qname]
    assert any(entry["rule_id"] == "cwe-89-sql-string-format" for entry in tag_entries)


def test_security_scan_semgrep_returns_error_when_cli_missing(tmp_path: Path) -> None:
    root, _ = _make_repo_with_node(tmp_path)

    def _raise(self, *args, **kwargs):
        raise SemgrepNotAvailable("semgrep not installed for test")

    with patch(
        "better_code_review_graph.tools.SemgrepScanner.__init__",
        new=_raise,
    ):
        payload = security_scan(repo_root=str(root), engine="semgrep")
    assert payload["engine"] == "semgrep"
    assert "error" in payload
    assert "not installed" in payload["error"]


def test_security_scan_semgrep_uses_scanner_when_available(tmp_path: Path) -> None:
    """When the CLI is available, results are aggregated under ``(repo-wide)``."""
    root, _ = _make_repo_with_node(tmp_path)
    fake_tag = Tag(
        rule_id="semgrep-rule-x",
        severity="MEDIUM",
        message="hardcoded literal",
        line=2,
    )

    class _FakeScanner:
        def __init__(self, *args, **kwargs):
            return None

        def scan_path(self, target):
            return SemgrepResult(tags=[fake_tag], raw_output="{}")

    with patch("better_code_review_graph.tools.SemgrepScanner", new=_FakeScanner):
        payload = security_scan(repo_root=str(root), engine="semgrep")
    assert payload["engine"] == "semgrep"
    assert payload["total"] == 1
    assert payload["by_severity"].get("MEDIUM") == 1
    assert "(repo-wide)" in payload["tags_by_node"]


def test_security_scan_caches_last_scan_to_disk(tmp_path: Path) -> None:
    root, _ = _make_repo_with_node(tmp_path)
    payload = security_scan(repo_root=str(root))
    cache_path = root / ".code-review-graph" / "security-last-scan.json"
    assert cache_path.is_file(), "cache file should be written"
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached == payload


def test_security_scan_persists_security_tags_to_nodes(tmp_path: Path) -> None:
    root, qname = _make_repo_with_node(tmp_path)
    security_scan(repo_root=str(root))
    db_path = root / ".code-review-graph" / "graph.db"
    store = GraphStore(db_path)
    try:
        row = store._conn.execute(
            "SELECT security_tags FROM nodes WHERE qualified_name = ?",
            (qname,),
        ).fetchone()
        assert row is not None
        assert row["security_tags"] is not None
        decoded = json.loads(row["security_tags"])
        assert isinstance(decoded, list)
        assert any("cwe-89" in entry for entry in decoded)
    finally:
        store.close()


def test_security_scan_skips_suppressed_rules(tmp_path: Path) -> None:
    root, qname = _make_repo_with_node(tmp_path)
    _save_suppressions(root, ["cwe-89-sql-string-format"])
    payload = security_scan(repo_root=str(root))
    assert qname not in payload["tags_by_node"]
    assert payload["suppressed_count"] == 1


def test_security_scan_no_findings_yields_empty_payload(tmp_path: Path) -> None:
    """A node whose source text does not match any rule produces no tags."""
    root, qname = _make_repo_with_node(
        tmp_path,
        source_text="def safe(): return 1\n",
    )
    payload = security_scan(repo_root=str(root))
    assert payload["total"] == 0
    assert qname not in payload["tags_by_node"]


# ---------------------------------------------------------------------------
# security_report
# ---------------------------------------------------------------------------


def test_security_report_returns_json_by_default(tmp_path: Path) -> None:
    root, _ = _make_repo_with_node(tmp_path)
    scan_payload = security_scan(repo_root=str(root))
    report = security_report(repo_root=str(root))
    assert report == scan_payload


def test_security_report_returns_sarif_when_format_sarif(tmp_path: Path) -> None:
    root, qname = _make_repo_with_node(tmp_path)
    security_scan(repo_root=str(root))
    sarif = security_report(repo_root=str(root), format="sarif")
    assert sarif["version"] == "2.1.0"
    assert "runs" in sarif and len(sarif["runs"]) == 1
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "better-code-review-graph"
    assert run["results"], "SARIF run should carry at least one result"
    first = run["results"][0]
    assert first["ruleId"] == "cwe-89-sql-string-format"
    assert first["level"] == "error"  # HIGH -> error
    assert first["locations"][0]["logicalLocations"][0]["name"] == qname


def test_security_report_returns_error_when_no_prior_scan(tmp_path: Path) -> None:
    root, _ = _make_repo_with_node(tmp_path)
    # Do NOT call security_scan first.
    report = security_report(repo_root=str(root))
    assert "error" in report
    assert "No prior scan" in report["error"]


# ---------------------------------------------------------------------------
# security_suppress
# ---------------------------------------------------------------------------


def test_security_suppress_adds_rule_id(tmp_path: Path) -> None:
    root, _ = _make_repo_with_node(tmp_path)
    payload = security_suppress(repo_root=str(root), rule_id="cwe-89")
    assert payload["rule_id"] == "cwe-89"
    assert payload["suppressed"] is True
    assert payload["total_suppressed"] == 1
    assert "cwe-89" in _load_suppressions(root)


def test_security_suppress_remove_clears_rule_id(tmp_path: Path) -> None:
    root, _ = _make_repo_with_node(tmp_path)
    _save_suppressions(root, ["cwe-89", "cwe-78"])
    payload = security_suppress(repo_root=str(root), rule_id="cwe-89", remove=True)
    assert payload["suppressed"] is False
    assert payload["total_suppressed"] == 1
    sup = _load_suppressions(root)
    assert "cwe-89" not in sup
    assert "cwe-78" in sup


def test_security_suppress_returns_error_without_rule_id(tmp_path: Path) -> None:
    root, _ = _make_repo_with_node(tmp_path)
    payload = security_suppress(repo_root=str(root), rule_id=None)
    assert "error" in payload
    assert "rule_id" in payload["error"]


def test_security_suppress_persists_across_calls(tmp_path: Path) -> None:
    root, _ = _make_repo_with_node(tmp_path)
    security_suppress(repo_root=str(root), rule_id="cwe-22")
    security_suppress(repo_root=str(root), rule_id="cwe-95")
    sup = _load_suppressions(root)
    assert sup == {"cwe-22", "cwe-95"}


# ---------------------------------------------------------------------------
# security_rule_list
# ---------------------------------------------------------------------------


def test_security_rule_list_heuristic() -> None:
    payload = security_rule_list(engine="heuristic")
    assert payload["engine"] == "heuristic"
    assert isinstance(payload["rules"], list)
    assert len(payload["rules"]) >= 1
    sample = payload["rules"][0]
    assert {"id", "severity", "languages", "message"} <= set(sample.keys())


def test_security_rule_list_semgrep_with_overlay() -> None:
    payload = security_rule_list(engine="semgrep")
    assert payload["engine"] == "semgrep"
    if payload["rules"]:
        # At least the curated.yaml exists in the repo checkout.
        assert any(name.endswith(".yaml") for name in payload["rules"])
    else:
        assert "note" in payload


def test_security_rule_list_semgrep_no_overlay(monkeypatch) -> None:
    monkeypatch.setattr(
        "better_code_review_graph.tools._resolve_overlay_rules_dir",
        lambda: None,
    )
    payload = security_rule_list(engine="semgrep")
    assert payload["engine"] == "semgrep"
    assert payload["rules"] == []
    assert "note" in payload


# ---------------------------------------------------------------------------
# Suppression persistence helpers
# ---------------------------------------------------------------------------


def test_load_suppressions_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert _load_suppressions(tmp_path) == set()


def test_load_suppressions_handles_corrupt_file(tmp_path: Path) -> None:
    sup_path = tmp_path / ".code-review-graph" / "security-suppressions.json"
    sup_path.parent.mkdir(parents=True, exist_ok=True)
    sup_path.write_text("not-json", encoding="utf-8")
    assert _load_suppressions(tmp_path) == set()


def test_load_suppressions_rejects_non_list_payload(tmp_path: Path) -> None:
    sup_path = tmp_path / ".code-review-graph" / "security-suppressions.json"
    sup_path.parent.mkdir(parents=True, exist_ok=True)
    sup_path.write_text('{"not": "a list"}', encoding="utf-8")
    assert _load_suppressions(tmp_path) == set()


def test_security_scan_semgrep_filters_suppressed_tag(tmp_path: Path) -> None:
    """Suppressed rule_id is dropped from semgrep tags_by_node bucket."""
    root, _ = _make_repo_with_node(tmp_path)
    _save_suppressions(root, ["semgrep-rule-x"])
    suppressed_tag = Tag(
        rule_id="semgrep-rule-x",
        severity="MEDIUM",
        message="suppressed",
        line=1,
    )
    surviving_tag = Tag(
        rule_id="semgrep-rule-y",
        severity="HIGH",
        message="not suppressed",
        line=2,
    )

    class _FakeScanner:
        def __init__(self, *args, **kwargs):
            return None

        def scan_path(self, target):
            return SemgrepResult(
                tags=[suppressed_tag, surviving_tag],
                raw_output="{}",
            )

    with patch("better_code_review_graph.tools.SemgrepScanner", new=_FakeScanner):
        payload = security_scan(repo_root=str(root), engine="semgrep")
    assert payload["total"] == 1
    assert "semgrep-rule-y" in payload["by_rule"]
    assert "semgrep-rule-x" not in payload["by_rule"]


def test_load_last_scan_returns_none_when_missing(tmp_path: Path) -> None:
    assert _load_last_scan(tmp_path) is None


def test_load_last_scan_handles_corrupt_file(tmp_path: Path) -> None:
    cache_path = tmp_path / ".code-review-graph" / "security-last-scan.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{not json", encoding="utf-8")
    assert _load_last_scan(tmp_path) is None


# ---------------------------------------------------------------------------
# Server-level ``security`` action dispatcher
# ---------------------------------------------------------------------------


def test_server_security_tool_dispatches_scan(tmp_path: Path) -> None:
    from better_code_review_graph.server import security as security_tool

    root, _ = _make_repo_with_node(tmp_path)
    payload = security_tool(action="scan", repo_root=str(root))
    assert payload["engine"] == "heuristic"
    assert payload["total"] >= 1


def test_server_security_tool_dispatches_report(tmp_path: Path) -> None:
    from better_code_review_graph.server import security as security_tool

    root, _ = _make_repo_with_node(tmp_path)
    security_scan(repo_root=str(root))
    sarif = security_tool(action="report", repo_root=str(root), format="sarif")
    assert sarif["version"] == "2.1.0"


def test_server_security_tool_dispatches_suppress(tmp_path: Path) -> None:
    from better_code_review_graph.server import security as security_tool

    root, _ = _make_repo_with_node(tmp_path)
    payload = security_tool(action="suppress", repo_root=str(root), rule_id="cwe-89")
    assert payload["rule_id"] == "cwe-89"
    assert payload["suppressed"] is True


def test_server_security_tool_dispatches_rule_list(tmp_path: Path) -> None:
    from better_code_review_graph.server import security as security_tool

    payload = security_tool(action="rule_list", engine="heuristic")
    assert payload["engine"] == "heuristic"
    assert payload["rules"]


def test_server_security_tool_invalid_action_returns_error() -> None:
    from better_code_review_graph.server import security as security_tool

    payload = security_tool(action="bogus")
    assert "error" in payload
    assert "bogus" in payload["error"]
