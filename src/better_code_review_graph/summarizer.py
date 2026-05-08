"""LLM summary cache-key derivation + provider env-var detection.

Phase 1 v1.6.x foundation for cached LLM-enhanced node summaries. This
module is intentionally minimal -- it owns the *what to cache under which
key* contract; the actual provider client calls + batching live in later
tasks of the same phase.

Cache key shape: ``"{sha256_hex}:{provider}"``. Switching provider
invalidates the cached summary because the provider tag is part of the
key, even when the source bytes are identical. Pre-computed hashes are
trusted verbatim (the caller has likely already paid the SHA-256 cost
when persisting ``nodes.source_hash`` -- recomputing here is wasteful and
also gives subtle "rehash drift" bugs if the caller passes a normalised
form of the source).

Provider priority: Gemini wins over OpenAI when both keys are set, and
``GOOGLE_API_KEY`` is treated as a Gemini alias. This matches the
embedding backend's Gemini-over-OpenAI sub-ordering in
``embeddings.py`` (full embedding order: jina > gemini > openai >
cohere). Jina + Cohere are intentionally excluded here because they
don't expose chat-completion APIs.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class NodeNeedingSummary:
    """One node candidate for LLM summarization.

    Attributes:
        node_id: Qualified-name primary key (``file_path::name``).
        source_text: Raw function source code that the LLM will summarize.
        source_hash: Optional pre-computed SHA-256 hex digest of
            ``source_text`` -- when provided the cache key trusts it
            verbatim and skips rehashing.
    """

    node_id: str
    source_text: str
    source_hash: str | None


def compute_source_hash(source_text: str) -> str:
    """Return the SHA-256 hex digest of ``source_text`` encoded as UTF-8.

    Pure function, no I/O. ``source_text=""`` is well-defined and returns
    ``hashlib.sha256(b"").hexdigest()``.
    """
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def compute_summary_cache_key(node: NodeNeedingSummary, provider: str) -> str:
    """Derive the LLM-summary cache key for ``node`` under ``provider``.

    Uses ``node.source_hash`` if present (trusted verbatim, no
    recomputation), otherwise hashes ``node.source_text`` on demand.
    Format: ``"{hash}:{provider}"``.
    """
    hash_value = (
        node.source_hash
        if node.source_hash is not None
        else compute_source_hash(node.source_text)
    )
    return f"{hash_value}:{provider}"


def resolve_summary_provider() -> tuple[str, str] | None:
    """Detect the active LLM summary provider from environment variables.

    Returns ``(provider, api_key)`` tuple, or ``None`` if no provider key
    is configured. Empty-string values are treated as "not set" so that
    ``GEMINI_API_KEY=""`` does not yield a broken ``("gemini", "")``
    tuple.

    Priority:
    1. ``GEMINI_API_KEY`` (Gemini, primary)
    2. ``GOOGLE_API_KEY`` (Gemini, alias)
    3. ``OPENAI_API_KEY`` (OpenAI)

    Mirrors the Gemini-over-OpenAI sub-ordering used by
    ``embeddings.py``. Jina + Cohere are intentionally excluded because
    those providers don't expose chat-completion APIs.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if gemini_key:
        return ("gemini", gemini_key)
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return ("openai", openai_key)
    return None
