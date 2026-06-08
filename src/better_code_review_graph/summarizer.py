"""LLM summary cache-key derivation + provider env-var detection + per-node call.

Phase 1 v1.6.x foundation for cached LLM-enhanced node summaries. This
module owns the *what to cache under which key* contract plus the
single-node LLM call that generates a summary; batching + cache lookup
live in later tasks of the same phase.

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

LLM SDK imports (``google-genai``, ``openai``) are deferred into
private ``_get_*_client`` helpers so ``import summarizer`` stays cheap
when only the cache-key helpers are exercised (precommit, T0 smoke).
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Single-node LLM summarization
# ---------------------------------------------------------------------------

_PROMPT_PREFIX = (
    "Write a one-paragraph docstring (max 3 sentences) describing what this function does. "
    "No code, no examples, no markdown. Just the description.\n\n"
    "Source:\n"
)


def _get_gemini_client(api_key: str) -> Any:
    """Return a configured ``google-genai`` client.

    Imported lazily so the SDK isn't loaded for callers that only use
    the cache-key helpers (e.g. precommit smoke tests).
    """
    from google import genai

    return genai.Client(api_key=api_key)


def _get_openai_client(api_key: str) -> Any:
    """Return a configured ``openai`` client.

    Imported lazily so the SDK isn't loaded for callers that only use
    the cache-key helpers (e.g. precommit smoke tests).
    """
    import openai

    return openai.OpenAI(api_key=api_key)


def summarize_node(
    node: NodeNeedingSummary,
    *,
    provider: str,
    api_key: str,
) -> str:
    """Generate a one-paragraph docstring summary for a single node.

    Args:
        node: NodeNeedingSummary with source_text to summarize.
        provider: must be lowercase ("gemini" or "openai") -- matches
            ``resolve_summary_provider()`` return tuple's first element.
            No normalization is performed; the contract is explicit
            lowercase.
        api_key: API credential for the provider.

    Returns:
        The generated summary text, stripped of leading/trailing whitespace.

    Raises:
        ValueError: if provider is not one of {"gemini", "openai"}.
        RuntimeError: if the LLM call fails (wraps the original
            exception), or if the SDK returns an empty/None response
            (e.g. safety filter / content policy block on Gemini, empty
            ``choices`` or ``content=None`` on OpenAI).

    Cost: 1 API call per invocation. The caller is responsible for cache hit/miss
    logic (see compute_summary_cache_key in this module).
    """
    if provider not in {"gemini", "openai"}:
        raise ValueError(
            f"Unsupported provider: {provider!r} (expected 'gemini' or 'openai')"
        )

    # Concatenate rather than .format() so source code containing literal
    # ``{`` / ``}`` (dict literals, f-strings, JSX) does not blow up
    # ``str.format`` with KeyError/IndexError. Only one substitution slot
    # exists, so concatenation is the cleaner contract.
    prompt = _PROMPT_PREFIX + node.source_text

    if provider == "gemini":
        try:
            client = _get_gemini_client(api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
        except Exception as exc:
            raise RuntimeError(f"summarize_node failed via {provider}: {exc}") from exc
        text = response.text
        if not text or not text.strip():
            raise RuntimeError(
                f"summarize_node: gemini returned empty/None text "
                f"(likely safety filter or content policy block) for node {node.node_id}"
            )
        return text.strip()

    # provider == "openai"
    try:
        client = _get_openai_client(api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        raise RuntimeError(f"summarize_node failed via {provider}: {exc}") from exc
    if not response.choices:
        raise RuntimeError(
            f"summarize_node: openai returned no choices for node {node.node_id}"
        )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError(
            f"summarize_node: openai returned empty/None content "
            f"(likely safety filter) for node {node.node_id}"
        )
    return content.strip()


# ---------------------------------------------------------------------------
# Batch orchestration (Task 5)
# ---------------------------------------------------------------------------

# Default cap on per-run LLM calls. Override per-call via the max_nodes parameter.
DEFAULT_MAX_NODES_PER_RUN = 500


@dataclass(frozen=True)
class BatchSummarizeResult:
    """Outcome counts from a batch_summarize run."""

    generated: int  # nodes whose summary was newly generated this run
    cached: int  # nodes whose stored summary was still valid (cache hit)
    skipped_no_provider: bool = False  # True iff no provider env var was set
    provider: str | None = None  # provider used (None if skipped)
    errors: int = 0  # nodes where summarize_node raised; counted but logged + skipped


def batch_summarize(
    store: Any, *, max_nodes: int = DEFAULT_MAX_NODES_PER_RUN
) -> BatchSummarizeResult:
    """Generate summaries for Function nodes that lack a current cache entry.

    Iteration scope: at most ``max_nodes`` Function-kind nodes whose
    ``source_text`` is non-null. For each candidate:

    - If stored summary + ``summary_provider`` + ``source_hash`` all match
      the live provider + freshly-computed source hash, it's a cache hit
      and we skip.
    - Otherwise call :func:`summarize_node` and persist via
      :meth:`GraphStore.update_summary`.

    Errors from :func:`summarize_node` are logged via the module logger and
    counted in :class:`BatchSummarizeResult.errors`; the batch continues so
    a single transient provider hiccup doesn't kill an entire run. Caller
    can re-run later — failed nodes will retry next time because their
    stored ``source_hash`` still doesn't match the live one.

    Returns counts. No-op (``skipped_no_provider=True``) when no provider
    env var is configured.
    """
    if max_nodes < 1:
        raise ValueError(f"max_nodes must be >= 1, got {max_nodes}")

    resolved = resolve_summary_provider()
    if resolved is None:
        return BatchSummarizeResult(
            generated=0,
            cached=0,
            skipped_no_provider=True,
            provider=None,
            errors=0,
        )
    provider, api_key = resolved

    cursor = store._conn.execute(
        "SELECT id, source_text, source_hash, summary, summary_provider FROM nodes "
        "WHERE kind='Function' AND source_text IS NOT NULL LIMIT ?",
        (max_nodes,),
    )

    generated = 0
    cached = 0
    errors = 0

    for row in cursor:
        row_id = row[0]
        src = row[1]
        stored_hash = row[2]
        stored_summary = row[3]
        stored_provider = row[4]

        live_hash = compute_source_hash(src)

        if stored_summary and stored_hash == live_hash and stored_provider == provider:
            cached += 1
            continue

        try:
            summary = summarize_node(
                NodeNeedingSummary(
                    node_id=str(row_id),
                    source_text=src,
                    source_hash=live_hash,
                ),
                provider=provider,
                api_key=api_key,
            )
        except Exception as exc:
            logger.warning("summarize_node failed for id=%d: %s", row_id, exc)
            errors += 1
            continue

        store.update_summary(
            row_id,
            summary=summary,
            provider=provider,
            source_hash=live_hash,
        )
        generated += 1

    return BatchSummarizeResult(
        generated=generated,
        cached=cached,
        skipped_no_provider=False,
        provider=provider,
        errors=errors,
    )
