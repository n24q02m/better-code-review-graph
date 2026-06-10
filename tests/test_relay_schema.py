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
