"""Config schema for relay page setup."""

from mcp_relay_core.schema.types import ConfigField, RelayConfigSchema

RELAY_SCHEMA: RelayConfigSchema = {
    "server": "better-code-review-graph",
    "displayName": "Code Review Graph",
    "description": "At least one API key required for cloud embeddings. Priority: Jina > Gemini > OpenAI > Cohere. Skip for local ONNX mode.",
    "fields": [
        ConfigField(
            key="JINA_AI_API_KEY",
            label="Jina AI API Key",
            type="password",
            placeholder="jina_...",
            helpUrl="https://jina.ai/embeddings/",
            helpText="Highest priority. Embedding + reranking.",
            required=False,
        ),
        ConfigField(
            key="GEMINI_API_KEY",
            label="Gemini API Key",
            type="password",
            placeholder="AIza...",
            helpUrl="https://aistudio.google.com/apikey",
            helpText="Embedding via Google Gemini. Free tier available.",
            required=False,
        ),
        ConfigField(
            key="OPENAI_API_KEY",
            label="OpenAI API Key",
            type="password",
            placeholder="sk-...",
            helpUrl="https://platform.openai.com/api-keys",
            helpText="Embedding only.",
            required=False,
        ),
        ConfigField(
            key="COHERE_API_KEY",
            label="Cohere API Key",
            type="password",
            placeholder="",
            helpUrl="https://dashboard.cohere.com/api-keys",
            helpText="Embedding + reranking.",
            required=False,
        ),
    ],
}
