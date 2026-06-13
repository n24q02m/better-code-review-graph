"""Config schema for relay page setup (model-chain widget).

The relay form uses per-task ``model-chain`` widgets: the user picks an
ordered list of ``provider/model`` strings per task (order = fallback). The
relay page derives the required API-key fields from the providers referenced
by the chosen models (``derived: True``) and renders them automatically.

The literal `dict[str, Any]` type is intentional: this schema includes
`description` and `capabilityInfo` fields that the relay page renders at
runtime, but older wheels of `n24q02m-mcp-core` ship a stricter
`RelayConfigSchema` TypedDict that does not declare those keys. Using
`dict[str, Any]` keeps the schema forward-compatible while the installed
mcp-core catches up; see tracker: see docs/migration-from-mcp-relay-core.md.
"""

from typing import Any

_EMBEDDING_SUGGESTED = [
    "jina_ai/jina-embeddings-v5-text-small",
    "gemini/gemini-embedding-001",
    "openai/text-embedding-3-large",
    "cohere/embed-multilingual-v3.0",
]
_SUMMARY_SUGGESTED = [
    "gemini/gemini-2.5-flash",
    "openai/gpt-4o-mini",
]


def _key_field(key: str, label: str, ph: str, url: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "type": "password",
        "placeholder": ph,
        "helpUrl": url,
        "derived": True,
        "required": False,
    }


RELAY_SCHEMA: dict[str, Any] = {
    "server": "better-code-review-graph",
    "displayName": "Code Review Graph",
    "description": (
        "Pick models per task (order = fallback). Leave embedding empty for "
        "local ONNX; leave summary empty to disable LLM summaries. Key fields "
        "appear automatically for the providers your models use."
    ),
    "fields": [
        {
            "key": "EMBEDDING_MODELS",
            "label": "Embedding models",
            "type": "model-chain",
            "task": "embedding",
            "suggestedModels": _EMBEDDING_SUGGESTED,
            "hasLocal": True,
            "placeholder": "add embedding model…",
        },
        {
            "key": "SUMMARY_MODELS",
            "label": "Summary models",
            "type": "model-chain",
            "task": "summary",
            "suggestedModels": _SUMMARY_SUGGESTED,
            "hasLocal": False,
            "placeholder": "add summary model…",
        },
        _key_field(
            "JINA_AI_API_KEY", "Jina AI API Key", "jina_...", "https://jina.ai/api-key"
        ),
        _key_field(
            "GEMINI_API_KEY",
            "Gemini API Key",
            "AIza...",
            "https://aistudio.google.com/apikey",
        ),
        _key_field(
            "OPENAI_API_KEY",
            "OpenAI API Key",
            "sk-...",
            "https://platform.openai.com/api-keys",
        ),
        _key_field(
            "COHERE_API_KEY",
            "Cohere API Key",
            "co-...",
            "https://dashboard.cohere.com/api-keys",
        ),
        _key_field("XAI_API_KEY", "xAI API Key", "xai-...", "https://console.x.ai"),
        _key_field(
            "ANTHROPIC_API_KEY",
            "Anthropic API Key",
            "sk-ant-...",
            "https://console.anthropic.com",
        ),
    ],
    "capabilityInfo": [
        {
            "label": "Embedding",
            "priority": "configurable",
            "description": "Vector embeddings for code graph search. Empty = local Qwen3-Embedding (0.6B ONNX).",
        },
        {
            "label": "Summary",
            "priority": "configurable",
            "description": "LLM docstring summaries for graph nodes. Empty = summaries disabled.",
        },
    ],
}
