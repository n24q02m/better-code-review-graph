"""Zero-env-config relay setup flow.

When no env vars or config file are found, triggers the relay page setup
to collect credentials from the user via a browser-based form.
"""

from __future__ import annotations

import logging
import os
import sys

from mcp_relay_core.relay.client import create_session, poll_for_result
from mcp_relay_core.storage.config_file import write_config
from mcp_relay_core.storage.resolver import resolve_config

from .relay_schema import RELAY_SCHEMA

logger = logging.getLogger(__name__)

SERVER_NAME = "better-code-review-graph"
DEFAULT_RELAY_URL = "https://relay.n24q02m.com"
REQUIRED_FIELDS = ["GEMINI_API_KEY"]


async def ensure_config() -> dict[str, str] | None:
    """Resolve config or trigger relay setup.

    Resolution order:
    1. Environment variables (GEMINI_API_KEY)
    2. Encrypted config file (~/.config/mcp/config.enc)
    3. Relay setup (browser-based form via relay server)

    Returns:
        Config dict with credential keys, or None if setup fails/times out.
    """
    # 1. Check env vars directly (fast path)
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        logger.info("GEMINI_API_KEY found in environment")
        return {"GEMINI_API_KEY": api_key}

    # 2. Check config file via resolver
    result = resolve_config(SERVER_NAME, REQUIRED_FIELDS)
    if result.config is not None:
        logger.info("Config loaded from %s", result.source)
        # Inject into environment for downstream consumers
        for key, value in result.config.items():
            os.environ.setdefault(key, value)
        return result.config

    # 3. No config found -- trigger relay setup
    logger.info("No credentials found. Starting relay setup...")

    relay_url = DEFAULT_RELAY_URL
    try:
        session = await create_session(relay_url, SERVER_NAME, RELAY_SCHEMA)
    except Exception:
        logger.warning(
            "Cannot reach relay server at %s. "
            "Set GEMINI_API_KEY environment variable manually.",
            relay_url,
        )
        return None

    # Log URL to stderr (visible to user in MCP client)
    print(
        f"\nSetup required. Open this URL to configure:\n{session.relay_url}\n",
        file=sys.stderr,
        flush=True,
    )

    # Poll for result
    try:
        config = await poll_for_result(relay_url, session)
    except RuntimeError:
        logger.error("Relay setup timed out or session expired")
        return None

    # Save to config file
    write_config(SERVER_NAME, config)
    logger.info("Config saved successfully")

    # Inject into environment
    for key, value in config.items():
        os.environ.setdefault(key, value)

    return config
