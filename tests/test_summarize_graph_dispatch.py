"""Phase 1 v1.6.x: graph(action='summarize') MCP wiring."""

from __future__ import annotations

from unittest.mock import patch

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.summarizer import BatchSummarizeResult
from better_code_review_graph.tools import summarize_graph_dispatch


def test_dispatch_returns_skipped_when_no_provider(tmp_path, monkeypatch):
    """No provider env var set → status='skipped' with helpful reason."""
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    # Use the same store init pattern as other tools tests
    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        mock_get_store.return_value = (store, tmp_path)
        try:
            result = summarize_graph_dispatch(repo_root=str(tmp_path))
        finally:
            store.close()

    assert result["status"] == "skipped"
    assert result["reason"] == "no_provider_configured"
    assert "GEMINI_API_KEY" in result["summary"]


def test_dispatch_returns_ok_with_counts_on_success(tmp_path, monkeypatch):
    """Provider set + nodes processed → status='ok' with counts + summary string."""
    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    fake_result = BatchSummarizeResult(
        generated=3,
        cached=1,
        skipped_no_provider=False,
        provider="gemini",
        errors=0,
    )

    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        mock_get_store.return_value = (store, tmp_path)
        try:
            with patch(
                "better_code_review_graph.summarizer.batch_summarize"
            ) as mock_batch:
                mock_batch.return_value = fake_result
                result = summarize_graph_dispatch(repo_root=str(tmp_path), max_nodes=10)
        finally:
            store.close()

    assert result["status"] == "ok"
    assert result["provider"] == "gemini"
    assert result["generated"] == 3
    assert result["cached"] == 1
    assert result["errors"] == 0
    assert "3 new" in result["summary"]
    assert "1 cached" in result["summary"]
    assert "gemini" in result["summary"]


def test_dispatch_summary_string_mentions_errors_when_present(tmp_path, monkeypatch):
    """When errors > 0, summary string should mention the count."""
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    fake_result = BatchSummarizeResult(
        generated=2,
        cached=0,
        skipped_no_provider=False,
        provider="gemini",
        errors=1,
    )

    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        mock_get_store.return_value = (store, tmp_path)
        try:
            with patch(
                "better_code_review_graph.summarizer.batch_summarize"
            ) as mock_batch:
                mock_batch.return_value = fake_result
                result = summarize_graph_dispatch(repo_root=str(tmp_path))
        finally:
            store.close()

    assert "1 error" in result["summary"]


def test_dispatch_returns_error_on_invalid_max_nodes(tmp_path, monkeypatch):
    """max_nodes <= 0 → status='error' with ValueError message (caught from batch_summarize)."""
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    with patch("better_code_review_graph.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        mock_get_store.return_value = (store, tmp_path)
        try:
            result = summarize_graph_dispatch(repo_root=str(tmp_path), max_nodes=0)
        finally:
            store.close()

    assert result["status"] == "error"
    assert "max_nodes" in result["error"]
