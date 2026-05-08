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
        node.node_id = "z"  # type: ignore[misc]


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


def test_summarize_node_gemini_returns_text():
    node = NodeNeedingSummary(
        node_id="x.py::foo", source_text="def foo(): pass", source_hash=None
    )
    fake_response = MagicMock()
    fake_response.text = (
        "  Returns nothing — placeholder function.  "  # whitespace must be stripped
    )
    with patch("better_code_review_graph.summarizer._get_gemini_client") as mock_get:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response
        mock_get.return_value = mock_client
        result = summarize_node(node, provider="gemini", api_key="g-key")
    assert result == "Returns nothing — placeholder function."
    mock_get.assert_called_once_with("g-key")
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash"
    assert "def foo(): pass" in call_kwargs["contents"]


def test_summarize_node_openai_returns_text():
    node = NodeNeedingSummary(
        node_id="x.py::bar", source_text="def bar(): pass", source_hash=None
    )
    fake_choice = MagicMock()
    fake_choice.message.content = "\nEmpty stub function.\n"
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    with patch("better_code_review_graph.summarizer._get_openai_client") as mock_get:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_response
        mock_get.return_value = mock_client
        result = summarize_node(node, provider="openai", api_key="o-key")
    assert result == "Empty stub function."
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["messages"][0]["role"] == "user"


def test_summarize_node_unknown_provider_raises():
    node = NodeNeedingSummary(node_id="x", source_text="y", source_hash=None)
    with pytest.raises(ValueError, match="Unsupported provider"):
        summarize_node(node, provider="anthropic", api_key="k")


def test_summarize_node_wraps_sdk_errors():
    node = NodeNeedingSummary(node_id="x", source_text="y", source_hash=None)
    with patch("better_code_review_graph.summarizer._get_gemini_client") as mock_get:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API timeout")
        mock_get.return_value = mock_client
        with pytest.raises(RuntimeError, match="summarize_node failed via gemini"):
            summarize_node(node, provider="gemini", api_key="g-key")


def test_summarize_node_gemini_empty_text_raises():
    """Gemini ``response.text=None`` (safety filter) must raise RuntimeError directly,
    NOT wrapped as 'summarize_node failed via gemini: ...'.
    """
    node = NodeNeedingSummary(
        node_id="x.py::foo", source_text="def foo(): pass", source_hash=None
    )
    fake_response = MagicMock()
    fake_response.text = None
    with patch("better_code_review_graph.summarizer._get_gemini_client") as mock_get:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response
        mock_get.return_value = mock_client
        with pytest.raises(RuntimeError, match="empty/None text") as exc_info:
            summarize_node(node, provider="gemini", api_key="g-key")
    # Must be the explicit guard, not the SDK-wrapping path.
    assert "summarize_node failed via gemini" not in str(exc_info.value)
    assert "x.py::foo" in str(exc_info.value)


def test_summarize_node_openai_no_choices_raises():
    """OpenAI ``response.choices=[]`` must raise RuntimeError 'no choices' directly."""
    node = NodeNeedingSummary(
        node_id="x.py::bar", source_text="def bar(): pass", source_hash=None
    )
    fake_response = MagicMock()
    fake_response.choices = []
    with patch("better_code_review_graph.summarizer._get_openai_client") as mock_get:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_response
        mock_get.return_value = mock_client
        with pytest.raises(RuntimeError, match="no choices") as exc_info:
            summarize_node(node, provider="openai", api_key="o-key")
    assert "summarize_node failed via openai" not in str(exc_info.value)
    assert "x.py::bar" in str(exc_info.value)


def test_summarize_node_openai_none_content_raises():
    """OpenAI ``message.content=None`` (safety filter) must raise RuntimeError 'empty/None content'."""
    node = NodeNeedingSummary(
        node_id="x.py::baz", source_text="def baz(): pass", source_hash=None
    )
    fake_choice = MagicMock()
    fake_choice.message.content = None
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    with patch("better_code_review_graph.summarizer._get_openai_client") as mock_get:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_response
        mock_get.return_value = mock_client
        with pytest.raises(RuntimeError, match="empty/None content") as exc_info:
            summarize_node(node, provider="openai", api_key="o-key")
    assert "summarize_node failed via openai" not in str(exc_info.value)
    assert "x.py::baz" in str(exc_info.value)


def test_summarize_node_provider_is_case_sensitive():
    """provider arg must match the lowercase canonical form returned by resolve_summary_provider."""
    node = NodeNeedingSummary(node_id="x", source_text="y", source_hash=None)
    with pytest.raises(ValueError, match="Unsupported provider: 'Gemini'"):
        summarize_node(node, provider="Gemini", api_key="k")


def test_summarize_node_handles_braces_in_source():
    """Function source containing { } (dict literals, f-strings) must not break prompt construction."""
    src = 'def make_d(): return {"a": f"{x}"}'  # dict literal + f-string
    node = NodeNeedingSummary(node_id="x", source_text=src, source_hash=None)
    fake_response = MagicMock()
    fake_response.text = "Returns a dict."
    with patch("better_code_review_graph.summarizer._get_gemini_client") as mock_get:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response
        mock_get.return_value = mock_client
        result = summarize_node(node, provider="gemini", api_key="k")
    assert result == "Returns a dict."
    # Verify the source went verbatim into the prompt
    assert src in mock_client.models.generate_content.call_args.kwargs["contents"]


def test_get_gemini_client_constructs_with_api_key():
    """Lazy-import path in _get_gemini_client must call genai.Client(api_key=...)."""
    from better_code_review_graph.summarizer import _get_gemini_client

    fake_client = MagicMock()
    with patch("google.genai.Client", return_value=fake_client) as mock_ctor:
        result = _get_gemini_client("g-key")
    assert result is fake_client
    mock_ctor.assert_called_once_with(api_key="g-key")


def test_get_openai_client_constructs_with_api_key():
    """Lazy-import path in _get_openai_client must call openai.OpenAI(api_key=...)."""
    from better_code_review_graph.summarizer import _get_openai_client

    fake_client = MagicMock()
    with patch("openai.OpenAI", return_value=fake_client) as mock_ctor:
        result = _get_openai_client("o-key")
    assert result is fake_client
    mock_ctor.assert_called_once_with(api_key="o-key")


def test_summarize_node_openai_create_failure_wraps_runtimeerror():
    """OpenAI client.chat.completions.create() raising must be wrapped in RuntimeError (lines 203-204)."""
    node = NodeNeedingSummary(
        node_id="x.py::boom", source_text="def boom(): pass", source_hash=None
    )
    with patch("better_code_review_graph.summarizer._get_openai_client") as mock_get:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError(
            "openai upstream 503"
        )
        mock_get.return_value = mock_client
        with pytest.raises(
            RuntimeError, match="summarize_node failed via openai"
        ) as exc_info:
            summarize_node(node, provider="openai", api_key="o-key")
    # Original cause chained via "from exc"
    assert "openai upstream 503" in str(exc_info.value)


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
