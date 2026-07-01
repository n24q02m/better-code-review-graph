"""Tests for relay_schema module (model-chain widget)."""

from __future__ import annotations

from better_code_review_graph.relay_schema import RELAY_SCHEMA


def _fields_by_key() -> dict:
    return {f["key"]: f for f in RELAY_SCHEMA["fields"]}


class TestRelaySchema:
    def test_server_name(self):
        assert RELAY_SCHEMA["server"] == "better-code-review-graph"

    def test_display_name(self):
        assert RELAY_SCHEMA["displayName"] == "Code Review Graph"

    def test_model_chain_tasks_are_embedding_and_summary(self):
        tasks = {
            f["task"] for f in RELAY_SCHEMA["fields"] if f.get("type") == "model-chain"
        }
        assert tasks == {"embedding", "summary"}

    def test_embedding_has_local_summary_does_not(self):
        fields = _fields_by_key()
        assert fields["EMBEDDING_MODELS"]["hasLocal"] is True
        assert fields["SUMMARY_MODELS"]["hasLocal"] is False

    def test_suggested_models_all_have_provider_prefix(self):
        for f in RELAY_SCHEMA["fields"]:
            if f.get("type") == "model-chain":
                for model in f["suggestedModels"]:
                    assert "/" in model, f"{model} missing provider prefix"

    def test_derived_key_fields_present_and_marked(self):
        fields = _fields_by_key()
        for key in (
            "JINA_AI_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "COHERE_API_KEY",
        ):
            assert key in fields
            assert fields[key]["derived"] is True

    def test_vertex_express_key_field_present_and_derived(self):
        fields = _fields_by_key()
        assert "GOOGLE_VERTEX_EXPRESS_API_KEY" in fields
        assert fields["GOOGLE_VERTEX_EXPRESS_API_KEY"]["derived"] is True
        assert "VERTEX_AI_API_KEY" not in fields  # no dead-end field

    def test_no_priority_arrows_in_capability_info(self):
        for cap in RELAY_SCHEMA["capabilityInfo"]:
            assert ">" not in cap["priority"], cap
            assert cap["priority"] == "configurable"
