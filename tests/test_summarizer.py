"""Tests for the LLM summary cache + provider helpers (Phase 1 v1.6.x).

Covers better_code_review_graph.summarizer -- hash derivation,
cache-key composition, provider auto-detection from environment
variables, and the single-node summarize_node LLM call (Gemini /
OpenAI paths, error wrapping, unknown-provider validation). All LLM
client interactions are mocked via unittest.mock.patch against the
private _get_gemini_client / _get_openai_client helpers, so no
network traffic is generated. Batch + cache-lookup wiring lives in
Task 5.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
from unittest.mock import MagicMock, patch

import pytest


def test_compute_source_hash_is_sha256():
    """Simple smoke test for SHA-256 hex digest derivation."""
    from better_code_review_graph.summarizer import compute_source_hash

    # echo -n "test" | sha256sum
    expected = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    assert compute_source_hash("test") == expected


def test_compute_source_hash_empty_string():
    """Empty string is well-defined and returns the empty-input SHA-256."""
    from better_code_review_graph.summarizer import compute_source_hash

    expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert compute_source_hash("") == expected


def test_compute_source_hash_handles_unicode():
    """Non-ASCII characters are UTF-8 encoded before hashing."""
    from better_code_review_graph.summarizer import compute_source_hash

    # Mixed emoji + non-BMP char
    res = compute_source_hash("🔥 \U0001f600")
    assert isinstance(res, str)
    assert len(res) == 64


def test_node_needing_summary_is_frozen():
    """NodeNeedingSummary is an immutable value object."""
    from better_code_review_graph.summarizer import NodeNeedingSummary

    node = NodeNeedingSummary(node_id="1", source_text="s", source_hash="h")
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.node_id = "2"


def test_cache_key_combines_source_hash_and_provider():
    """Format: {hash}:{provider}."""
    from better_code_review_graph.summarizer import (
        NodeNeedingSummary,
        compute_source_hash,
        compute_summary_cache_key,
    )

    src = "def f(): pass"
    h = compute_source_hash(src)
    node = NodeNeedingSummary(node_id="1", source_text=src, source_hash=h)
    key = compute_summary_cache_key(node, "gemini")
    assert key == f"{h}:gemini"


def test_cache_key_changes_when_provider_changes():
    """Provider tag is part of the key to avoid cross-provider cache poisoning."""
    from better_code_review_graph.summarizer import (
        NodeNeedingSummary,
        compute_source_hash,
        compute_summary_cache_key,
    )

    src = "def f(): pass"
    h = compute_source_hash(src)
    node = NodeNeedingSummary(node_id="1", source_text=src, source_hash=h)
    key1 = compute_summary_cache_key(node, "gemini")
    key2 = compute_summary_cache_key(node, "openai")
    assert key1 != key2
    assert "gemini" in key1
    assert "openai" in key2


def test_cache_key_uses_precomputed_hash_when_provided():
    """Avoid redundant hashing if the caller already provided node.source_hash."""
    from better_code_review_graph.summarizer import (
        NodeNeedingSummary,
        compute_summary_cache_key,
    )

    # We provide a dummy hash that DOES NOT match the source_text.
    # The cache-key helper should trust our hash verbatim.
    node = NodeNeedingSummary(
        node_id="1", source_text="real source", source_hash="trusted_hash"
    )
    key = compute_summary_cache_key(node, "gemini")
    assert key == "trusted_hash:gemini"


# ---------------------------------------------------------------------------
# resolve_summary_provider (Detection Logic)
# ---------------------------------------------------------------------------


def test_resolve_provider_prefers_gemini(monkeypatch):
    """GEMINI_API_KEY takes priority over others."""
    from better_code_review_graph.summarizer import resolve_summary_provider

    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")
    res = resolve_summary_provider()
    assert res == ("gemini", "g-key")


def test_resolve_provider_falls_back_to_openai(monkeypatch):
    """If no Gemini key, use OpenAI."""
    from better_code_review_graph.summarizer import resolve_summary_provider

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")
    res = resolve_summary_provider()
    assert res == ("openai", "o-key")


def test_resolve_provider_handles_google_api_key_alias(monkeypatch):
    """GOOGLE_API_KEY is treated as Gemini."""
    from better_code_review_graph.summarizer import resolve_summary_provider

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-alias")
    res = resolve_summary_provider()
    assert res == ("gemini", "google-alias")


def test_resolve_provider_returns_none_when_no_key(monkeypatch):
    """No configured keys -> None."""
    from better_code_review_graph.summarizer import resolve_summary_provider

    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert resolve_summary_provider() is None


def test_resolve_provider_empty_gemini_falls_through_to_google(monkeypatch):
    """Empty string values are treated as 'not set'."""
    from better_code_review_graph.summarizer import resolve_summary_provider

    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "g-alias")
    res = resolve_summary_provider()
    assert res == ("gemini", "g-alias")


def test_resolve_provider_all_empty_returns_none(monkeypatch):
    """If all keys are empty strings, return None."""
    from better_code_review_graph.summarizer import resolve_summary_provider

    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert resolve_summary_provider() is None


# ---------------------------------------------------------------------------
# summarize_node (Single-node LLM Call)
# ---------------------------------------------------------------------------


def test_summarize_node_gemini_returns_text():
    """Success path for Gemini."""
    from better_code_review_graph.summarizer import NodeNeedingSummary, summarize_node

    node = NodeNeedingSummary(node_id="1", source_text="def f(): pass", source_hash="h")
    # Mock response object from SDK
    mock_resp = MagicMock()
    mock_resp.text = " This is a summary.  "

    with patch("better_code_review_graph.summarizer._get_gemini_client") as mock_get:
        mock_get.return_value.models.generate_content.return_value = mock_resp
        res = summarize_node(node, provider="gemini", api_key="test-key")

    assert res == "This is a summary."
    # Verify client was constructed with key
    mock_get.assert_called_once_with("test-key")


def test_summarize_node_openai_returns_text():
    """Success path for OpenAI."""
    from better_code_review_graph.summarizer import NodeNeedingSummary, summarize_node

    node = NodeNeedingSummary(node_id="1", source_text="def f(): pass", source_hash="h")
    # Mock choice object
    mock_choice = MagicMock()
    mock_choice.message.content = " OpenAI summary. "
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    with patch("better_code_review_graph.summarizer._get_openai_client") as mock_get:
        mock_get.return_value.chat.completions.create.return_value = mock_resp
        res = summarize_node(node, provider="openai", api_key="o-key")

    assert res == "OpenAI summary."
    mock_get.assert_called_once_with("o-key")


def test_summarize_node_unknown_provider_raises():
    """ValueError on unsupported provider string."""
    from better_code_review_graph.summarizer import summarize_node

    with pytest.raises(ValueError, match="Unsupported provider"):
        summarize_node(MagicMock(), provider="unknown", api_key="k")


def test_summarize_node_wraps_sdk_errors():
    """RuntimeError wraps SDK-specific exceptions for caller convenience."""
    from better_code_review_graph.summarizer import summarize_node

    with patch(
        "better_code_review_graph.summarizer._get_gemini_client",
        side_effect=Exception("network error"),
    ):
        with pytest.raises(RuntimeError, match="summarize_node failed via gemini"):
            summarize_node(MagicMock(), provider="gemini", api_key="k")


def test_summarize_node_gemini_empty_text_raises():
    """RuntimeError if Gemini returns empty/None (safety filters / policy)."""
    from better_code_review_graph.summarizer import summarize_node

    mock_resp = MagicMock()
    mock_resp.text = ""  # Blocked by safety filter often returns empty

    with patch("better_code_review_graph.summarizer._get_gemini_client") as mock_get:
        mock_get.return_value.models.generate_content.return_value = mock_resp
        with pytest.raises(RuntimeError, match="gemini returned empty/None text"):
            summarize_node(MagicMock(), provider="gemini", api_key="k")

    mock_resp.text = None
    with patch("better_code_review_graph.summarizer._get_gemini_client") as mock_get:
        mock_get.return_value.models.generate_content.return_value = mock_resp
        with pytest.raises(RuntimeError, match="gemini returned empty/None text"):
            summarize_node(MagicMock(), provider="gemini", api_key="k")


def test_summarize_node_openai_no_choices_raises():
    """RuntimeError if OpenAI returns no choices."""
    from better_code_review_graph.summarizer import summarize_node

    mock_resp = MagicMock()
    mock_resp.choices = []

    with patch("better_code_review_graph.summarizer._get_openai_client") as mock_get:
        mock_get.return_value.chat.completions.create.return_value = mock_resp
        with pytest.raises(RuntimeError, match="openai returned no choices"):
            summarize_node(MagicMock(), provider="openai", api_key="k")


def test_summarize_node_openai_none_content_raises():
    """RuntimeError if OpenAI choice content is None."""
    from better_code_review_graph.summarizer import summarize_node

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    with patch("better_code_review_graph.summarizer._get_openai_client") as mock_get:
        mock_get.return_value.chat.completions.create.return_value = mock_resp
        with pytest.raises(RuntimeError, match="openai returned empty/None content"):
            summarize_node(MagicMock(), provider="openai", api_key="k")


def test_summarize_node_provider_is_case_sensitive():
    """Provider must be exact lowercase 'gemini' or 'openai'."""
    from better_code_review_graph.summarizer import summarize_node

    with pytest.raises(ValueError):
        summarize_node(MagicMock(), provider="Gemini", api_key="k")


def test_summarize_node_handles_braces_in_source():
    """Verify that source containing { } does not break the prompt via format() etc."""
    from better_code_review_graph.summarizer import NodeNeedingSummary, summarize_node

    node = NodeNeedingSummary(
        node_id="1", source_text="def f(): return {'x': 1}", source_hash="h"
    )
    mock_resp = MagicMock()
    mock_resp.text = "Summary."

    with patch("better_code_review_graph.summarizer._get_gemini_client") as mock_get:
        mock_get.return_value.models.generate_content.return_value = mock_resp
        # This call must NOT raise KeyError or IndexError
        summarize_node(node, provider="gemini", api_key="k")


def test_get_gemini_client_constructs_with_api_key():
    """Deferred import and constructor call."""
    from better_code_review_graph.summarizer import _get_gemini_client

    with patch("google.genai.Client") as mock_cls:
        _get_gemini_client("key-123")
        mock_cls.assert_called_once_with(api_key="key-123")


def test_get_openai_client_constructs_with_api_key():
    """Deferred import and constructor call."""
    from better_code_review_graph.summarizer import _get_openai_client

    with patch("openai.OpenAI") as mock_cls:
        _get_openai_client("key-abc")
        mock_cls.assert_called_once_with(api_key="key-abc")


def test_summarize_node_openai_create_failure_wraps_runtimeerror():
    """Specific regression for Task 5 error-count wiring."""
    from better_code_review_graph.summarizer import NodeNeedingSummary, summarize_node

    node = NodeNeedingSummary(node_id="1", source_text="s", source_hash="h")
    with patch("better_code_review_graph.summarizer._get_openai_client") as mock_get:
        mock_get.return_value.chat.completions.create.side_effect = Exception("err")
        with pytest.raises(RuntimeError, match="summarize_node failed via openai"):
            summarize_node(node, provider="openai", api_key="k")


# ---------------------------------------------------------------------------
# update_summary + batch_summarize (Task 5)
# ---------------------------------------------------------------------------


def test_update_summary_persists_to_db(tmp_path):
    """Direct functional verification for GraphStore.update_summary."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        node_id = store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="h",
        )
        # Initially null
        row = store._conn.execute(
            "SELECT summary, summary_provider, source_hash FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] is None

        store.update_summary(
            node_id,
            summary="New summary.",
            provider="gemini",
            source_hash="source_hash_abc",
        )

        row = store._conn.execute(
            "SELECT summary, summary_provider, source_hash FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "New summary."
        assert row[1] == "gemini"
        assert row[2] == "source_hash_abc"
    finally:
        store.close()


def test_batch_summarize_skips_when_no_provider(tmp_path, monkeypatch):
    """Without env vars set, batch_summarize returns skipped_no_provider=True without calling LLM."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.summarizer import batch_summarize

    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        result = batch_summarize(store, max_nodes=10)
        assert result.skipped_no_provider is True
        assert result.provider is None
    finally:
        store.close()


def test_batch_summarize_generates_for_uncached_nodes(tmp_path, monkeypatch):
    """If no summary stored, generate and persist."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize, compute_source_hash

    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        node_id = store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="h",
        )
        # Must have source_text to be a candidate
        store._conn.execute(
            "UPDATE nodes SET source_text=? WHERE id=?",
            ("def f(): return 1", node_id),
        )
        store._conn.commit()

        with patch("better_code_review_graph.summarizer.summarize_node") as mock_sum:
            mock_sum.return_value = "Generated summary."
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.cached == 0
        assert result.provider == "gemini"

        # Verify persistence
        row = store._conn.execute(
            "SELECT summary, source_hash FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "Generated summary."
        assert row[1] == compute_source_hash("def f(): return 1")
    finally:
        store.close()


def test_batch_summarize_cache_hit_when_hash_and_provider_match(tmp_path, monkeypatch):
    """If stored summary + hash + provider match live, skip LLM call."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize, compute_source_hash

    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        src = "def f(): return 1"
        node_id = store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="h",
        )
        # Store a matching cache entry
        store._conn.execute(
            "UPDATE nodes SET source_text=?, summary=?, summary_provider=?, source_hash=? WHERE id=?",
            (src, "Cached summary.", "gemini", compute_source_hash(src), node_id),
        )
        store._conn.commit()

        with patch("better_code_review_graph.summarizer.summarize_node") as mock_sum:
            result = batch_summarize(store, max_nodes=10)

        assert result.cached == 1
        assert result.generated == 0
        mock_sum.assert_not_called()
    finally:
        store.close()


def test_batch_summarize_regenerates_when_source_changed(tmp_path, monkeypatch):
    """If stored hash != live hash, treat as stale and regenerate."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize

    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        node_id = store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="h",
        )
        # Stored summary corresponds to OLD source; live source is new
        store._conn.execute(
            "UPDATE nodes SET source_text=?, summary=?, summary_provider=?, source_hash=? WHERE id=?",
            (
                "def f(): return 2",
                "Old summary for return 1.",
                "gemini",
                "stale_hash",
                node_id,
            ),
        )
        store._conn.commit()

        with patch("better_code_review_graph.summarizer.summarize_node") as mock_sum:
            mock_sum.return_value = "Returns 2."
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.cached == 0
        # Verify summary updated
        row = store._conn.execute(
            "SELECT summary FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "Returns 2."
    finally:
        store.close()


def test_batch_summarize_respects_max_nodes_cap(tmp_path, monkeypatch):
    """max_nodes=2 with 5 candidate nodes should generate at most 2."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize

    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        for i in range(5):
            nid = store.upsert_node(
                NodeInfo(
                    kind="Function",
                    name=f"f{i}",
                    file_path="x.py",
                    line_start=i,
                    line_end=i + 1,
                    language="python",
                ),
                file_hash="h",
            )
            store._conn.execute(
                "UPDATE nodes SET source_text=? WHERE id=?",
                (f"def f{i}(): return {i}", nid),
            )
        store._conn.commit()

        with patch("better_code_review_graph.summarizer.summarize_node") as mock_sum:
            mock_sum.return_value = "Stub."
            result = batch_summarize(store, max_nodes=2)

        assert result.generated == 2
        assert mock_sum.call_count == 2
    finally:
        store.close()


def test_batch_summarize_continues_after_per_node_error(tmp_path, monkeypatch):
    """If summarize_node raises for one node, batch should count error + continue with others."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize

    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        for i in range(3):
            nid = store.upsert_node(
                NodeInfo(
                    kind="Function",
                    name=f"f{i}",
                    file_path="x.py",
                    line_start=i,
                    line_end=i + 1,
                    language="python",
                ),
                file_hash="h",
            )
            store._conn.execute(
                "UPDATE nodes SET source_text=? WHERE id=?",
                (f"def f{i}(): return {i}", nid),
            )
        store._conn.commit()

        # 2nd call raises, 1st + 3rd succeed
        side_effects = ["First.", RuntimeError("boom"), "Third."]
        with patch(
            "better_code_review_graph.summarizer.summarize_node",
            side_effect=side_effects,
        ) as mock_sum:
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 2
        assert result.errors == 1
        assert mock_sum.call_count == 3

        # Lock per-node persistence: nodes 0 + 2 must have summaries; node 1 (raised) must not.
        rows = store._conn.execute(
            "SELECT id, summary FROM nodes WHERE kind='Function' ORDER BY id"
        ).fetchall()
        # Map by row order (node creation order matches row id order in this test).
        summaries = [(r[1] is not None, r[1]) for r in rows]
        # Node 0 (1st call): "First."
        # Node 1 (2nd call): RAISED -> no persist
        # Node 2 (3rd call): "Third."
        assert summaries[0] == (
            True,
            "First.",
        ), f"Node 0 should have summary 'First.', got {summaries[0]}"
        assert summaries[1] == (
            False,
            None,
        ), f"Node 1 should have no summary (error), got {summaries[1]}"
        assert summaries[2] == (
            True,
            "Third.",
        ), f"Node 2 should have summary 'Third.', got {summaries[2]}"
    finally:
        store.close()


def test_batch_summarize_treats_empty_string_summary_as_cache_miss(
    tmp_path, monkeypatch
):
    """Empty-string stored_summary should be treated as 'no summary' and trigger regeneration.

    Locks the if stored_summary and ... truthiness contract in
    batch_summarize: even if hash + provider match, a stored empty
    string is NOT a valid cached summary and must be regenerated.
    """
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize, compute_source_hash

    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        src = "def f(): return 1"
        node_id = store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="h",
        )
        # Stored summary is empty string, hash + provider would otherwise match.
        store._conn.execute(
            "UPDATE nodes SET source_text=?, summary=?, summary_provider=?, source_hash=? WHERE id=?",
            (src, "", "gemini", compute_source_hash(src), node_id),
        )
        store._conn.commit()

        with patch("better_code_review_graph.summarizer.summarize_node") as mock_sum:
            mock_sum.return_value = "Returns 1."
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1, "Empty-string summary should NOT be a cache hit"
        assert result.cached == 0
        mock_sum.assert_called_once()
        # Verify regeneration persisted.
        row = store._conn.execute(
            "SELECT summary FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "Returns 1."
    finally:
        store.close()


def test_batch_summarize_invalid_max_nodes_raises():
    """max_nodes <= 0 should raise ValueError before any DB query."""
    from better_code_review_graph.summarizer import batch_summarize

    with pytest.raises(ValueError, match="max_nodes must be"):
        batch_summarize(MagicMock(), max_nodes=0)
    with pytest.raises(ValueError, match="max_nodes must be"):
        batch_summarize(MagicMock(), max_nodes=-1)


def test_batch_summarize_skips_non_function_nodes(tmp_path, monkeypatch):
    """Class/Type/Test nodes are not summarized — kind='Function' filter."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize

    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        for kind in ("Class", "Type", "Test"):
            nid = store.upsert_node(
                NodeInfo(
                    kind=kind,
                    name=f"{kind}_x",
                    file_path="x.py",
                    line_start=1,
                    line_end=2,
                    language="python",
                ),
                file_hash="h",
            )
            store._conn.execute(
                "UPDATE nodes SET source_text=? WHERE id=?",
                ("class X: pass", nid),
            )
        store._conn.commit()

        with patch("better_code_review_graph.summarizer.summarize_node") as mock_sum:
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 0
        mock_sum.assert_not_called()
    finally:
        store.close()


def test_batch_summarize_error_logging(tmp_path, monkeypatch, caplog):
    """Verify that summarize_node failures are logged as warnings with node ID."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize

    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        nid = store.upsert_node(
            NodeInfo(
                kind="Function",
                name="fail_func",
                file_path="fail.py",
                line_start=10,
                line_end=12,
                language="python",
            ),
            file_hash="h",
        )
        store._conn.execute(
            "UPDATE nodes SET source_text=? WHERE id=?",
            ("def fail_func(): pass", nid),
        )
        store._conn.commit()

        # Clear logs from migrations/setup to avoid noise
        caplog.clear()
        with caplog.at_level(
            logging.WARNING, logger="better_code_review_graph.summarizer"
        ):
            with patch(
                "better_code_review_graph.summarizer.summarize_node",
                side_effect=RuntimeError("simulated failure"),
            ):
                result = batch_summarize(store, max_nodes=1)

        assert result.errors == 1
        # Check records directly for more robust assertion
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("summarize_node failed for id=" in w.message for w in warnings)
        assert any(str(nid) in w.message for w in warnings)
        assert any("simulated failure" in w.message for w in warnings)
    finally:
        store.close()
