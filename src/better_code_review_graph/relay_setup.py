"""Relay-first setup flow for better-code-review-graph.

Always shows the relay URL at startup so users can configure cloud embedding
providers via browser. If the user skips or relay is unreachable, falls back
to local ONNX mode (qwen3-embed, works without any credentials).

Resolution order:
1. Environment variables (GEMINI_API_KEY etc.)
2. Encrypted config file (~/.config/mcp/config.enc)
3. Relay setup (browser-based form, 30s timeout for optional-cred server)
4. Local mode fallback (qwen3-embed ONNX)
"""

from __future__ import annotations

import logging
import os
import sys

from .relay_schema import RELAY_SCHEMA

logger = logging.getLogger(__name__)

SERVER_NAME = "better-code-review-graph"
DEFAULT_RELAY_URL = "https://relay.n24q02m.com"
REQUIRED_FIELDS = ["GEMINI_API_KEY"]

# Cloud API keys that indicate user has env vars configured
CLOUD_KEYS = [
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "JINA_AI_API_KEY",
    "OPENAI_API_KEY",
    "COHERE_API_KEY",
    "CO_API_KEY",
]

# Shorter timeout for optional-credential servers (user can skip)
RELAY_TIMEOUT_S = 30.0


async def ensure_config() -> dict[str, str] | None:
    """Resolve config: env vars -> config file -> relay setup -> local fallback.

    Always shows relay URL at startup for relay-first design.
    Uses 30s timeout since CRG works locally without credentials.

    Returns:
        Config dict with credential keys, or None if skipped/failed (local mode).
    """
    # 1. Check env vars directly (fast path)
    if any(os.environ.get(k) for k in CLOUD_KEYS):
        logger.info("Cloud API keys found in environment")
        return None  # env vars take priority, no relay needed

    # 2. Check config file via resolver
    try:
        from mcp_relay_core.storage.resolver import resolve_config

        result = resolve_config(SERVER_NAME, REQUIRED_FIELDS)
        if result.config is not None:
            logger.info("Config loaded from %s", result.source)
            # Inject into environment for downstream consumers
            for key, value in result.config.items():
                os.environ.setdefault(key, value)
            return result.config
    except Exception:
        pass

    # 3. Always trigger relay setup (relay-first design)
    logger.info("No credentials found. Starting relay setup...")

    relay_url = DEFAULT_RELAY_URL
    try:
        from mcp_relay_core.relay.client import create_session

        session = await create_session(relay_url, SERVER_NAME, RELAY_SCHEMA)
    except Exception:
        logger.debug("Cannot reach relay server at %s. Using local mode.", relay_url)
        return None

    # Log URL to stderr (visible to user in MCP client)
    print(
        f"\nConfigure cloud embedding (optional, 30s timeout):"
        f"\n{session.relay_url}"
        f"\nSkip to use local mode (qwen3-embed ONNX).\n",
        file=sys.stderr,
        flush=True,
    )

    # Poll for result with shorter timeout
    try:
        from mcp_relay_core.relay.client import poll_for_result
        from mcp_relay_core.storage.config_file import write_config

        config = await poll_for_result(relay_url, session, timeout_s=RELAY_TIMEOUT_S)

        # Save to config file
        write_config(SERVER_NAME, config)
        logger.info("Config saved successfully")

        # Inject into environment
        for key, value in config.items():
            os.environ.setdefault(key, value)

        return config

    except RuntimeError as e:
        if "RELAY_SKIPPED" in str(e):
            logger.info("Relay setup skipped by user. Using local mode.")
        elif "timed out" in str(e).lower():
            logger.info("Relay setup timed out. Using local mode.")
        else:
            logger.debug("Relay setup ended: %s", e)
        return None
