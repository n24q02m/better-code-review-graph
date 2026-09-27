"""Tests for the LLM summary cache + hull chat-cell dispatch (WP2 de-host).

Covers ``better_code_review_graph.summarizer`` -- hash derivation,
cache-key composition, the configured-cell resolution (``summary_cell``),
the single-node ``summarize_node_async`` call, and the batch queue
(cache hit/miss, cap, per-node fail-open). All LLM interactions are
mocked at the ``OpenAICompatClient`` seam; no network traffic is generated.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
from typing import Any
from unittest.mock import patch

import pytest
from hull_core.config.models import ModelCell

import better_code_review_graph.summarizer as summarizer
from better_code_review_graph.summarizer import (
    NodeNeedingSummary,
    batch_summarize,
    compute_source_hash,
    compute_summary_cache_key,
    summarize_node_async,
    summary_cell,
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
    node = NodeNeedingSummary(node_id="x", source_text="s", source_hash=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.source_text = "t"  # type: ignore[misc]


def test_cache_key_combines_source_hash_and_provider():
    node = NodeNeedingSummary(
        node_id="m::f",
        source_text="def f(): pass",
        source_hash="abc123",
    )
    key = compute_summary_cache_key(node, "gemini/gemini-2.5-flash")
    assert key == "abc123:gemini/gemini-2.5-flash"


def test_cache_key_changes_when_provider_changes():
    node = NodeNeedingSummary(node_id="m::f", source_text="s", source_hash="h1")
    assert compute_summary_cache_key(node, "model-a") != compute_summary_cache_key(
        node, "model-b"
    )


def test_cache_key_uses_precomputed_hash_when_provided():
    """A precomputed source_hash is trusted verbatim -- no rehashing."""
    node = NodeNeedingSummary(
        node_id="m::f", source_text="def f(): pass", source_hash="h1"
    )
    key = compute_summary_cache_key(node, "model-a")
    assert key == "h1:model-a"
    assert "def" not in key


# ---------------------------------------------------------------------------
# summary_cell (host-configured chat cell)
# ---------------------------------------------------------------------------


class _FakeChatClient:
    """Seam double for hull's OpenAICompatClient inside summarizer."""

    def __init__(
        self, cell: ModelCell, responses: list[Any], auth_mode: str = "no-auth"
    ):
        self.cell = cell
        self.auth_mode = auth_mode
        self._responses = responses
        self.calls: list[list[dict]] = []

    async def chat(self, messages: list[dict], **options: Any) -> str:
        self.calls.append(messages)
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return str(item)

    async def aclose(self) -> None:
        return None


def _install_cell(monkeypatch, model: str = "gemini/gemini-2.5-flash") -> ModelCell:
    """Point summary_cell() at a configured fake cell."""
    cell = ModelCell(
        task="chat",
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-test",
        model=model,
    )
    monkeypatch.setattr(summarizer, "summary_cell", lambda: cell)
    return cell


def test_summary_cell_configured(tmp_path, monkeypatch):
    """A config.toml chat cell with an api_key resolves to the cell."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[models.chat]\nbase_url = "https://openrouter.ai/api/v1"\n'
        'api_key = "sk-h"\nmodel = "z-ai/glm-5.3-flash"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
    cell = summary_cell()
    assert cell is not None
    assert cell.model == "z-ai/glm-5.3-flash"
    assert cell.configured is True


def test_summary_cell_unconfigured_is_none(tmp_path, monkeypatch):
    """No config file (or a keyless cell) disables summaries."""
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "absent"))
    assert summary_cell() is None

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[models.chat]\nbase_url = "https://openrouter.ai/api/v1"\napi_key = ""\nmodel = "m"\n',
        encoding="utf-8",
    )
    assert summary_cell() is None


# ---------------------------------------------------------------------------
# summarize_node_async
# ---------------------------------------------------------------------------


def _node(src: str = "def f(): return 1") -> NodeNeedingSummary:
    return NodeNeedingSummary(
        node_id="x.py::f", source_text=src, source_hash=compute_source_hash(src)
    )


def test_summarize_node_returns_stripped_text(monkeypatch):
    client = _FakeChatClient(_install_cell(monkeypatch), ["  Returns 1.  \n"])
    out = asyncio.run(summarize_node_async(_node(), client))
    assert out == "Returns 1."
    assert len(client.calls) == 1


def test_summarize_node_prompt_carries_source_verbatim(monkeypatch):
    """Source containing { } (dict literals, f-strings) must survive verbatim."""
    src = 'd = {"k": 1}\ndef f(): return f"{d}"'
    client = _FakeChatClient(_install_cell(monkeypatch), ["ok"])
    asyncio.run(summarize_node_async(_node(src), client))
    prompt = client.calls[0][0]["content"]
    assert src in prompt
    assert prompt.startswith("Write a one-paragraph docstring")


def test_summarize_node_wraps_provider_errors(monkeypatch):
    client = _FakeChatClient(_install_cell(monkeypatch), [RuntimeError("API timeout")])
    with pytest.raises(RuntimeError, match="summarize_node failed"):
        asyncio.run(summarize_node_async(_node(), client))


def test_summarize_node_empty_content_raises(monkeypatch):
    """Empty/None content (safety filter) must fail loudly, not cache garbage."""
    client = _FakeChatClient(_install_cell(monkeypatch), ["   "])
    with pytest.raises(RuntimeError, match="empty/None content"):
        asyncio.run(summarize_node_async(_node(), client))


# ---------------------------------------------------------------------------
# update_summary + batch_summarize
# ---------------------------------------------------------------------------


def _make_store(tmp_path):
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo

    store = GraphStore(str(tmp_path / "test.db"))
    return store, NodeInfo


def _add_function(store, NodeInfo, i: int = 0, src: str | None = None):
    node_id = store.upsert_node(
        NodeInfo(
            kind="Function",
            name=f"f{i}",
            file_path="x.py",
            line_start=i + 1,
            line_end=i + 2,
            language="python",
        ),
        file_hash="h",
    )
    store._conn.execute(
        "UPDATE nodes SET source_text=? WHERE id=?",
        (src or f"def f{i}(): return {i}", node_id),
    )
    store._conn.commit()
    return node_id


def test_update_summary_persists_to_db(tmp_path):
    """GraphStore.update_summary should write summary + provider + source_hash atomically."""
    store, NodeInfo = _make_store(tmp_path)
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


def test_batch_summarize_skips_when_no_cell(tmp_path, monkeypatch):
    """Without a configured chat cell, batch_summarize skips without calling the LLM."""
    monkeypatch.setattr(summarizer, "summary_cell", lambda: None)

    store, NodeInfo = _make_store(tmp_path)
    try:
        _add_function(store, NodeInfo)
        result = batch_summarize(store, max_nodes=10)
        assert result.skipped_no_provider is True
        assert result.generated == 0
        assert result.cached == 0
        assert result.provider is None
    finally:
        store.close()


def test_batch_summarize_generates_for_uncached_nodes(tmp_path, monkeypatch):
    """Function nodes without summary should be sent to the chat cell and persisted."""
    cell = _install_cell(monkeypatch, model="gemini/gemini-2.5-flash")

    store, NodeInfo = _make_store(tmp_path)
    try:
        node_id = _add_function(store, NodeInfo, src="def f(): return 1")
        fake = _FakeChatClient(cell, ["Returns 1."])
        with patch.object(summarizer, "OpenAICompatClient", lambda c, auth_mode: fake):
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.cached == 0
        assert result.provider == "gemini/gemini-2.5-flash"
        # Verify persisted
        row = store._conn.execute(
            "SELECT summary, summary_provider, source_hash FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "Returns 1."
        assert row[1] == "gemini/gemini-2.5-flash"
        assert row[2] == compute_source_hash("def f(): return 1")
    finally:
        store.close()


def test_batch_summarize_cache_hit_when_hash_and_provider_match(tmp_path, monkeypatch):
    """Pre-existing summary + matching source_hash + matching provider => cache hit."""
    cell = _install_cell(monkeypatch, model="gemini/gemini-2.5-flash")

    store, NodeInfo = _make_store(tmp_path)
    try:
        src = "def f(): return 1"
        node_id = _add_function(store, NodeInfo, src=src)
        store._conn.execute(
            "UPDATE nodes SET source_text=?, summary=?, summary_provider=?, source_hash=? WHERE id=?",
            (
                src,
                "Cached summary.",
                "gemini/gemini-2.5-flash",
                compute_source_hash(src),
                node_id,
            ),
        )
        store._conn.commit()

        fake = _FakeChatClient(cell, [])
        with patch.object(summarizer, "OpenAICompatClient", lambda c, auth_mode: fake):
            result = batch_summarize(store, max_nodes=10)

        assert result.cached == 1
        assert result.generated == 0
        assert fake.calls == []
    finally:
        store.close()


def test_batch_summarize_respects_max_nodes_cap(tmp_path, monkeypatch):
    """max_nodes=2 with 5 candidate nodes should generate at most 2 (SELECT ... LIMIT ?)."""
    cell = _install_cell(monkeypatch)

    store, NodeInfo = _make_store(tmp_path)
    try:
        for i in range(5):
            _add_function(store, NodeInfo, i=i)

        fake = _FakeChatClient(cell, ["Stub."] * 5)
        with patch.object(summarizer, "OpenAICompatClient", lambda c, auth_mode: fake):
            result = batch_summarize(store, max_nodes=2)

        assert result.generated == 2
        assert len(fake.calls) == 2
    finally:
        store.close()


def test_batch_summarize_continues_after_per_node_error(tmp_path, monkeypatch):
    """A failing chat call for one node counts as error + continues with others."""
    cell = _install_cell(monkeypatch)

    store, NodeInfo = _make_store(tmp_path)
    try:
        for i in range(3):
            _add_function(store, NodeInfo, i=i)

        fake = _FakeChatClient(cell, ["First.", RuntimeError("boom"), "Third."])
        with patch.object(summarizer, "OpenAICompatClient", lambda c, auth_mode: fake):
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 2
        assert result.errors == 1
        assert len(fake.calls) == 3

        # Lock per-node persistence: nodes 0 + 2 must have summaries; node 1 (raised) must not.
        rows = store._conn.execute(
            "SELECT id, summary FROM nodes WHERE kind='Function' ORDER BY id"
        ).fetchall()
        summaries = [(r[1] is not None, r[1]) for r in rows]
        assert summaries[0] == (True, "First.")
        assert summaries[1] == (False, None)
        assert summaries[2] == (True, "Third.")
    finally:
        store.close()


def test_batch_summarize_treats_empty_string_summary_as_cache_miss(
    tmp_path, monkeypatch
):
    """Empty-string stored_summary must regenerate even when hash + provider match."""
    cell = _install_cell(monkeypatch, model="gemini/gemini-2.5-flash")

    store, NodeInfo = _make_store(tmp_path)
    try:
        src = "def f(): return 1"
        node_id = _add_function(store, NodeInfo, src=src)
        store._conn.execute(
            "UPDATE nodes SET source_text=?, summary=?, summary_provider=?, source_hash=? WHERE id=?",
            (src, "", "gemini/gemini-2.5-flash", compute_source_hash(src), node_id),
        )
        store._conn.commit()

        fake = _FakeChatClient(cell, ["Returns 1."])
        with patch.object(summarizer, "OpenAICompatClient", lambda c, auth_mode: fake):
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1, "Empty-string summary should NOT be a cache hit"
        assert result.cached == 0
        assert len(fake.calls) == 1
        row = store._conn.execute(
            "SELECT summary FROM nodes WHERE id=?", (node_id,)
        ).fetchone()
        assert row[0] == "Returns 1."
    finally:
        store.close()


def test_batch_summarize_regenerates_when_source_changed(tmp_path, monkeypatch):
    """If stored hash != live hash, treat as stale and regenerate."""
    cell = _install_cell(monkeypatch, model="gemini/gemini-2.5-flash")

    store, NodeInfo = _make_store(tmp_path)
    try:
        node_id = _add_function(store, NodeInfo, src="def f(): return 1")
        store._conn.execute(
            "UPDATE nodes SET summary=?, summary_provider=?, source_hash=? WHERE id=?",
            ("Old summary.", "gemini/gemini-2.5-flash", "stale-hash", node_id),
        )
        store._conn.commit()

        fake = _FakeChatClient(cell, ["New summary."])
        with patch.object(summarizer, "OpenAICompatClient", lambda c, auth_mode: fake):
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.cached == 0
    finally:
        store.close()


def test_changing_model_invalidates_summary_cache(tmp_path, monkeypatch):
    """The full model is the cache identity: switching cells invalidates old summaries."""
    store, NodeInfo = _make_store(tmp_path)
    try:
        src = "def f(): return 1"
        node_id = _add_function(store, NodeInfo, src=src)
        store._conn.execute(
            "UPDATE nodes SET source_text=?, summary=?, summary_provider=?, source_hash=? WHERE id=?",
            (src, "Old model summary.", "model-a", compute_source_hash(src), node_id),
        )
        store._conn.commit()

        # Host switches the chat cell to a different model.
        cell_b = _install_cell(monkeypatch, model="model-b")
        fake = _FakeChatClient(cell_b, ["New model summary."])
        with patch.object(summarizer, "OpenAICompatClient", lambda c, auth_mode: fake):
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 1
        assert result.provider == "model-b"
        row = store._conn.execute(
            "SELECT summary, summary_provider FROM nodes WHERE id=?", (node_id,)
        ).fetchone()
        assert row[0] == "New model summary."
        assert row[1] == "model-b"
    finally:
        store.close()


def test_batch_summarize_skips_non_function_nodes(tmp_path, monkeypatch):
    """Only Function-kind nodes enter the summarize queue."""
    from better_code_review_graph.parser import NodeInfo

    cell = _install_cell(monkeypatch)

    store, _ = _make_store(tmp_path)
    try:
        store.upsert_node(
            NodeInfo(
                kind="Class",
                name="X",
                file_path="x.py",
                line_start=1,
                line_end=2,
                language="python",
            ),
            file_hash="h",
        )
        store._conn.execute(
            "UPDATE nodes SET source_text=? WHERE name='X'", ("class X: pass",)
        )
        store._conn.commit()

        fake = _FakeChatClient(cell, [])
        with patch.object(summarizer, "OpenAICompatClient", lambda c, auth_mode: fake):
            result = batch_summarize(store, max_nodes=10)

        assert result.generated == 0
        assert result.cached == 0
        assert fake.calls == []
    finally:
        store.close()


def test_batch_summarize_invalid_max_nodes_raises(monkeypatch):
    _install_cell(monkeypatch)
    with pytest.raises(ValueError, match="max_nodes"):
        batch_summarize(store=None, max_nodes=0)


def test_batch_summarize_arbitrary_model_names_accepted(tmp_path, monkeypatch):
    """Any OpenAI-spec model name works through the cell (provider-agnostic)."""
    cell = _install_cell(monkeypatch, model="anthropic/claude-3-5-sonnet")

    store, NodeInfo = _make_store(tmp_path)
    try:
        _add_function(store, NodeInfo, src="def f(): return 1")
        fake = _FakeChatClient(cell, ["Returns 1."])
        with patch.object(summarizer, "OpenAICompatClient", lambda c, auth_mode: fake):
            result = batch_summarize(store, max_nodes=10)
        assert result.generated == 1
        assert result.provider == "anthropic/claude-3-5-sonnet"
    finally:
        store.close()
