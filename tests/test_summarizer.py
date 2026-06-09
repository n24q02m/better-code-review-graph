"""Tests for the LLM summary cache + provider helpers (Phase 1 v1.6.x).

Covers ``better_code_review_graph.summarizer`` -- hash derivation,
cache-key composition, provider auto-detection from environment
variables, and the single-node ``summarize_node`` LLM call (Gemini /
OpenAI paths, error wrapping, unknown-provider validation). All LLM
client interactions are mocked via ``unittest.mock.patch`` against the
private ``_get_gemini_client`` / ``_get_openai_client`` helpers, so no
network traffic is generated. Batch + cache-lookup wiring lives in
Task 5.
"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.summarizer import (
    NodeNeedingSummary,
    compute_source_hash,
    compute_summary_cache_key,
    resolve_summary_provider,
    summarize_node,
)

# ---------------------------------------------------------------------------
# Hash + cache key
# ---------------------------------------------------------------------------


def test_compute_source_hash_empty_string():
    """Empty or None input must produce empty string -- drift-bug prevention."""
    assert compute_source_hash("") == ""
    assert compute_source_hash(None) == ""


def test_compute_source_hash_standard_string():
    """Matches SHA-256 of UTF-8 encoded bytes for non-empty strings."""
    src = "def f(): return 1"
    expected = hashlib.sha256(src.encode("utf-8")).hexdigest()
    assert compute_source_hash(src) == expected


def test_compute_summary_cache_key_trusts_precomputed_hash():
    """If NodeNeedingSummary has source_hash, we use it verbatim without re-hashing."""
    node = NodeNeedingSummary(
        node_id="f.py::f",
        source_text="ignored",
        source_hash="precomputed-sha256",
    )
    key = compute_summary_cache_key(node, "gemini")
    assert key == "precomputed-sha256:gemini"


def test_compute_summary_cache_key_hashes_on_demand():
    """If source_hash is None, we compute it from source_text."""
    src = "def f(): return 1"
    node = NodeNeedingSummary(node_id="f.py::f", source_text=src, source_hash=None)
    expected_hash = hashlib.sha256(src.encode("utf-8")).hexdigest()

    key = compute_summary_cache_key(node, "openai")
    assert key == f"{expected_hash}:openai"


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def test_resolve_summary_provider_gemini_wins(monkeypatch):
    """GEMINI_API_KEY takes precedence over OPENAI_API_KEY."""
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")

    res = resolve_summary_provider()
    assert res == ("gemini", "g-key")


def test_resolve_summary_provider_google_alias(monkeypatch):
    """GOOGLE_API_KEY is treated as a Gemini alias."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

    res = resolve_summary_provider()
    assert res == ("gemini", "google-key")


def test_resolve_summary_provider_openai_fallback(monkeypatch):
    """If no Gemini/Google keys, OpenAI is used."""
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")

    res = resolve_summary_provider()
    assert res == ("openai", "o-key")


def test_resolve_summary_provider_none_when_all_missing(monkeypatch):
    """Returns None if no supported provider key is set."""
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    assert resolve_summary_provider() is None


def test_resolve_summary_provider_treats_empty_as_unset(monkeypatch):
    """Empty strings in env vars are treated as not set."""
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")

    res = resolve_summary_provider()
    assert res == ("openai", "o-key")


# ---------------------------------------------------------------------------
# summarize_node (Gemini path)
# ---------------------------------------------------------------------------


def test_summarize_node_gemini_success():
    """Verifies Gemini client interaction and response stripping."""
    node = NodeNeedingSummary(node_id="x", source_text="def f(): pass", source_hash="h")

    # Mock the client returned by _get_gemini_client
    mock_client = MagicMock()
    # response.text
    mock_client.models.generate_content.return_value.text = "  A function.  "

    with patch(
        "better_code_review_graph.summarizer._get_gemini_client",
        return_value=mock_client,
    ):
        summary = summarize_node(node, provider="gemini", api_key="abc")

    assert summary == "A function."
    # Check args: model and prompt concatenation
    args, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-2.5-flash"
    assert "def f(): pass" in kwargs["contents"]


def test_summarize_node_gemini_error_wrapping():
    """If SDK raises, we wrap in RuntimeError."""
    node = NodeNeedingSummary(node_id="x", source_text="src", source_hash="h")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = ValueError("Safety block")

    with patch(
        "better_code_review_graph.summarizer._get_gemini_client",
        return_value=mock_client,
    ):
        with pytest.raises(RuntimeError, match="summarize_node failed via gemini"):
            summarize_node(node, provider="gemini", api_key="abc")


def test_summarize_node_gemini_empty_response_raises():
    """Gemini returning None/empty text (e.g. filter) should raise RuntimeError."""
    node = NodeNeedingSummary(node_id="x", source_text="src", source_hash="h")
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value.text = ""

    with patch(
        "better_code_review_graph.summarizer._get_gemini_client",
        return_value=mock_client,
    ):
        with pytest.raises(RuntimeError, match="gemini returned empty/None text"):
            summarize_node(node, provider="gemini", api_key="abc")


# ---------------------------------------------------------------------------
# summarize_node (OpenAI path)
# ---------------------------------------------------------------------------


def test_summarize_node_openai_success():
    """Verifies OpenAI client interaction and response stripping."""
    node = NodeNeedingSummary(node_id="x", source_text="def f(): pass", source_hash="h")

    mock_client = MagicMock()
    # response.choices[0].message.content
    mock_choice = MagicMock()
    mock_choice.message.content = "  OpenAI summary. \n "
    mock_client.chat.completions.create.return_value.choices = [mock_choice]

    with patch(
        "better_code_review_graph.summarizer._get_openai_client",
        return_value=mock_client,
    ):
        summary = summarize_node(node, provider="openai", api_key="abc")

    assert summary == "OpenAI summary."
    # Check args
    args, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["messages"][0]["content"].endswith("def f(): pass")


def test_summarize_node_openai_empty_choices_raises():
    """OpenAI returning empty choices list should raise RuntimeError."""
    node = NodeNeedingSummary(node_id="x", source_text="src", source_hash="h")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = []

    with patch(
        "better_code_review_graph.summarizer._get_openai_client",
        return_value=mock_client,
    ):
        with pytest.raises(RuntimeError, match="openai returned no choices"):
            summarize_node(node, provider="openai", api_key="abc")


# ---------------------------------------------------------------------------
# summarize_node (Validation)
# ---------------------------------------------------------------------------


def test_summarize_node_unsupported_provider():
    """Must raise ValueError for non-gemini/openai providers."""
    node = NodeNeedingSummary(node_id="x", source_text="src", source_hash="h")
    with pytest.raises(ValueError, match="Unsupported provider: 'claude'"):
        summarize_node(node, provider="claude", api_key="abc")


# ---------------------------------------------------------------------------
# Batch orchestration (Task 5)
# ---------------------------------------------------------------------------


def test_batch_summarize_skips_when_no_provider(tmp_path, monkeypatch):
    """If no API key is set, batch_summarize returns early with skipped_no_provider=True."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.summarizer import batch_summarize

    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        result = batch_summarize(store)
        assert result.skipped_no_provider is True
        assert result.provider is None
    finally:
        store.close()


def test_batch_summarize_processes_new_nodes(tmp_path, monkeypatch):
    """Freshly inserted Function nodes with source_text should be summarized and persisted."""
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
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="h",
        )
        # Manually set source_text since upsert_node logic might be skipped/simplified in mocks
        store._conn.execute(
            "UPDATE nodes SET source_text=? WHERE id=?",
            ("def f(): return 1", nid),
        )
        store._conn.commit()

        with patch("better_code_review_graph.summarizer.summarize_node") as mock_sum:
            mock_sum.return_value = "Generated summary."
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.cached == 0
        assert result.provider == "gemini"

        # Verify DB update
        row = store._conn.execute(
            "SELECT summary, summary_provider, source_hash FROM nodes WHERE id=?",
            (nid,),
        ).fetchone()
        assert row[0] == "Generated summary."
        assert row[1] == "gemini"
        # source_hash must be set
        assert row[2] is not None
    finally:
        store.close()


def test_batch_summarize_cache_hit_skips_regeneration(tmp_path, monkeypatch):
    """If summary + hash + provider already match, skip API call."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize

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
        # Pre-seed cached summary
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

    Locks the ``if stored_summary and ...`` truthiness contract in
    ``batch_summarize``: even if hash + provider match, a stored empty
    string is NOT a valid cached summary and must be regenerated.
    """
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize

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


def test_batch_summarize_detect_empty_string_as_cached(tmp_path, monkeypatch):
    """Empty string hashing fix prevents drift between temporal and summarizer.

    Temporal Index uses "" for empty source hash. Summarizer must also use ""
    (via fixed compute_source_hash) so that cache hits work for empty functions.
    """
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize

    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        src = ""
        node_id = store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=1,
                language="python",
                source_text=src,
            ),
            file_hash="h",
        )
        # Simulate temporal index storing "" as hash
        store._conn.execute(
            "UPDATE nodes SET summary=?, summary_provider=?, source_hash=? WHERE id=?",
            ("Existing summary.", "gemini", "", node_id),
        )
        store._conn.commit()

        with patch("better_code_review_graph.summarizer.summarize_node") as mock_sum:
            result = batch_summarize(store, max_nodes=10)

        assert result.cached == 1
        assert result.generated == 0
        mock_sum.assert_not_called()
    finally:
        store.close()
