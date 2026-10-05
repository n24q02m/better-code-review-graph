"""Phase 1 v1.6.x: graph(action='summarize') MCP wiring."""

from __future__ import annotations

from unittest.mock import patch

from crg.graph import GraphStore
from crg.summarizer import (
    BatchSummarizeResult,
    JevRankingReceipt,
)
from crg.tools import summarize_graph_dispatch


def test_dispatch_returns_skipped_when_no_provider(tmp_path, monkeypatch):
    """No chat cell key → status='skipped' with helpful reason."""
    monkeypatch.delenv("HULL_CHAT_API_KEY", raising=False)

    # Use the same store init pattern as other tools tests
    with patch("crg.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        mock_get_store.return_value = (store, tmp_path)
        try:
            result = summarize_graph_dispatch(repo_root=str(tmp_path))
        finally:
            store.close()

    assert result["status"] == "skipped"
    assert result["reason"] == "no_provider_configured"
    assert "models.chat" in result["summary"]


def test_dispatch_returns_ok_with_counts_on_success(tmp_path, monkeypatch):
    """Provider set + nodes processed → status='ok' with counts + summary string."""
    monkeypatch.delenv("HULL_CHAT_API_KEY", raising=False)

    fake_result = BatchSummarizeResult(
        generated=3,
        cached=1,
        skipped_no_provider=False,
        provider="gemini",
        errors=0,
        jev_ranking=JevRankingReceipt(used=False),
    )

    with patch("crg.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        mock_get_store.return_value = (store, tmp_path)
        try:
            with patch("crg.summarizer.batch_summarize") as mock_batch:
                mock_batch.return_value = fake_result
                result = summarize_graph_dispatch(repo_root=str(tmp_path), max_nodes=10)
        finally:
            store.close()

    assert result["status"] == "ok"
    assert result["provider"] == "gemini"
    assert result["generated"] == 3
    assert result["cached"] == 1
    assert result["errors"] == 0
    assert result["jev_ranking"] == {
        "used": False,
        "batches": 0,
        "ranked_nodes": 0,
        "failopen_reason": None,
    }
    assert "3 new" in result["summary"]
    assert "1 cached" in result["summary"]
    assert "gemini" in result["summary"]


def test_dispatch_summary_string_mentions_errors_when_present(tmp_path):
    """When errors > 0, summary string should mention the count."""

    fake_result = BatchSummarizeResult(
        generated=2,
        cached=0,
        skipped_no_provider=False,
        provider="gemini",
        errors=1,
    )

    with patch("crg.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        mock_get_store.return_value = (store, tmp_path)
        try:
            with patch("crg.summarizer.batch_summarize") as mock_batch:
                mock_batch.return_value = fake_result
                result = summarize_graph_dispatch(repo_root=str(tmp_path))
        finally:
            store.close()

    assert "1 error" in result["summary"]


def test_dispatch_returns_error_on_invalid_max_nodes(tmp_path):
    """max_nodes <= 0 → status='error' with ValueError message (caught from batch_summarize)."""

    with patch("crg.tools._get_store") as mock_get_store:
        store = GraphStore(str(tmp_path / "test.db"))
        mock_get_store.return_value = (store, tmp_path)
        try:
            result = summarize_graph_dispatch(repo_root=str(tmp_path), max_nodes=0)
        finally:
            store.close()

    assert result["status"] == "error"
    assert "max_nodes" in result["error"]
