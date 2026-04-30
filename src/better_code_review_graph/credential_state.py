"""Non-blocking credential state management for better-code-review-graph.

State machine: awaiting_setup -> setup_in_progress -> (configured | local)
Reset: configured/local -> awaiting_setup (via setup tool).

CRG has a local fallback (qwen3-embed ONNX) so all tools work without
cloud credentials. Cloud keys are optional enhancements.

When no credentials are present, ``trigger_relay_setup`` spawns a LOCAL
HTTP credential form on ``http://127.0.0.1:<random>`` via
``mcp_core.start_local_server_background`` with the CRG relay schema.
The user pastes API keys into that local form; ``save_credentials``
persists to ``~/.better-code-review-graph-mcp/config.json`` via
``PerPluginStore``.

This fallback is LOCAL-ONLY. We never hit the remote relay URL here --
that is reserved for explicit ``MCP_MODE`` HTTP deployments. See
``~/.claude/skills/mcp-dev/references/mode-matrix.md`` section
``stdio proxy`` for the canonical rule.

Migrated from mcp_core.storage.config_file (shared config.enc) to
mcp_core.storage.per_plugin_store (per-plugin encrypted store) for
trust model alignment per spec 2026-04-30-trust-model-alignment.md.
"""

from __future__ import annotations

import asyncio
import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger
from mcp_core.storage.per_plugin_store import PerPluginStore

SERVER_NAME = "better-code-review-graph"
PLUGIN_NAME = "better-code-review-graph"

# Grace window so the browser renders "Setup complete!" before the local spawn closes.
_SPAWN_CLEANUP_S = 5.0

CLOUD_KEYS = [
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "JINA_AI_API_KEY",
    "OPENAI_API_KEY",
    "COHERE_API_KEY",
    "CO_API_KEY",
]


class CredentialState(Enum):
    AWAITING_SETUP = "awaiting_setup"
    SETUP_IN_PROGRESS = "setup_in_progress"
    CONFIGURED = "configured"
    LOCAL = "local"


# Module-level state
_state: CredentialState = CredentialState.AWAITING_SETUP
_setup_url: str | None = None
_active_handle: Any | None = None  # LocalServerHandle


def get_state() -> CredentialState:
    """Return current credential state."""
    return _state


def get_setup_url() -> str | None:
    """Return current relay setup URL (if any)."""
    return _setup_url


def resolve_credential_state() -> CredentialState:
    """Fast, synchronous credential check. Called during lifespan startup.

    Checks (in order):
    1. ENV VARS -- if any CLOUD_KEYS present, state = CONFIGURED
    2. CONFIG FILE -- if saved config has cloud keys, apply to env, state = CONFIGURED
    3. LOCAL MODE MARKER -- if user explicitly skipped, state = LOCAL
    4. NOTHING -- state = AWAITING_SETUP (server starts fast, relay triggered lazily)

    Returns new state. Takes <10ms.
    """
    global _state

    if any(os.environ.get(k) for k in CLOUD_KEYS):
        logger.info("Cloud API keys found in environment")
        _state = CredentialState.CONFIGURED
        return _state

    try:
        saved = PerPluginStore(PLUGIN_NAME).load()
        if saved and any(saved.get(k) for k in CLOUD_KEYS):
            for key, value in saved.items():
                if value and key not in os.environ:
                    os.environ[key] = value
            logger.info("Config loaded from encrypted per-plugin store")
            _state = CredentialState.CONFIGURED
            return _state
    except Exception:
        pass

    try:
        from mcp_core import get_mode

        mode = get_mode(SERVER_NAME)
        if mode == "local":
            logger.info("Local mode marker found, skipping relay")
            _state = CredentialState.LOCAL
            return _state
    except Exception:
        pass

    logger.info("No credentials found -- server starting in awaiting_setup mode")
    _state = CredentialState.AWAITING_SETUP
    return _state


async def _close_active_handle() -> None:
    """Best-effort close of the module-level local credential-form handle."""
    global _active_handle

    handle = _active_handle
    _active_handle = None
    if handle is None:
        return
    try:
        await handle.close()
    except Exception:  # pragma: no cover - best-effort cleanup, hard to fault-inject
        logger.opt(exception=True).debug(
            "Best-effort close of credential-form handle failed"
        )


def _schedule_spawn_cleanup(grace_s: float = _SPAWN_CLEANUP_S) -> None:
    """Schedule detached cleanup of the local credential-form spawn."""
    if _active_handle is None:
        return

    async def _delayed_close() -> None:  # pragma: no cover - timer-based detached task
        try:
            await asyncio.sleep(grace_s)
            await _close_active_handle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.opt(exception=True).debug("Delayed spawn cleanup failed")

    try:  # pragma: no cover - detached task scheduling
        task = asyncio.create_task(_delayed_close())
        task.add_done_callback(lambda _t: None)
    except RuntimeError:
        pass


async def trigger_relay_setup(
    *,
    force: bool = False,
    timeout: float | None = None,  # noqa: ARG001
) -> str | None:
    """Spawn a local credential form (stdio fallback) and return its URL.

    The spawn is LOCAL ONLY -- ``mcp_core.start_local_server_background``
    binds ``127.0.0.1:<random>`` and renders the CRG relay schema in a
    browser form. ``timeout`` is accepted for backward compatibility but
    unused.
    """
    global _state, _setup_url, _active_handle

    if not force and _state not in (CredentialState.AWAITING_SETUP,):
        return _setup_url

    if _active_handle is not None and _setup_url:
        _state = CredentialState.SETUP_IN_PROGRESS
        return _setup_url

    _state = CredentialState.SETUP_IN_PROGRESS

    try:
        from fastmcp import FastMCP
        from mcp_core import start_local_server_background, try_open_browser

        from better_code_review_graph.relay_schema import RELAY_SCHEMA

        stub_mcp = FastMCP(f"{SERVER_NAME}-setup")

        handle = await start_local_server_background(
            stub_mcp,
            server_name=SERVER_NAME,
            relay_schema=RELAY_SCHEMA,
            port=0,
            host="127.0.0.1",
            on_credentials_saved=save_credentials,
        )

        _active_handle = handle
        _setup_url = f"http://{handle.host}:{handle.port}/"

        try_open_browser(_setup_url)

        logger.info("Local credential form ready at {}", _setup_url)
        return _setup_url

    except Exception as e:
        logger.debug("Relay setup failed: {}. Server continues in awaiting_setup.", e)
        _state = CredentialState.AWAITING_SETUP
        await _close_active_handle()
        _setup_url = None
        return None


def _sub_data_dir(sub: str) -> Path:
    """Return per-JWT-sub data directory (creates if missing).

    Used in multi-user remote mode where ``PUBLIC_URL`` is set. Each JWT
    ``sub`` gets its own scope for ``config.json`` (cloud API keys) and
    ``graph.db`` (per-user code knowledge graph) so credentials and graph
    state never leak across users sharing the same deployment.
    """
    base = Path(os.environ.get("CRG_DATA_DIR", str(Path.home() / ".crg")))
    d = base / "subs" / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path_for_sub(sub: str) -> Path:
    """Return per-sub graph.db path for multi-user remote mode."""
    return _sub_data_dir(sub) / "graph.db"


def store_for_sub(sub: str, config: dict[str, str]) -> None:
    """Persist a sub's credential config to ``<data>/subs/<sub>/config.json``."""
    (_sub_data_dir(sub) / "config.json").write_text(json.dumps(config))


def read_for_sub(sub: str) -> dict[str, str]:
    """Read a sub's credential config; returns ``{}`` if absent."""
    p = _sub_data_dir(sub) / "config.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_credentials(
    config: dict[str, str], context: dict[str, str] | None = None
) -> dict | None:
    """Save credentials from OAuth form and apply to environment.

    Single-user mode (default, ``PUBLIC_URL`` unset): writes to the shared
    ``config.enc`` on the host -- one set of cloud API keys for one user.

    Multi-user remote mode (``PUBLIC_URL`` set): scopes credentials by the
    per-authorize JWT ``sub`` from ``context``. Each user's keys land in
    ``<CRG_DATA_DIR>/subs/<sub>/config.json`` so credentials never leak
    across users. Refuses to persist if ``sub`` missing.

    Called by the local OAuth AS when the user submits API keys via the
    browser form. Returns optional dict with next_step info (always None
    for CRG -- no multi-step flow).
    """
    global _state

    if os.environ.get("PUBLIC_URL"):
        sub = context.get("sub") if context else None
        if not sub:
            raise RuntimeError(
                "multi-user mode: SubjectContext sub required to save credentials"
            )
        store_for_sub(sub, config)
        _state = CredentialState.CONFIGURED
        logger.info("Credentials saved for sub={} via remote OAuth form", sub)
        _schedule_spawn_cleanup()
        return None

    from better_code_review_graph.relay_setup import apply_config

    PerPluginStore(PLUGIN_NAME).save(config)
    apply_config(config)
    _state = CredentialState.CONFIGURED
    logger.info("Credentials saved via local OAuth form")

    # Cloud-only setup is done -- schedule local spawn cleanup so the browser
    # renders "Setup complete!" then the local server closes.
    _schedule_spawn_cleanup()
    return None


def set_state(state: CredentialState) -> None:
    """For testing and setup tool actions."""
    global _state
    _state = state


def reset_state() -> None:
    """Reset to awaiting_setup (used by setup reset action)."""
    global _state, _setup_url
    _state = CredentialState.AWAITING_SETUP
    _setup_url = None

    # Close any active local credential-form spawn; fire-and-forget so callers
    # don't need to be async.
    if _active_handle is not None:  # pragma: no cover - detached task scheduling
        try:
            task = asyncio.create_task(_close_active_handle())
            task.add_done_callback(lambda _t: None)
        except RuntimeError:
            pass

    try:
        from mcp_core import clear_mode

        clear_mode(SERVER_NAME)
        PerPluginStore(PLUGIN_NAME).clear()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Simple load/save/clear helpers (thin wrappers over PerPluginStore)
# ---------------------------------------------------------------------------


def load_credentials(sub: str | None = None) -> dict:
    """Load credentials from per-plugin store. Returns empty dict if absent."""
    return PerPluginStore(PLUGIN_NAME, sub).load() or {}


def clear_credentials(sub: str | None = None) -> None:
    """Remove credentials from per-plugin store."""
    PerPluginStore(PLUGIN_NAME, sub).clear()
