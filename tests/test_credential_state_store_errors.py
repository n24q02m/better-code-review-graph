"""A broken credential store must not be reported as "not configured yet".

``resolve_credential_state`` reads the encrypted per-plugin store and the
local-mode marker in HTTP mode. Both reads used to swallow every exception
into ``logger.debug``, so a store that exists but cannot be decrypted was
indistinguishable from a fresh install: the server logged "No credentials
found -- server starting in awaiting_setup mode" and the user went off to
re-enter API keys that were already saved and already correct.

Two things made that invisible rather than merely quiet:

* the level was ``debug``, below the default threshold, and
* ``credential_state`` is the only module using loguru, where
  ``logger.debug("Exception in %s: %s", name, exc)`` renders literally as
  ``Exception in %s: %s`` -- loguru formats with ``str.format``, so the
  ``%s`` placeholders never interpolate and the cause is dropped even when
  debug logging is switched on.
"""

from __future__ import annotations

import pytest
from loguru import logger

from better_code_review_graph import credential_state as cs

_DECRYPT_ERROR = "machine key mismatch -- cannot decrypt config.json"


@pytest.fixture
def loguru_messages():
    """Capture every loguru record emitted during the test."""
    captured: list[object] = []
    sink_id = logger.add(captured.append, level="DEBUG", format="{message}")
    try:
        yield captured
    finally:
        logger.remove(sink_id)


@pytest.fixture
def http_mode_without_env_keys(monkeypatch):
    """HTTP mode with no cloud keys set, so the store path is reached."""
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    for key in cs.CLOUD_KEYS:
        monkeypatch.delenv(key, raising=False)


def _levels_and_texts(captured) -> list[tuple[str, str]]:
    return [(m.record["level"].name, str(m)) for m in captured]


class TestUnreadableStoreIsReported:
    def test_store_read_failure_is_logged_above_debug_with_the_cause(
        self, loguru_messages, http_mode_without_env_keys, monkeypatch
    ):
        """The operator must be able to tell "broken" from "not set up"."""
        monkeypatch.setattr(
            cs.PerPluginStore,
            "load",
            lambda self: (_ for _ in ()).throw(RuntimeError(_DECRYPT_ERROR)),
        )

        state = cs.resolve_credential_state()

        # The server still starts -- crg works without cloud credentials.
        assert state is cs.CredentialState.AWAITING_SETUP

        emitted = _levels_and_texts(loguru_messages)
        loud = [
            (level, text)
            for level, text in emitted
            if level in ("WARNING", "ERROR", "CRITICAL")
        ]
        assert loud, f"a broken store must not be debug-only; got {emitted}"
        assert any(_DECRYPT_ERROR in text for _level, text in loud), (
            f"the underlying cause must survive into the message; got {loud}"
        )

    def test_mode_marker_read_failure_is_logged_above_debug_with_the_cause(
        self, loguru_messages, http_mode_without_env_keys, monkeypatch
    ):
        """A previous "skip relay" choice going unreadable is also a fault."""
        monkeypatch.setattr(cs.PerPluginStore, "load", lambda self: None)

        import mcp_core

        monkeypatch.setattr(
            mcp_core,
            "get_mode",
            lambda name: (_ for _ in ()).throw(RuntimeError(_DECRYPT_ERROR)),
        )

        state = cs.resolve_credential_state()
        assert state is cs.CredentialState.AWAITING_SETUP

        emitted = _levels_and_texts(loguru_messages)
        loud = [
            (level, text)
            for level, text in emitted
            if level in ("WARNING", "ERROR", "CRITICAL")
        ]
        assert loud, f"an unreadable mode marker must not be debug-only; got {emitted}"
        assert any(_DECRYPT_ERROR in text for _level, text in loud), (
            f"the underlying cause must survive into the message; got {loud}"
        )

    def test_no_placeholder_leaks_into_any_message(
        self, loguru_messages, http_mode_without_env_keys, monkeypatch
    ):
        """Guard the loguru-vs-printf trap that dropped the cause entirely."""
        monkeypatch.setattr(
            cs.PerPluginStore,
            "load",
            lambda self: (_ for _ in ()).throw(RuntimeError(_DECRYPT_ERROR)),
        )

        cs.resolve_credential_state()

        for _level, text in _levels_and_texts(loguru_messages):
            assert "%s" not in text, (
                f"printf placeholder reached the log verbatim: {text!r} -- "
                "loguru formats with str.format, not %-style"
            )


class TestHealthyPathsUnchanged:
    def test_absent_store_still_reports_awaiting_setup_quietly(
        self, loguru_messages, http_mode_without_env_keys, monkeypatch
    ):
        """A fresh install is not a fault and must stay quiet.

        ``PerPluginStore.load()`` returns ``None`` when nothing was ever
        saved, so this path raises nothing and must not warn.
        """
        monkeypatch.setattr(cs.PerPluginStore, "load", lambda self: None)

        import mcp_core

        monkeypatch.setattr(mcp_core, "get_mode", lambda name: None)

        state = cs.resolve_credential_state()

        assert state is cs.CredentialState.AWAITING_SETUP
        loud = [
            (level, text)
            for level, text in _levels_and_texts(loguru_messages)
            if level in ("WARNING", "ERROR", "CRITICAL")
        ]
        assert not loud, f"a fresh install must not warn; got {loud}"

    def test_env_keys_short_circuit_before_touching_the_store(
        self, loguru_messages, monkeypatch
    ):
        """Env-var credentials win and never read the store at all."""
        monkeypatch.setenv("MCP_TRANSPORT", "http")
        monkeypatch.setenv("GEMINI_API_KEY", "set-by-user")

        def _explode(self):
            raise AssertionError("store must not be read when env keys are present")

        monkeypatch.setattr(cs.PerPluginStore, "load", _explode)

        assert cs.resolve_credential_state() is cs.CredentialState.CONFIGURED
