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
