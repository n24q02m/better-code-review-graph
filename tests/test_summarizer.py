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

import dataclasses
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


def test_compute_source_hash_is_sha256():
    source = "def add(a, b):\n    return a + b\n"
    expected = hashlib.sha256(source.encode("utf-8")).hexdigest()
    actual = compute_source_hash(source)

    # SHA-256 hex digest is 64 lowercase hex chars.
    assert len(actual) == 64
    assert all(c in "0123456789abcdef" for c in actual)
    assert actual == expected


def test_compute_source_hash_empty_string():
    """Empty input must produce sha256 of empty bytes -- well-defined contract."""
    assert (
        compute_source_hash("")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_compute_source_hash_handles_unicode():
    """Unicode source code (non-ASCII) must hash via UTF-8 encoding."""
    src = "def greet(): return 'café'"
    expected = hashlib.sha256(src.encode("utf-8")).hexdigest()
    assert compute_source_hash(src) == expected
    # Also verify it's not the latin-1 hash (which would be different)
    assert compute_source_hash(src) != hashlib.sha256(src.encode("latin-1")).hexdigest()


def test_node_needing_summary_is_frozen():
    """NodeNeedingSummary must be immutable for safe use as cache key input."""
    node = NodeNeedingSummary(node_id="x", source_text="y", source_hash=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.node_id = "z"  # ty: ignore[invalid-assignment]


def test_cache_key_combines_source_hash_and_provider():
    source = "def add(a, b):\n    return a + b\n"
    expected_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()

    node = NodeNeedingSummary(
        node_id="src/x.py::add",
        source_text=source,
        source_hash=None,
    )
    key = compute_summary_cache_key(node, "gemini")

    assert key == f"{expected_hash}:gemini"


def test_cache_key_changes_when_provider_changes():
    source = "def add(a, b):\n    return a + b\n"
    node = NodeNeedingSummary(
        node_id="src/x.py::add",
        source_text=source,
        source_hash=None,
    )
    gemini_key = compute_summary_cache_key(node, "gemini")
    openai_key = compute_summary_cache_key(node, "openai")

    assert gemini_key != openai_key
    # Both must end with the provider tag and share the same hash prefix.
    assert gemini_key.endswith(":gemini")
    assert openai_key.endswith(":openai")
    assert gemini_key.split(":", 1)[0] == openai_key.split(":", 1)[0]


def test_cache_key_uses_precomputed_hash_when_provided():
    """When ``source_hash`` is set the cache key MUST trust it verbatim.

    We pass a fake hash that does NOT match the source text; the key must
    still embed the fake hash, proving no recomputation occurred.
    """
    fake_hash = "deadbeef" * 8  # 64 hex chars, intentionally wrong
    node = NodeNeedingSummary(
        node_id="src/x.py::add",
        source_text="def add(a, b):\n    return a + b\n",
        source_hash=fake_hash,
    )
    key = compute_summary_cache_key(node, "gemini")

    assert key == f"{fake_hash}:gemini"


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def _clear_provider_env(monkeypatch):
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_resolve_provider_prefers_gemini(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")

    result = resolve_summary_provider()

    assert result == ("gemini", "g-key")


def test_resolve_provider_falls_back_to_openai(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")

    result = resolve_summary_provider()

    assert result == ("openai", "o-key")


def test_resolve_provider_handles_google_api_key_alias(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

    result = resolve_summary_provider()

    assert result == ("gemini", "google-key")


def test_resolve_provider_returns_none_when_no_key(monkeypatch):
    _clear_provider_env(monkeypatch)

    result = resolve_summary_provider()

    assert result is None


def test_resolve_provider_empty_gemini_falls_through_to_google(monkeypatch):
    """Empty GEMINI_API_KEY should fall through to GOOGLE_API_KEY (per docstring contract)."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    assert resolve_summary_provider() == ("gemini", "google-key")


def test_resolve_provider_all_empty_returns_none(monkeypatch):
    """All env vars set to empty strings should be treated as unset."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert resolve_summary_provider() is None


# ---------------------------------------------------------------------------
# summarize_node (single-node LLM summary)
# ---------------------------------------------------------------------------


def _completion_resp(content):
    """Build a fake mcp_core.llm.completion response (OpenAI-shaped)."""
    fake_choice = MagicMock()
    fake_choice.message.content = content
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    return fake_response


def test_summarize_node_gemini_returns_text(monkeypatch):
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)
    node = NodeNeedingSummary(
        node_id="x.py::foo", source_text="def foo(): pass", source_hash=None
    )
    # Whitespace must be stripped.
    fake_response = _completion_resp("  Returns nothing — placeholder function.  ")
    with patch(
        "mcp_core.llm.completion", return_value=fake_response
    ) as mock_completion:
        result = summarize_node(node, provider="gemini", api_key="g-key")
    assert result == "Returns nothing — placeholder function."
    mock_completion.assert_called_once()
    call_kwargs = mock_completion.call_args.kwargs
    # Default gemini model used when SUMMARY_MODEL unset.
    assert call_kwargs["model"] == "gemini/gemini-2.5-flash"
    assert call_kwargs["messages"][0]["role"] == "user"
    assert "def foo(): pass" in call_kwargs["messages"][0]["content"]
    assert call_kwargs["api_key"] == "g-key"
    # No LLM_API_BASE set -> normalised to None.
    assert call_kwargs["api_base"] is None


def test_summarize_node_openai_returns_text(monkeypatch):
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)
    node = NodeNeedingSummary(
        node_id="x.py::bar", source_text="def bar(): pass", source_hash=None
    )
    fake_response = _completion_resp("\nEmpty stub function.\n")
    with patch(
        "mcp_core.llm.completion", return_value=fake_response
    ) as mock_completion:
        result = summarize_node(node, provider="openai", api_key="o-key")
    assert result == "Empty stub function."
    call_kwargs = mock_completion.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["messages"][0]["role"] == "user"


def test_summarize_node_uses_summary_model_override(monkeypatch):
    """SUMMARY_MODEL env, when set, is used verbatim regardless of provider."""
    monkeypatch.setenv("SUMMARY_MODEL", "openai/gpt-5-mini")
    node = NodeNeedingSummary(
        node_id="x.py::foo", source_text="def foo(): pass", source_hash=None
    )
    fake_response = _completion_resp("A summary.")
    with patch(
        "mcp_core.llm.completion", return_value=fake_response
    ) as mock_completion:
        # provider is "gemini" but override forces the openai model.
        result = summarize_node(node, provider="gemini", api_key="key")
    assert result == "A summary."
    assert mock_completion.call_args.kwargs["model"] == "openai/gpt-5-mini"


def test_summarize_node_forwards_llm_api_base(monkeypatch):
    """LLM_API_BASE env is forwarded as api_base."""
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)
    monkeypatch.setenv("LLM_API_BASE", "https://proxy.example/v1")
    node = NodeNeedingSummary(node_id="x", source_text="y", source_hash=None)
    with patch(
        "mcp_core.llm.completion", return_value=_completion_resp("ok")
    ) as mock_completion:
        summarize_node(node, provider="openai", api_key="o-key")
    assert mock_completion.call_args.kwargs["api_base"] == "https://proxy.example/v1"


def test_summarize_node_unknown_provider_raises():
    node = NodeNeedingSummary(node_id="x", source_text="y", source_hash=None)
    with pytest.raises(ValueError, match="Unsupported provider"):
        summarize_node(node, provider="anthropic", api_key="k")


def test_summarize_node_wraps_llm_errors(monkeypatch):
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)
    node = NodeNeedingSummary(node_id="x", source_text="y", source_hash=None)
    with patch("mcp_core.llm.completion", side_effect=Exception("API timeout")):
        with pytest.raises(RuntimeError, match="summarize_node failed via gemini"):
            summarize_node(node, provider="gemini", api_key="g-key")


def test_summarize_node_no_choices_raises(monkeypatch):
    """litellm ``response.choices=[]`` must raise RuntimeError 'no choices' directly."""
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)
    node = NodeNeedingSummary(
        node_id="x.py::bar", source_text="def bar(): pass", source_hash=None
    )
    fake_response = MagicMock()
    fake_response.choices = []
    with patch("mcp_core.llm.completion", return_value=fake_response):
        with pytest.raises(RuntimeError, match="no choices") as exc_info:
            summarize_node(node, provider="openai", api_key="o-key")
    assert "summarize_node failed via openai" not in str(exc_info.value)
    assert "x.py::bar" in str(exc_info.value)


def test_summarize_node_none_content_raises(monkeypatch):
    """litellm ``message.content=None`` (safety filter) must raise 'empty/None content'."""
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)
    node = NodeNeedingSummary(
        node_id="x.py::baz", source_text="def baz(): pass", source_hash=None
    )
    fake_response = _completion_resp(None)
    with patch("mcp_core.llm.completion", return_value=fake_response):
        with pytest.raises(RuntimeError, match="empty/None content") as exc_info:
            summarize_node(node, provider="gemini", api_key="g-key")
    assert "summarize_node failed via gemini" not in str(exc_info.value)
    assert "x.py::baz" in str(exc_info.value)


def test_summarize_node_provider_is_case_sensitive():
    """provider arg must match the lowercase canonical form returned by resolve_summary_provider."""
    node = NodeNeedingSummary(node_id="x", source_text="y", source_hash=None)
    with pytest.raises(ValueError, match="Unsupported provider: 'Gemini'"):
        summarize_node(node, provider="Gemini", api_key="k")


def test_summarize_node_handles_braces_in_source(monkeypatch):
    """Function source containing { } (dict literals, f-strings) must not break prompt construction."""
    monkeypatch.delenv("SUMMARY_MODEL", raising=False)
    src = 'def make_d(): return {"a": f"{x}"}'  # dict literal + f-string
    node = NodeNeedingSummary(node_id="x", source_text=src, source_hash=None)
    fake_response = _completion_resp("Returns a dict.")
    with patch(
        "mcp_core.llm.completion", return_value=fake_response
    ) as mock_completion:
        result = summarize_node(node, provider="gemini", api_key="k")
    assert result == "Returns a dict."
    # Verify the source went verbatim into the prompt
    assert src in mock_completion.call_args.kwargs["messages"][0]["content"]


# ---------------------------------------------------------------------------
# _provider_from_model (cache-key provider derivation)
# ---------------------------------------------------------------------------


def test_provider_from_model_derives_prefix():
    from better_code_review_graph.summarizer import _provider_from_model

    assert _provider_from_model("gemini/gemini-2.5-flash") == "gemini"
    assert _provider_from_model("google/gemini-pro") == "gemini"
    assert _provider_from_model("openai/gpt-4o-mini") == "openai"
    assert _provider_from_model("gpt/gpt-4o") == "openai"
    # Bare OpenAI-style name -> openai default.
    assert _provider_from_model("gpt-4o-mini") == "openai"
    # Unknown prefix is passed through verbatim.
    assert _provider_from_model("cohere/command-r") == "cohere"


# ---------------------------------------------------------------------------
# update_summary + batch_summarize (Task 5)
# ---------------------------------------------------------------------------


def test_update_summary_persists_to_db(tmp_path):
    """GraphStore.update_summary should write summary + provider + source_hash atomically."""
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
        store.update_summary(
            node_id, summary="A summary.", provider="gemini", source_hash="abc123"
        )
        row = store._conn.execute(
            "SELECT summary, summary_provider, source_hash FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "A summary."
        assert row[1] == "gemini"
        assert row[2] == "abc123"
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
        assert result.generated == 0
        assert result.cached == 0
        assert result.provider is None
    finally:
        store.close()


def test_batch_summarize_generates_for_uncached_nodes(tmp_path, monkeypatch):
    """Function nodes without summary should be sent to LLM and result persisted."""
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
        # Set source_text directly since NodeInfo doesn't carry it
        store._conn.execute(
            "UPDATE nodes SET source_text=? WHERE id=?",
            ("def f(): return 1", node_id),
        )
        store._conn.commit()

        with patch("better_code_review_graph.summarizer.summarize_node") as mock_sum:
            mock_sum.return_value = "Returns 1."
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.cached == 0
        assert result.provider == "gemini"
        # Verify persisted
        row = store._conn.execute(
            "SELECT summary, summary_provider, source_hash FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "Returns 1."
        assert row[1] == "gemini"
        assert row[2] == compute_source_hash("def f(): return 1")
    finally:
        store.close()


def test_batch_summarize_cache_hit_when_hash_and_provider_match(tmp_path, monkeypatch):
    """Pre-existing summary + matching source_hash + matching provider => cache hit, no LLM call."""
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


def test_batch_summarize_cache_provider_from_summary_model(tmp_path, monkeypatch):
    """With SUMMARY_MODEL set, the cache tag is derived from the model prefix.

    Env-resolved provider is 'gemini' (GEMINI_API_KEY) but SUMMARY_MODEL points
    at an OpenAI model, so the persisted ``summary_provider`` + result.provider
    must be 'openai' (derived from the prefix), invalidating any gemini-tagged
    cache entry.
    """
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo
    from better_code_review_graph.summarizer import batch_summarize, compute_source_hash

    for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("SUMMARY_MODEL", "openai/gpt-4o-mini")

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
        # Pre-existing gemini-tagged summary: must NOT be a cache hit under the
        # openai-derived tag, so it regenerates.
        store._conn.execute(
            "UPDATE nodes SET source_text=?, summary=?, summary_provider=?, source_hash=? WHERE id=?",
            (src, "Old gemini summary.", "gemini", compute_source_hash(src), node_id),
        )
        store._conn.commit()

        with patch("better_code_review_graph.summarizer.summarize_node") as mock_sum:
            mock_sum.return_value = "New summary."
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.cached == 0
        assert result.provider == "openai"
        row = store._conn.execute(
            "SELECT summary, summary_provider FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "New summary."
        assert row[1] == "openai"
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
