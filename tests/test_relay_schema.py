"""Tests for relay_schema module."""

from __future__ import annotations

from better_code_review_graph.relay_schema import RELAY_SCHEMA


class TestRelaySchema:
    def test_server_name(self):
        assert RELAY_SCHEMA["server"] == "better-code-review-graph"

    def test_display_name(self):
        assert RELAY_SCHEMA["displayName"] == "Code Review Graph"

    def test_has_fields(self):
        fields = RELAY_SCHEMA["fields"]
        assert len(fields) == 4

    def test_field_keys(self):
        keys = [f["key"] for f in RELAY_SCHEMA["fields"]]
        assert keys == [
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
        ]

    def test_all_fields_optional(self):
        for field in RELAY_SCHEMA["fields"]:
            assert field["required"] is False

    def test_schema_is_valid_typed_dict(self):
        assert "server" in RELAY_SCHEMA
        assert "displayName" in RELAY_SCHEMA
        assert "fields" in RELAY_SCHEMA
