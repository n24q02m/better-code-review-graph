"""Tests for HTTP multi-user credential wiring (per-sub contextvar).

Covers:
- ``_current_sub`` contextvar default + isolation across asyncio tasks
- ``set_current_sub`` / ``get_current_sub`` round-trip
- ``credentials_for_current_request`` falls back to env when sub unset (stdio)
- Per-sub credential isolation (sub_a does not see sub_b's keys)
- ``_per_request_sub_scope`` callback semantics (sets + resets contextvar)

These tests do not boot the full HTTP server; they exercise the contextvar
plumbing directly. Real HTTP wiring is exercised by the E2E driver
(``mcp-core/scripts/e2e``) under config ``crg``.
"""

from __future__ import annotations

import asyncio

import pytest

from better_code_review_graph.credential_state import (
    CLOUD_KEYS,
    _current_sub,
    credentials_for_current_request,
    get_current_sub,
    set_current_sub,
    store_for_sub,
)


@pytest.fixture(autouse=True)
def _reset_contextvar():
    """Ensure each test starts with no active sub binding."""
    token = _current_sub.set(None)
    try:
        yield
    finally:
        _current_sub.reset(token)


@pytest.fixture
def _clean_cloud_env(monkeypatch):
    """Strip all CLOUD_KEYS from os.environ for deterministic stdio fallback."""
    for key in CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_stdio_mode_unchanged(monkeypatch, _clean_cloud_env):
    """Stdio path: ``_current_sub`` is None -> env-only fallback.

    Asserts that without a sub bound, ``credentials_for_current_request``
    returns env-derived dict (CLOUD_KEYS only) and that setting an env
    var is observed by the helper.
    """
    assert get_current_sub() is None
    assert credentials_for_current_request() == {}

    monkeypatch.setenv("OPENAI_API_KEY", "sk-stdio-only")
    monkeypatch.setenv("UNRELATED_VAR", "ignored")

    creds = credentials_for_current_request()
    assert creds == {"OPENAI_API_KEY": "sk-stdio-only"}
    # Non-cloud keys must not leak through
    assert "UNRELATED_VAR" not in creds


def test_http_sub_a_isolation(tmp_path, monkeypatch, _clean_cloud_env):
    """HTTP multi-user: sub_a's saved keys are returned for that sub only."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))

    store_for_sub("sub-a", {"OPENAI_API_KEY": "sk-a"})

    set_current_sub("sub-a")
    creds = credentials_for_current_request()
    assert creds == {"OPENAI_API_KEY": "sk-a"}


def test_http_sub_b_no_bleed(tmp_path, monkeypatch, _clean_cloud_env):
    """sub_b's bucket is independent: sub_a keys do not bleed into sub_b."""
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))

    store_for_sub("sub-a", {"OPENAI_API_KEY": "sk-a"})
    store_for_sub("sub-b", {"GEMINI_API_KEY": "gm-b"})

    set_current_sub("sub-b")
    creds = credentials_for_current_request()
    assert creds == {"GEMINI_API_KEY": "gm-b"}
    # sub_a's key must NOT appear in sub_b's view
    assert "OPENAI_API_KEY" not in creds


def test_http_no_sub_returns_empty(tmp_path, monkeypatch, _clean_cloud_env):
    """An authenticated sub with no saved config gets empty dict (not env).

    Once a sub is bound, the helper consults the per-sub bucket exclusively;
    process env vars are never returned for an HTTP request (would leak the
    deployment's bootstrap creds across users).
    """
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-process-env-leak")

    set_current_sub("sub-fresh")
    creds = credentials_for_current_request()
    assert creds == {}
    assert "OPENAI_API_KEY" not in creds


async def test_concurrent_subs_isolation(tmp_path, monkeypatch, _clean_cloud_env):
    """Concurrent asyncio tasks each see their own sub binding.

    ContextVar is per-task in asyncio (each ``asyncio.create_task`` copies
    the current context), so setting ``_current_sub`` in task A must not
    affect task B running on the same event loop.
    """
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))

    store_for_sub("sub-a", {"OPENAI_API_KEY": "sk-a"})
    store_for_sub("sub-b", {"GEMINI_API_KEY": "gm-b"})

    barrier = asyncio.Event()
    results: dict[str, dict[str, str]] = {}

    async def _request(sub: str) -> None:
        # Each task starts with _current_sub default (None); the simulated
        # auth_scope middleware sets it for the duration of the request.
        token = _current_sub.set(sub)
        try:
            # Yield to let other tasks interleave -- catches any global state
            # accidentally leaking between tasks.
            await barrier.wait()
            results[sub] = credentials_for_current_request()
        finally:
            _current_sub.reset(token)

    task_a = asyncio.create_task(_request("sub-a"))
    task_b = asyncio.create_task(_request("sub-b"))
    # Let both tasks reach the barrier so their context bindings are live
    # simultaneously before we read from each.
    await asyncio.sleep(0.01)
    barrier.set()
    await asyncio.gather(task_a, task_b)

    assert results["sub-a"] == {"OPENAI_API_KEY": "sk-a"}
    assert results["sub-b"] == {"GEMINI_API_KEY": "gm-b"}


async def test_per_request_sub_scope_callback(tmp_path, monkeypatch, _clean_cloud_env):
    """The ``auth_scope`` middleware must set on entry and reset on exit.

    Simulates a request lifecycle: set _current_sub from claims, run the
    inner handler (which observes the bound sub), then reset back so the
    next request starts clean.
    """
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    store_for_sub("user-42", {"COHERE_API_KEY": "co-42"})

    observed: list[str | None] = []

    async def _inner_handler() -> None:
        observed.append(get_current_sub())
        observed.append(credentials_for_current_request().get("COHERE_API_KEY"))

    # Inline copy of server._per_request_sub_scope -- keeps the test
    # decoupled from the FastMCP / Starlette plumbing while exercising
    # the exact pattern used in run_http().
    async def _per_request_sub_scope(claims: dict, next_):
        token = _current_sub.set(claims.get("sub"))
        try:
            await next_()
        finally:
            _current_sub.reset(token)

    # Pre-condition: no sub bound
    assert get_current_sub() is None

    await _per_request_sub_scope({"sub": "user-42"}, _inner_handler)

    # Inner handler saw the bound sub + its credentials
    assert observed == ["user-42", "co-42"]
    # Post-condition: middleware reset cleanly so next request starts fresh
    assert get_current_sub() is None
