"""Config schema for relay page setup."""

from mcp_relay_core.schema.types import ConfigField, RelayConfigSchema

RELAY_SCHEMA: RelayConfigSchema = {
    "server": "better-code-review-graph",
    "displayName": "Code Review Graph",
    "fields": [
        ConfigField(
            key="GEMINI_API_KEY",
            label="Gemini API Key",
            type="password",
            placeholder="AIza...",
            helpUrl="https://aistudio.google.com/apikey",
            helpText="Required for cloud embeddings via Google Gemini",
        ),
    ],
}
