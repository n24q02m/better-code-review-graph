"""Tests for the RELAY_SCHEMA configuration."""

from __future__ import annotations

from better_code_review_graph.relay_schema import RELAY_SCHEMA


class TestRelaySchema:
    def test_server_id(self):
        """Must match the expected server ID for relay identification."""
        assert RELAY_SCHEMA["server"] == "better-code-review-graph"

    def test_display_name(self):
        """Must match the expected display name for the relay UI."""
        assert RELAY_SCHEMA["displayName"] == "Code Review Graph"

    def test_description(self):
        """Must have a descriptive string for users."""
        assert isinstance(RELAY_SCHEMA["description"], str)
        assert "API keys" in RELAY_SCHEMA["description"]

    def test_fields_structure(self):
        """Fields must be a list of configuration objects."""
        fields = RELAY_SCHEMA["fields"]
        assert isinstance(fields, list)
        assert len(fields) == 4

        expected_keys = [
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
        ]
        actual_keys = [f["key"] for f in fields]
        assert actual_keys == expected_keys

    def test_fields_attributes(self):
        """Each field must have the required relay attributes."""
        for field in RELAY_SCHEMA["fields"]:
            assert "key" in field
            assert "label" in field
            assert "type" in field
            assert "required" in field
            assert field["required"] is False
            if "helpUrl" in field:
                assert field["helpUrl"].startswith("https://")

    def test_capability_info(self):
        """Must define embedding and reranking capabilities for the relay UI."""
        capabilities = RELAY_SCHEMA["capabilityInfo"]
        assert isinstance(capabilities, list)
        assert len(capabilities) == 2

        labels = [c["label"] for c in capabilities]
        assert "Embedding" in labels
        assert "Reranking" in labels

        for cap in capabilities:
            assert "label" in cap
            assert "priority" in cap
            assert "description" in cap

    def test_forward_compatibility_type(self):
        """The schema must be a plain dict for forward compatibility."""
        # The docstring in relay_schema.py notes this is intentional.
        assert isinstance(RELAY_SCHEMA, dict)
