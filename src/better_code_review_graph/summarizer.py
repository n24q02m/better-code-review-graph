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

LLM dispatch goes through ``mcp_core.llm.completion`` (litellm
passthrough). The litellm import is deferred into ``summarize_node`` so
``import summarizer`` stays cheap when only the cache-key helpers are
exercised (precommit, T0 smoke).
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

# Default litellm ``provider/model`` per summary provider. Overridable via the
# ``SUMMARY_MODEL`` env var (used verbatim when set).
_DEFAULT_SUMMARY_MODELS: dict[str, str] = {
    "gemini": "gemini/gemini-2.5-flash",
    "openai": "gpt-4o-mini",
}


def _provider_from_model(model: str) -> str:
    """Derive the cache-key provider tag from a litellm model string.

    Used so a ``SUMMARY_MODEL`` override still produces a stable
    ``{hash}:{provider}`` cache key. The provider prefix (text before the
    first ``/``) is matched first; bare OpenAI-style names (e.g.
    ``gpt-4o-mini``) default to ``openai``.
    """
    if "/" in model:
        prefix = model.split("/", 1)[0].lower()
        if prefix in ("gemini", "google"):
            return "gemini"
        if prefix == "openai":
            return "openai"
        return prefix
    # Bare names with no provider prefix are OpenAI-style (e.g. gpt-4o-mini).
    return "openai"


def summarize_node(
    node: NodeNeedingSummary,
    *,
    provider: str,
    api_key: str | None,
    model: str | None = None,
) -> str:
    """Generate a one-paragraph docstring summary for a single node.

    Dispatches through ``mcp_core.llm.completion`` (litellm passthrough).

    Model resolution:
    - When ``model`` is passed explicitly (a litellm ``provider/model``
      override), it is used verbatim. Routing is carried by the model
      string, so the ``provider`` value is only a label and is *not*
      validated against {"gemini", "openai"}.
    - When ``model`` is ``None``, the per-provider default in
      :data:`_DEFAULT_SUMMARY_MODELS` is used and ``provider`` MUST be one
      of {"gemini", "openai"}.

    Args:
        node: NodeNeedingSummary with source_text to summarize.
        provider: lowercase provider label. In the default-model path it
            selects the model and must be "gemini" or "openai" (matches
            ``resolve_summary_provider()``); in the explicit-``model`` path
            it is purely a label for error messages.
        api_key: API credential for the provider, or ``None`` to let
            litellm resolve the provider's key from the environment.
        model: optional explicit litellm ``provider/model`` override. When
            set, skips the per-provider default lookup and the provider
            allowlist guard.

    Returns:
        The generated summary text, stripped of leading/trailing whitespace.

    Raises:
        ValueError: in the default-model path only, if provider is not one
            of {"gemini", "openai"}.
        RuntimeError: if the LLM call fails (wraps the original
            exception), or if litellm returns an empty/None response
            (e.g. safety filter / content policy block, empty ``choices``
            or ``content=None``).

    Cost: 1 API call per invocation. The caller is responsible for cache hit/miss
    logic (see compute_summary_cache_key in this module).
    """
    if model is None:
        if provider not in {"gemini", "openai"}:
            raise ValueError(
                f"Unsupported provider: {provider!r} (expected 'gemini' or 'openai')"
            )
        model = _DEFAULT_SUMMARY_MODELS[provider]

    # Concatenate rather than .format() so source code containing literal
    # ``{`` / ``}`` (dict literals, f-strings, JSX) does not blow up
    # ``str.format`` with KeyError/IndexError. Only one substitution slot
    # exists, so concatenation is the cleaner contract.
    prompt = _PROMPT_PREFIX + node.source_text

    # Lazy import: litellm costs ~1-2s on first import.
    from mcp_core.llm import completion

    try:
        # Normalise empty string to None: mcp_core.llm forwards a non-None
        # api_key to litellm, which suppresses provider env-var fallback (401).
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_base=os.environ.get("LLM_API_BASE") or None,
            api_key=api_key or None,
        )
    except Exception as exc:
        raise RuntimeError(f"summarize_node failed via {provider}: {exc}") from exc

    if not response.choices:
        raise RuntimeError(
            f"summarize_node: {provider} returned no choices for node {node.node_id}"
        )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError(
            f"summarize_node: {provider} returned empty/None content "
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

    # SUMMARY_MODEL override: the model string carries litellm routing, so it
    # may target a different provider than the env-resolved one. In that case
    # (a) the cache tag is derived from the model prefix (so switching models
    # invalidates stale summaries), and (b) the env-resolved api_key is dropped
    # to None — it belongs to ``provider``, not the override's provider, and
    # forwarding it would 401. ``api_key=None`` lets litellm resolve the
    # correct key from the environment for the override's provider.
    override_model = os.environ.get("SUMMARY_MODEL")
    if override_model:
        cache_provider = _provider_from_model(override_model)
        effective_api_key: str | None = None
    else:
        cache_provider = provider
        effective_api_key = api_key

    rows = store._conn.execute(
        "SELECT id, source_text, source_hash, summary, summary_provider FROM nodes "
        "WHERE kind='Function' AND source_text IS NOT NULL LIMIT ?",
        (max_nodes,),
    ).fetchall()

    generated = 0
    cached = 0
    errors = 0

    for row in rows:
        row_id = row[0]
        src = row[1]
        stored_hash = row[2]
        stored_summary = row[3]
        stored_provider = row[4]

        live_hash = compute_source_hash(src)

        if (
            stored_summary
            and stored_hash == live_hash
            and stored_provider == cache_provider
        ):
            cached += 1
            continue

        try:
            summary = summarize_node(
                NodeNeedingSummary(
                    node_id=str(row_id),
                    source_text=src,
                    source_hash=live_hash,
                ),
                provider=cache_provider,
                api_key=effective_api_key,
                model=override_model,
            )
        except Exception as exc:
            logger.warning("summarize_node failed for id=%d: %s", row_id, exc)
            errors += 1
            continue

        store.update_summary(
            row_id,
            summary=summary,
            provider=cache_provider,
            source_hash=live_hash,
        )
        generated += 1

    return BatchSummarizeResult(
        generated=generated,
        cached=cached,
        skipped_no_provider=False,
        provider=cache_provider,
        errors=errors,
    )
