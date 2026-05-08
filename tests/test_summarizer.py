"""Tests for the LLM summary cache + provider helpers (Phase 1 v1.6.x).

Covers the four pure-Python helpers in
``better_code_review_graph.summarizer`` -- hash derivation, cache-key
composition, and provider auto-detection from environment variables.
The module deliberately holds no LLM client code yet (Tasks 4-5).
"""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from better_code_review_graph.summarizer import (
    NodeNeedingSummary,
    compute_source_hash,
    compute_summary_cache_key,
    resolve_summary_provider,
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
