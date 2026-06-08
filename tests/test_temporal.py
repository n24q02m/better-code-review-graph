from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

from better_code_review_graph.temporal import (
    TemporalIndex,
    TemporalUpsertResult,
    _hash_source,
)


def test_hash_source_handles_none() -> None:
    """None input collapses to empty string hash."""
    assert _hash_source(None) == ""


def test_hash_source_handles_empty_string() -> None:
    """Empty string input collapses to empty string hash."""
    assert _hash_source("") == ""


def test_hash_source_returns_sha256_for_content() -> None:
    """Valid string returns hex-encoded SHA-256."""
    text = "def foo(): pass"
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert _hash_source(text) == expected


def test_temporal_upsert_result_fields() -> None:
    """TemporalUpsertResult holds the expected fields."""
    res = TemporalUpsertResult(action="inserted", closed_out_count=0)
    assert res.action == "inserted"
    assert res.closed_out_count == 0


def test_temporal_index_instantiation() -> None:
    """TemporalIndex can be instantiated with a store and sha."""
    mock_store = MagicMock()
    idx = TemporalIndex(mock_store, current_sha="abc")
    assert idx._store == mock_store
    assert idx._current_sha == "abc"
