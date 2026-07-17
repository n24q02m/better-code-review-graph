"""HTTP multi-user dispatch wiring: per-sub key + model chain reach litellm.

The contextvar plumbing (``credentials_for_current_request`` / per-sub
buckets) is exercised by ``test_multi_user.py``. This file closes the loop:
it asserts the *live dispatch paths* (embedding + summarizer) actually
consult the bound sub's bucket -- the per-sub API key AND the per-sub
``EMBEDDING_MODELS`` / ``SUMMARY_MODELS`` chain must reach the (mocked)
``mcp_core.llm`` call, and a second concurrent sub must be isolated.

Regression guard for the multi-user leak: before this fix the resolvers
read ``os.environ`` directly, so in HTTP multi-user mode every sub got the
deployment-global env (or nothing) instead of their own per-sub config.

CRITICAL INVARIANT: per-sub values flow request-scoped (read at dispatch
time via the per-sub accessor) -- they are NEVER written to the
process-global ``os.environ`` (that would leak one sub's secret to a
concurrent request of another sub). The isolation assertions below fail
loudly if a future change reintroduces an ``os.environ.setdefault`` leak.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.credential_state import (
    CLOUD_KEYS,
    _current_sub,
    store_for_sub,
)
from better_code_review_graph.embeddings import (
    CloudEmbeddingBackend,
    resolve_embedding_chain,
)
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.summarizer import batch_summarize, resolve_summary_chain


@pytest.fixture(autouse=True)
def _reset_contextvar():
    """Each test starts and ends with no active sub binding."""
    token = _current_sub.set(None)
    try:
        yield
    finally:
        _current_sub.reset(token)


@pytest.fixture
def _clean_cloud_env(monkeypatch):
    """Strip cloud keys + model chains so per-sub config is the only source."""
    for key in (*CLOUD_KEYS, "EMBEDDING_MODELS", "SUMMARY_MODELS"):
        monkeypatch.delenv(key, raising=False)


def _embedding_response(n: int, dim: int = 768) -> MagicMock:
    resp = MagicMock()
    resp.data = [{"index": i, "embedding": [0.1] * dim} for i in range(n)]
    return resp


def _completion_response(text: str) -> MagicMock:
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = text
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# resolve_embedding_chain / resolve_summary_chain: per-sub vs env
# ---------------------------------------------------------------------------


def test_embedding_chain_reads_per_sub_config(tmp_path, monkeypatch, _clean_cloud_env):
    """When a sub is bound, EMBEDDING_MODELS comes from that sub's bucket."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    store_for_sub(
        "sub-a",
        {
            "EMBEDDING_MODELS": "gemini/gemini-embedding-001",
            "GEMINI_API_KEY": "gm-a",
        },
    )

    _current_sub.set("sub-a")
    assert resolve_embedding_chain() == ["gemini/gemini-embedding-001"]


def test_embedding_chain_second_sub_isolated(tmp_path, monkeypatch, _clean_cloud_env):
    """sub-b's chain is its own; sub-a's EMBEDDING_MODELS does not bleed in."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    store_for_sub("sub-a", {"EMBEDDING_MODELS": "gemini/gemini-embedding-001"})
    store_for_sub("sub-b", {"EMBEDDING_MODELS": "openai/text-embedding-3-large"})

    _current_sub.set("sub-b")
    assert resolve_embedding_chain() == ["openai/text-embedding-3-large"]


def test_summary_chain_reads_per_sub_config(tmp_path, monkeypatch, _clean_cloud_env):
    """When a sub is bound, SUMMARY_MODELS comes from that sub's bucket."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    store_for_sub(
        "sub-a",
        {"SUMMARY_MODELS": "openai/gpt-4o-mini", "OPENAI_API_KEY": "sk-a"},
    )

    _current_sub.set("sub-a")
    assert resolve_summary_chain() == ["openai/gpt-4o-mini"]


def test_chain_falls_back_to_env_when_no_sub(monkeypatch, _clean_cloud_env):
    """Stdio / single-user (sub is None): env is the source of truth."""
    monkeypatch.setenv("EMBEDDING_MODELS", "openai/text-embedding-3-large")
    monkeypatch.setenv("SUMMARY_MODELS", "gemini/gemini-2.5-flash")

    assert _current_sub.get() is None
    assert resolve_embedding_chain() == ["openai/text-embedding-3-large"]
    assert resolve_summary_chain() == ["gemini/gemini-2.5-flash"]


# ---------------------------------------------------------------------------
# Embedding dispatch: per-sub key reaches the mocked litellm embedding call
# ---------------------------------------------------------------------------


def test_embedding_dispatch_uses_per_sub_key(tmp_path, monkeypatch, _clean_cloud_env):
    """The per-sub API key reaches mcp_core.llm.embedding; env stays clean."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    store_for_sub(
        "sub-a",
        {
            "EMBEDDING_MODELS": "gemini/gemini-embedding-001",
            "GEMINI_API_KEY": "gm-a",
        },
    )

    _current_sub.set("sub-a")
    backend = CloudEmbeddingBackend()
    assert backend.model == "gemini/gemini-embedding-001"

    with patch("mcp_core.llm.embedding") as mock_embed:
        mock_embed.return_value = _embedding_response(1)
        backend.embed_texts(["hello"], dimensions=768)

    call_kwargs = mock_embed.call_args.kwargs
    assert call_kwargs["model"] == "gemini/gemini-embedding-001"
    assert call_kwargs["api_key"] == "gm-a"
    # Per-sub key must NOT have leaked into the process environment.
    assert os.environ.get("GEMINI_API_KEY") is None


def test_embedding_dispatch_second_sub_isolated(
    tmp_path, monkeypatch, _clean_cloud_env
):
    """A second sub gets its own key/model -- never sub-a's."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    store_for_sub(
        "sub-a",
        {"EMBEDDING_MODELS": "gemini/gemini-embedding-001", "GEMINI_API_KEY": "gm-a"},
    )
    store_for_sub(
        "sub-b",
        {
            "EMBEDDING_MODELS": "openai/text-embedding-3-large",
            "OPENAI_API_KEY": "sk-b",
        },
    )

    _current_sub.set("sub-b")
    backend = CloudEmbeddingBackend()
    with patch("mcp_core.llm.embedding") as mock_embed:
        mock_embed.return_value = _embedding_response(1)
        backend.embed_texts(["hello"], dimensions=768)

    call_kwargs = mock_embed.call_args.kwargs
    assert call_kwargs["model"] == "openai/text-embedding-3-large"
    assert call_kwargs["api_key"] == "sk-b"
    # sub-a's key must NOT appear anywhere in sub-b's dispatch.
    assert call_kwargs["api_key"] != "gm-a"
    assert os.environ.get("OPENAI_API_KEY") is None
    assert os.environ.get("GEMINI_API_KEY") is None


# ---------------------------------------------------------------------------
# Summarizer dispatch: per-sub key + chain reach the mocked completion call
# ---------------------------------------------------------------------------


def _seed_function_node(store: GraphStore) -> None:
    store._conn.execute(
        "INSERT INTO nodes (id, qualified_name, name, kind, file_path, "
        "updated_at, source_text) VALUES (1, 'f.py::foo', 'foo', 'Function', "
        "'f.py', 0.0, 'def foo():\n    return 1\n')"
    )
    store._conn.commit()


def test_summarizer_dispatch_uses_per_sub_key(tmp_path, monkeypatch, _clean_cloud_env):
    """batch_summarize sends the per-sub model + key to mcp_core.llm.completion."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    store_for_sub(
        "sub-a",
        {"SUMMARY_MODELS": "openai/gpt-4o-mini", "OPENAI_API_KEY": "sk-a"},
    )

    store = GraphStore(str(tmp_path / "graph_a.db"))
    _seed_function_node(store)

    _current_sub.set("sub-a")
    with patch("mcp_core.llm.completion") as mock_completion:
        mock_completion.return_value = _completion_response("does a thing")
        result = batch_summarize(store)
    store.close()

    assert result.generated == 1
    assert result.provider == "openai"
    call_kwargs = mock_completion.call_args.kwargs
    assert call_kwargs["model"] == "openai/gpt-4o-mini"
    assert call_kwargs["api_key"] == "sk-a"
    assert os.environ.get("OPENAI_API_KEY") is None


def test_summarizer_dispatch_per_sub_google_alias_key(
    tmp_path, monkeypatch, _clean_cloud_env
):
    """A per-sub GOOGLE_API_KEY is accepted as the GEMINI_API_KEY alias."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    store_for_sub(
        "sub-g",
        {"SUMMARY_MODELS": "gemini/gemini-2.5-flash", "GOOGLE_API_KEY": "g-alias"},
    )

    store = GraphStore(str(tmp_path / "graph_g.db"))
    _seed_function_node(store)

    _current_sub.set("sub-g")
    with patch("mcp_core.llm.completion") as mock_completion:
        mock_completion.return_value = _completion_response("alias works")
        result = batch_summarize(store)
    store.close()

    assert result.generated == 1
    assert mock_completion.call_args.kwargs["api_key"] == "g-alias"


def test_summarizer_dispatch_second_sub_isolated(
    tmp_path, monkeypatch, _clean_cloud_env
):
    """sub-b's summary dispatch sees its own key/model, never sub-a's."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    store_for_sub(
        "sub-a",
        {"SUMMARY_MODELS": "openai/gpt-4o-mini", "OPENAI_API_KEY": "sk-a"},
    )
    store_for_sub(
        "sub-b",
        {"SUMMARY_MODELS": "gemini/gemini-2.5-flash", "GEMINI_API_KEY": "gm-b"},
    )

    store = GraphStore(str(tmp_path / "graph_b.db"))
    _seed_function_node(store)

    _current_sub.set("sub-b")
    with patch("mcp_core.llm.completion") as mock_completion:
        mock_completion.return_value = _completion_response("does b thing")
        result = batch_summarize(store)
    store.close()

    assert result.provider == "gemini"
    call_kwargs = mock_completion.call_args.kwargs
    assert call_kwargs["model"] == "gemini/gemini-2.5-flash"
    assert call_kwargs["api_key"] == "gm-b"
    assert call_kwargs["api_key"] != "sk-a"
    assert os.environ.get("GEMINI_API_KEY") is None
    assert os.environ.get("OPENAI_API_KEY") is None


# ---------------------------------------------------------------------------
# Per-sub custom endpoint (api_base): EMBEDDING_API_BASE / LLM_API_BASE reach
# the dispatch per request. Reading os.getenv instead would make the per-sub
# relay endpoint a silent no-op in multi-user mode (it only lives in the sub
# bucket, never the shared process env).
# ---------------------------------------------------------------------------


def test_embedding_dispatch_uses_per_sub_api_base(
    tmp_path, monkeypatch, _clean_cloud_env
):
    """The per-sub EMBEDDING_API_BASE reaches mcp_core.llm.embedding."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("EMBEDDING_API_BASE", raising=False)
    store_for_sub(
        "sub-a",
        {
            "EMBEDDING_MODELS": "gemini/gemini-embedding-001",
            "GEMINI_API_KEY": "gm-a",
            "EMBEDDING_API_BASE": "https://gw-a/v1",
        },
    )

    _current_sub.set("sub-a")
    backend = CloudEmbeddingBackend()
    with patch("mcp_core.llm.embedding") as mock_embed:
        mock_embed.return_value = _embedding_response(1)
        backend.embed_texts(["hello"], dimensions=768)

    call_kwargs = mock_embed.call_args.kwargs
    assert call_kwargs["api_base"] == "https://gw-a/v1"
    assert call_kwargs["api_key"] == "gm-a"
    # Per-sub endpoint must NOT have leaked into the process environment.
    assert os.environ.get("EMBEDDING_API_BASE") is None


def test_embedding_dispatch_api_base_second_sub_isolated(
    tmp_path, monkeypatch, _clean_cloud_env
):
    """A second sub drives its own EMBEDDING_API_BASE -- never sub-a's."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("EMBEDDING_API_BASE", raising=False)
    store_for_sub(
        "sub-a",
        {
            "EMBEDDING_MODELS": "gemini/gemini-embedding-001",
            "GEMINI_API_KEY": "gm-a",
            "EMBEDDING_API_BASE": "https://gw-a/v1",
        },
    )
    store_for_sub(
        "sub-b",
        {
            "EMBEDDING_MODELS": "openai/text-embedding-3-large",
            "OPENAI_API_KEY": "sk-b",
            "EMBEDDING_API_BASE": "https://gw-b/v1",
        },
    )

    _current_sub.set("sub-b")
    backend = CloudEmbeddingBackend()
    with patch("mcp_core.llm.embedding") as mock_embed:
        mock_embed.return_value = _embedding_response(1)
        backend.embed_texts(["hello"], dimensions=768)

    call_kwargs = mock_embed.call_args.kwargs
    assert call_kwargs["api_base"] == "https://gw-b/v1"
    assert call_kwargs["api_base"] != "https://gw-a/v1"


def test_summarizer_dispatch_uses_per_sub_api_base(
    tmp_path, monkeypatch, _clean_cloud_env
):
    """The per-sub LLM_API_BASE reaches mcp_core.llm.completion."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    store_for_sub(
        "sub-a",
        {
            "SUMMARY_MODELS": "openai/gpt-4o-mini",
            "OPENAI_API_KEY": "sk-a",
            "LLM_API_BASE": "https://gw-a/llm",
        },
    )

    store = GraphStore(str(tmp_path / "graph_a.db"))
    _seed_function_node(store)

    _current_sub.set("sub-a")
    with patch("mcp_core.llm.completion") as mock_completion:
        mock_completion.return_value = _completion_response("does a thing")
        result = batch_summarize(store)
    store.close()

    assert result.generated == 1
    call_kwargs = mock_completion.call_args.kwargs
    assert call_kwargs["api_base"] == "https://gw-a/llm"
    assert call_kwargs["api_key"] == "sk-a"
    assert os.environ.get("LLM_API_BASE") is None


def test_summarizer_dispatch_api_base_second_sub_isolated(
    tmp_path, monkeypatch, _clean_cloud_env
):
    """sub-b's LLM_API_BASE never bleeds sub-a's endpoint."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    store_for_sub(
        "sub-a",
        {
            "SUMMARY_MODELS": "openai/gpt-4o-mini",
            "OPENAI_API_KEY": "sk-a",
            "LLM_API_BASE": "https://gw-a/llm",
        },
    )
    store_for_sub(
        "sub-b",
        {
            "SUMMARY_MODELS": "gemini/gemini-2.5-flash",
            "GEMINI_API_KEY": "gm-b",
            "LLM_API_BASE": "https://gw-b/llm",
        },
    )

    store = GraphStore(str(tmp_path / "graph_b.db"))
    _seed_function_node(store)

    _current_sub.set("sub-b")
    with patch("mcp_core.llm.completion") as mock_completion:
        mock_completion.return_value = _completion_response("does b thing")
        batch_summarize(store)
    store.close()

    call_kwargs = mock_completion.call_args.kwargs
    assert call_kwargs["api_base"] == "https://gw-b/llm"
    assert call_kwargs["api_base"] != "https://gw-a/llm"


def test_api_base_falls_back_to_env_when_no_sub(monkeypatch, _clean_cloud_env):
    """Stdio / single-user (sub is None): *_API_BASE comes from os.environ.

    Unlike provider keys, litellm does not know crg's own ``*_API_BASE``
    names, so the single-user path must surface the env value or the
    configured endpoint would be dropped.
    """
    monkeypatch.setenv("EMBEDDING_API_BASE", "https://env-embed/v1")
    monkeypatch.setenv("LLM_API_BASE", "https://env-llm/v1")

    from better_code_review_graph.credential_state import (
        config_value_for_current_request,
    )

    assert _current_sub.get() is None
    assert (
        config_value_for_current_request("EMBEDDING_API_BASE") == "https://env-embed/v1"
    )
    assert config_value_for_current_request("LLM_API_BASE") == "https://env-llm/v1"


def test_per_sub_api_base_ssrf_rejected_in_multi_user(
    tmp_path, monkeypatch, _clean_cloud_env
):
    """A per-sub loopback EMBEDDING_API_BASE is blocked by the SSRF vet.

    The resolved endpoint flows into the REAL mcp_core.llm dispatch, which
    vets it (``_prep_api_base`` -> ``vet_api_base``) before any network call.
    ``PUBLIC_URL`` set => multi-user => loopback/private blocked
    unconditionally. Proves the per-sub endpoint stays on the vetted path.
    """
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_URL", "https://crg.example")  # multi-user mode
    monkeypatch.delenv("EMBEDDING_API_BASE", raising=False)

    from mcp_core.http import SSRFBlockedError

    store_for_sub(
        "sub-a",
        {
            "EMBEDDING_MODELS": "gemini/gemini-embedding-001",
            "GEMINI_API_KEY": "gm-a",
            "EMBEDDING_API_BASE": "http://127.0.0.1:9000",
        },
    )

    _current_sub.set("sub-a")
    backend = CloudEmbeddingBackend()
    with pytest.raises(SSRFBlockedError):
        backend.embed_texts(["hello"], dimensions=768)
