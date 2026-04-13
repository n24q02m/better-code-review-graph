"""Non-blocking credential state management for better-code-review-graph.

State machine: awaiting_setup -> setup_in_progress -> (configured | local)
Reset: configured/local -> awaiting_setup (via setup tool)

CRG has a local fallback (qwen3-embed ONNX) so all tools work without
cloud credentials. Cloud keys are optional enhancements.
"""

from __future__ import annotations

import os
from enum import Enum

from loguru import logger

SERVER_NAME = "better-code-review-graph"
DEFAULT_RELAY_URL = "https://better-code-review-graph.n24q02m.com"

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
_state = CredentialState.AWAITING_SETUP
_setup_url: str | None = None


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

    # 1. Check env vars
    if any(os.environ.get(k) for k in CLOUD_KEYS):
        logger.info("Cloud API keys found in environment")
        _state = CredentialState.CONFIGURED
        return _state

    # 2. Check config file
    try:
        from mcp_core.storage.config_file import read_config

        saved = read_config(SERVER_NAME)
        if saved and any(saved.get(k) for k in CLOUD_KEYS):
            # Apply to env vars
            for key, value in saved.items():
                if value and key not in os.environ:
                    os.environ[key] = value
            logger.info("Config loaded from encrypted file")
            _state = CredentialState.CONFIGURED
            # Propagate shared cloud keys to sibling servers on every startup
            _share_cloud_keys_to_peers(saved)
            return _state
    except Exception:
        pass

    # 3. Check local mode marker
    try:
        from mcp_core import get_mode

        mode = get_mode(SERVER_NAME)
        if mode == "local":
            logger.info("Local mode marker found, skipping relay")
            _state = CredentialState.LOCAL
            return _state
    except Exception:
        pass

    # 4. Nothing found
    logger.info("No credentials found -- server starting in awaiting_setup mode")
    _state = CredentialState.AWAITING_SETUP
    return _state


async def trigger_relay_setup(
    *, force: bool = False, timeout: float | None = None
) -> str | None:
    """Start relay session (lazy trigger). Returns setup URL or None.

    Uses SessionLock to reuse existing sessions across parallel processes.
    Tries to open browser automatically.
    Does NOT block -- returns URL immediately for the tool to include in response.
    """
    global _state, _setup_url

    if not force and _state not in (CredentialState.AWAITING_SETUP,):
        return _setup_url

    _state = CredentialState.SETUP_IN_PROGRESS

    try:
        # Check for existing session via lock
        from mcp_core import acquire_session_lock

        existing = await acquire_session_lock(SERVER_NAME)
        if existing:
            _setup_url = existing.relay_url
            logger.info("Reusing existing relay session")
            return _setup_url

        # Create new session
        from mcp_core.relay.client import create_session

        from better_code_review_graph.relay_schema import RELAY_SCHEMA

        relay_base = os.environ.get("MCP_RELAY_URL", DEFAULT_RELAY_URL)
        session = await create_session(relay_base, SERVER_NAME, RELAY_SCHEMA)  # ty: ignore[invalid-argument-type]

        # Save session lock for parallel processes
        import time

        from mcp_core import SessionInfo, write_session_lock

        await write_session_lock(
            SERVER_NAME,
            SessionInfo(
                session_id=session.session_id,
                relay_url=session.relay_url,
                created_at=time.time(),
            ),
        )

        _setup_url = session.relay_url

        # Try to open browser (best-effort)
        from mcp_core import try_open_browser

        try_open_browser(session.relay_url)

        logger.info("Relay session created: {}", session.relay_url)

        # Start background poll task (non-blocking)
        import asyncio

        asyncio.create_task(_poll_relay_background(relay_base, session, timeout))

        return _setup_url

    except Exception as e:
        logger.debug("Relay setup failed: {}. Server continues in awaiting_setup.", e)
        _state = CredentialState.AWAITING_SETUP
        return None


async def _poll_relay_background(
    relay_base: str, session: object, timeout: float | None
) -> None:
    """Background task that polls relay and applies config when user submits."""
    global _state
    try:
        from mcp_core.relay.client import poll_for_result
        from mcp_core.storage.config_file import write_config

        poll_timeout = timeout if timeout is not None else 300.0
        config = await poll_for_result(relay_base, session, timeout_s=poll_timeout)  # ty: ignore[invalid-argument-type]

        # Save config
        write_config(SERVER_NAME, config)

        # Apply to env
        for key, value in config.items():
            if value and key not in os.environ:
                os.environ[key] = value

        _state = CredentialState.CONFIGURED
        logger.info("Relay config applied successfully")

        # Share cloud keys with wet-mcp and mnemo-mcp peers
        _share_cloud_keys_to_peers(config)

        # Notify browser: setup complete (CRG has no GDrive OAuth step)
        session_id = getattr(session, "session_id", None)
        if session_id:
            try:
                from mcp_core.relay.client import send_message

                await send_message(
                    relay_base,
                    session_id,
                    {
                        "type": "complete",
                        "text": "Setup complete! Cloud embedding configured. You can close this tab.",
                    },
                )
            except Exception:
                pass

        # Release session lock
        from mcp_core import release_session_lock

        await release_session_lock(SERVER_NAME)

    except RuntimeError as e:
        if "RELAY_SKIPPED" in str(e):
            _state = CredentialState.LOCAL
            try:
                from mcp_core import set_local_mode

                set_local_mode(SERVER_NAME)
            except Exception:
                pass
        else:
            _state = CredentialState.AWAITING_SETUP
    except Exception:
        _state = CredentialState.AWAITING_SETUP


def _share_cloud_keys_to_peers(config: dict[str, str]) -> None:
    """Write shared cloud API keys to wet-mcp and mnemo-mcp config files."""
    try:
        from mcp_core.storage.config_file import write_config

        shared = {k: v for k, v in config.items() if k in CLOUD_KEYS and v}
        if not shared:
            return
        for peer in ("wet-mcp", "mnemo-mcp"):
            try:
                write_config(peer, shared)
                logger.debug("Shared cloud keys to {}", peer)
            except Exception as e:
                logger.debug("Failed to share keys to {}: {}", peer, e)
    except Exception as e:
        logger.debug("_share_cloud_keys_to_peers failed (non-fatal): {}", e)


def save_credentials(config: dict[str, str]) -> dict | None:
    """Save credentials from OAuth form to config.enc and apply to environment.

    Called by the local OAuth AS when the user submits API keys via the
    browser form. Returns optional dict with next_step info.
    """
    global _state

    from mcp_core.storage.config_file import write_config

    from better_code_review_graph.relay_setup import apply_config

    write_config(SERVER_NAME, config)
    apply_config(config)
    _state = CredentialState.CONFIGURED
    logger.info("Credentials saved via local OAuth form")

    _share_cloud_keys_to_peers(config)
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
    try:
        from mcp_core import clear_mode
        from mcp_core.storage.config_file import delete_config

        clear_mode(SERVER_NAME)
        delete_config(SERVER_NAME)
    except Exception:
        pass
