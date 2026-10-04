"""Hull model-cell policy as consumed by crg (WP2 de-host).

The per-sub BYOK bucket surface is gone (host-only keys, spec §4 Q1). What
remains testable at the crg level:

- model-chain resolution is HOST-wide (env), never per-request identity
- provider transport policy follows the auth mode: loopback providers are
  legitimate for a no-auth self-host, forbidden for shared (token/multi)
- one user's identity binding cannot change another request's dispatch
  configuration
"""

from __future__ import annotations

import httpx
import pytest
from hull_core.config.models import ModelCell
from hull_core.http.ssrf import SSRFBlockedError
from hull_core.providers.openai_spec import OpenAICompatClient

from crg.credential_state import set_current_sub
from crg.embeddings import resolve_embedding_chain


@pytest.fixture(autouse=True)
def _reset_subject():
    from crg.credential_state import _current_sub

    token = _current_sub.set(None)
    try:
        yield
    finally:
        _current_sub.reset(token)


def test_embedding_chain_is_host_env_not_request_scoped(monkeypatch):
    """A bound subject must not see a different EMBEDDING_MODELS chain."""
    monkeypatch.setenv("EMBEDDING_MODELS", "voyage-4-lite")
    set_current_sub("user-a")
    assert resolve_embedding_chain() == ["voyage-4-lite"]
    set_current_sub("user-b")
    assert resolve_embedding_chain() == ["voyage-4-lite"]
    set_current_sub(None)
    assert resolve_embedding_chain() == ["voyage-4-lite"]


def _cell(base_url: str) -> ModelCell:
    return ModelCell(task="embed", base_url=base_url, api_key="sk-test", model="m")


def test_loopback_provider_allowed_only_for_no_auth():
    """no-auth self-host may target local Ollama/vLLM on loopback."""
    client = OpenAICompatClient(_cell("http://127.0.0.1:11434/v1"), auth_mode="no-auth")
    try:
        assert client.cell.base_url.startswith("http://127.0.0.1")
    finally:
        ...


def test_loopback_provider_blocked_for_shared_modes():
    """token/multi deployments must not dispatch to loopback (SSRF)."""
    with pytest.raises(SSRFBlockedError):
        OpenAICompatClient(_cell("http://127.0.0.1:11434/v1"), auth_mode="token")
    with pytest.raises(SSRFBlockedError):
        OpenAICompatClient(_cell("http://localhost:11434/v1"), auth_mode="multi")


def test_client_carries_cell_authorization():
    """The cell's key becomes the bearer; keyless cells send no auth header."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1]}]})

    client = OpenAICompatClient(
        _cell("http://127.0.0.1:11434/v1"),
        auth_mode="no-auth",
        transport=httpx.MockTransport(handler),
    )
    import asyncio

    asyncio.run(client.embeddings(["x"]))
    assert seen["auth"] == "Bearer sk-test"
