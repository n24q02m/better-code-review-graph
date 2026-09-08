"""Request-scoped LLM summaries, cached by source hash and selected model.

Only the first explicit ``SUMMARY_MODELS`` entry runs; no implicit paid model
or cross-provider fallback is selected from available keys. An empty selection
disables summaries. The full selected model is persisted in ``summary_provider``
so switching models within one provider invalidates the cached summary.

LLM dispatch goes through ``mcp_core.llm.completion`` (litellm
passthrough). The litellm import is deferred into ``summarize_node`` so
``import summarizer`` stays cheap when only the cache-key helpers are
exercised (precommit, T0 smoke).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from mcp_core.llm.providers import provider_of_model

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


def resolve_summary_chain() -> list[str]:
    """Configured summary models in selection order; only the first is used.

    Empty -> summaries disabled. Legacy ``SUMMARY_MODEL`` honored one release
    (warning). Provider keys alone do not select a completion model.

    Request-scoped: ``SUMMARY_MODELS`` / ``SUMMARY_MODEL`` come from the bound
    JWT sub's per-sub bucket in HTTP
    multi-user mode, falling back to ``os.environ`` in stdio/single-user
    mode. Per-sub model selection must not leak across concurrent users.
    """
    from .credential_state import config_value_for_current_request

    explicit = (config_value_for_current_request("SUMMARY_MODELS") or "").strip()
    if explicit:
        return [m.strip() for m in explicit.split(",") if m.strip()]
    legacy = (config_value_for_current_request("SUMMARY_MODEL") or "").strip()
    if legacy:
        logger.warning(
            "Deprecated SUMMARY_MODEL honored; migrate to SUMMARY_MODELS "
            "(removed next release)."
        )
        return [legacy]
    return []


# ---------------------------------------------------------------------------
# Single-node LLM summarization
# ---------------------------------------------------------------------------

_PROMPT_PREFIX = (
    "Write a one-paragraph docstring (max 3 sentences) describing what this function does. "
    "No code, no examples, no markdown. Just the description.\n\n"
    "Source:\n"
)


def summarize_node(
    node: NodeNeedingSummary,
    *,
    provider: str,
    api_key: str | None,
    model: str | None = None,
) -> str:
    """Generate a one-paragraph docstring summary for a single node.

    Dispatches through ``mcp_core.llm.completion`` (litellm passthrough).

    ``model`` must be explicitly selected by the caller. ``provider`` is only
    an error label, never a selector. In a bound subject context, the subject's
    key overrides the argument; an absent key fails closed. Stdio callers may
    supply their own key or let the provider resolve its environment credential.

    Returns:
        The generated summary text, stripped of leading/trailing whitespace.

    Raises:
        ValueError: if no model is selected or the current subject lacks its key.
        RuntimeError: if the LLM call fails (wraps the original
            exception), or if litellm returns an empty/None response
            (e.g. safety filter / content policy block, empty ``choices``
            or ``content=None``).

    Cost: 1 API call per invocation. The caller is responsible for cache hit/miss
    logic (see compute_summary_cache_key in this module).
    """
    if not model:
        raise ValueError("Summary generation requires an explicit model")

    # Concatenate rather than .format() so source code containing literal
    # ``{`` / ``}`` (dict literals, f-strings, JSX) does not blow up
    # ``str.format`` with KeyError/IndexError. Only one substitution slot
    # exists, so concatenation is the cleaner contract.
    prompt = _PROMPT_PREFIX + node.source_text

    # Lazy import: litellm costs ~1-2s on first import.
    from mcp_core.llm import completion

    from .credential_state import config_value_for_current_request, get_current_sub

    if get_current_sub() is not None:
        from mcp_core.llm.providers import key_env_for_model

        key_env = key_env_for_model(model)
        api_key = config_value_for_current_request(key_env)
        if not api_key and key_env == "GEMINI_API_KEY":
            api_key = config_value_for_current_request("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "Summary generation requires a provider key for the current subject"
            )

    try:
        # Resolve the custom endpoint request-scoped (per-sub bucket in HTTP
        # multi-user, os.environ in stdio/single-user) via the same accessor
        # the caller uses for the key, so one sub's gateway URL never serves
        # another. Reading os.environ here would make the per-sub endpoint a
        # silent no-op in multi-user mode. SSRF-vetted downstream in dispatch.
        # Normalise empty string to None: mcp_core.llm forwards a non-None
        # api_key to litellm, which suppresses provider env-var fallback (401).
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_base=config_value_for_current_request("LLM_API_BASE") or None,
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
    skipped_no_provider: bool = False  # True iff no summary model was selected
    provider: str | None = None  # provider used (None if skipped)
    errors: int = 0  # nodes where summarize_node raised; counted but logged + skipped


def batch_summarize(
    store: Any, *, max_nodes: int = DEFAULT_MAX_NODES_PER_RUN
) -> BatchSummarizeResult:
    """Generate summaries for Function nodes that lack a current cache entry.

    Iteration scope: at most ``max_nodes`` Function-kind nodes whose
    ``source_text`` is non-null. For each candidate:

    - If stored summary + ``summary_provider`` + ``source_hash`` all match
      the selected model + freshly-computed source hash, it's a cache hit
      and we skip.
    - Otherwise call :func:`summarize_node` and persist via
      :meth:`GraphStore.update_summary`.

    Errors from :func:`summarize_node` are logged via the module logger and
    counted in :class:`BatchSummarizeResult.errors`; the batch continues so
    a single transient provider hiccup doesn't kill an entire run. Caller
    can re-run later — failed nodes will retry next time because their
    stored ``source_hash`` still doesn't match the live one.

    Returns counts. No-op (``skipped_no_provider=True``) when no summary model
    is configured.
    """
    if max_nodes < 1:
        raise ValueError(f"max_nodes must be >= 1, got {max_nodes}")

    chain = resolve_summary_chain()
    if not chain:
        return BatchSummarizeResult(
            generated=0,
            cached=0,
            skipped_no_provider=True,
            provider=None,
            errors=0,
        )

    # The complete selected model is the cache identity, not just its provider.
    model = chain[0]
    cache_provider = model
    provider_label = provider_of_model(model)

    # Resolve the provider key request-scoped: in HTTP multi-user mode it
    # comes from the bound JWT sub's per-sub bucket; in stdio/single-user mode
    # ``config_value_for_current_request`` falls back to ``os.environ``. We
    # pass it explicitly to ``summarize_node`` rather than letting litellm read
    # the process environment, so one user's key never reaches another
    # concurrent user's summary call. ``None`` (stdio, no key set) preserves
    # litellm's env fallback for the single-user path.
    from mcp_core.llm.providers import key_env_for_model

    from .credential_state import config_value_for_current_request

    key_env = key_env_for_model(model)
    api_key = config_value_for_current_request(key_env)
    if not api_key and key_env == "GEMINI_API_KEY":
        api_key = config_value_for_current_request("GOOGLE_API_KEY")

    # Performance Optimization: iterate over the cursor directly rather than
    # materializing rows in memory using .fetchall(), which is expensive
    # because it copies large `source_text` columns.
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
                provider=provider_label,
                api_key=api_key,
                model=model,
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
        provider=provider_label,
        errors=errors,
    )
