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
    "cohere/embed-v4.0",
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


def _api_base_field(key: str, label: str, help_text: str) -> dict[str, Any]:
    # Always-visible (not derived): the renderer only reveals a derived field
    # when a model chip derives that exact provider ENV key, and no model
    # derives *_API_BASE, so a derived endpoint field would stay hidden. The
    # optional badge comes from required:false. Value is SSRF-vetted per-sub in
    # mcp_core.llm dispatch before any request.
    return {
        "key": key,
        "label": label,
        "type": "url",
        "placeholder": "https://gateway.example/…",
        "helpText": help_text,
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
        _api_base_field(
            "EMBEDDING_API_BASE",
            "Embedding endpoint",
            "Custom endpoint / CF AI Gateway for embedding calls.",
        ),
        {
            "key": "SUMMARY_MODELS",
            "label": "Summary models",
            "type": "model-chain",
            "task": "summary",
            "suggestedModels": _SUMMARY_SUGGESTED,
            "hasLocal": False,
            "placeholder": "add summary model…",
        },
        _api_base_field(
            "LLM_API_BASE",
            "Summary (LLM) endpoint",
            "Custom endpoint / CF AI Gateway for summary LLM calls.",
        ),
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
        _key_field(
            "GOOGLE_VERTEX_EXPRESS_API_KEY",
            "Vertex AI (Express) API Key",
            "AQ...",
            "https://cloud.google.com/vertex-ai/generative-ai/docs/start/express-mode/overview",
        ),
    ],
    "capabilityInfo": [
        {
            "label": "Embedding",
            "priority": "configurable",
            "description": "Vector embeddings for code graph search. Empty = local fastretrieval registry.",
        },
        {
            "label": "Summary",
            "priority": "configurable",
            "description": "LLM docstring summaries for graph nodes. Empty = summaries disabled.",
        },
    ],
}
