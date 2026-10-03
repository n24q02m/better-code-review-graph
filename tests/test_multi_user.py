"""Tests for HTTP multi-user identity scoping (hull-core auth, WP2 de-host).

Covers:
- ``_current_sub`` contextvar default + isolation across asyncio tasks
- ``set_current_sub`` / ``get_current_sub`` round-trip
- ``get_current_sub`` falls back to hull-core's request identity in auth
  mode ``multi`` (namespace is the data root) and stays ``None`` for
  shared-namespace modes (no-auth / token) and unauthenticated contexts
- Path-safety: a hostile namespace cannot escape the ``subs/`` root

These tests do not boot the full HTTP server; they exercise the identity
plumbing directly. Real HTTP wiring is covered by the hull HTTP app tests
(``test_hull_http_mcp.py``).
"""

from __future__ import annotations

import asyncio

import pytest

from crg.credential_state import (
    _current_sub,
    get_current_sub,
    set_current_sub,
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
def _no_hull_identity(monkeypatch):
    """Neutralize the hull identity fallback (no request in flight)."""
    import hull_core.auth.context as hull_ctx

    monkeypatch.setattr(hull_ctx, "current_user", lambda: hull_ctx.AuthContext.local())


def test_no_binding_no_hull_identity(_no_hull_identity):
    """No explicit binding and no multi-mode hull identity -> None."""
    assert get_current_sub() is None


def test_explicit_binding_round_trip(_no_hull_identity):
    """set_current_sub/get_current_sub round-trip inside the same context."""
    set_current_sub("sub-a")
    assert get_current_sub() == "sub-a"


async def test_concurrent_subs_isolation(_no_hull_identity):
    """Concurrent asyncio tasks each see their own sub binding."""
    barrier = asyncio.Barrier(2)

    async def scoped(sub: str, key: str) -> str:
        token = _current_sub.set(sub)
        try:
            await barrier.wait()  # both bindings live simultaneously
            await asyncio.sleep(0.01)
            return f"{sub}:{get_current_sub()}:{key}"
        finally:
            _current_sub.reset(token)

    results = await asyncio.gather(
        scoped("sub-a", "k1"),
        scoped("sub-b", "k2"),
    )
    assert results[0] == "sub-a:sub-a:k1"
    assert results[1] == "sub-b:sub-b:k2"


def _bind_hull_identity(monkeypatch, mode: str, namespace: str) -> None:
    """Force hull-core's request identity contextvar to a fixed context."""
    import hull_core.auth.context as hull_ctx

    ctx = hull_ctx.AuthContext(
        uid="u1", namespace=namespace, mode=mode, allowed_roots=()
    )
    monkeypatch.setattr(hull_ctx, "current_user", lambda: ctx)


def test_hull_multi_mode_binds_namespace(monkeypatch):
    """In auth mode ``multi`` the hull namespace is the request subject."""
    _bind_hull_identity(monkeypatch, mode="multi", namespace="alice")
    assert get_current_sub() == "alice"


def test_hull_shared_modes_do_not_bind(monkeypatch):
    """Modes no-auth/token share one namespace: no sub -> repo-local db."""
    _bind_hull_identity(monkeypatch, mode="no-auth", namespace="default")
    assert get_current_sub() is None
    _bind_hull_identity(monkeypatch, mode="token", namespace="default")
    assert get_current_sub() is None


def test_hostile_namespace_rejected(monkeypatch, tmp_path):
    """A namespace carrying path separators must fail closed, not escape."""
    from crg.credential_state import db_path_for_sub

    _bind_hull_identity(monkeypatch, mode="multi", namespace="../evil")
    with pytest.raises(ValueError):
        get_current_sub()
    with pytest.raises(ValueError):
        db_path_for_sub("nested/path")
