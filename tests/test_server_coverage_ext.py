import json
from unittest.mock import patch

import pytest

from better_code_review_graph.server import (
    _config_status,
    _maybe_include_setup_hint,
    help,
    setup,
)


class TestHelpCoverageExt:
    def test_help_unknown_topic_no_suggestion(self):
        result = json.loads(help.fn(topic="zzzzzzzz"))
        assert "Unknown topic 'zzzzzzzz'." in result["error"]
        assert "Did you mean" not in result["error"]
        assert result["valid_topics"] == ["config", "graph", "query", "review"]

    def test_help_unknown_topic_with_suggestion(self):
        result = json.loads(help.fn(topic="graphi"))
        assert "Unknown topic 'graphi'. Did you mean 'graph'?" in result["error"]
        assert result["valid_topics"] == ["config", "graph", "query", "review"]

    @patch("better_code_review_graph.server.files")
    def test_help_file_not_found_fallback_ok(self, mock_files):
        # Mocking files() to raise FileNotFoundError
        mock_files.return_value.joinpath.return_value.read_text.side_effect = (
            FileNotFoundError("docs not found")
        )

        with patch("better_code_review_graph.server.get_docs_section") as mock_get_docs:
            mock_get_docs.return_value = {"status": "ok", "content": "Fallback content"}
            result = help.fn(topic="graph")
            assert result == "Fallback content"
            mock_get_docs.assert_called_once()

    @patch("better_code_review_graph.server.files")
    def test_help_file_not_found_fallback_fail(self, mock_files):
        mock_files.return_value.joinpath.return_value.read_text.side_effect = (
            FileNotFoundError("docs not found")
        )

        with patch("better_code_review_graph.server.get_docs_section") as mock_get_docs:
            mock_get_docs.return_value = {"status": "error"}
            result = json.loads(help.fn(topic="graph"))
            assert "Documentation not found for topic: graph" in result["error"]


class TestSetupCoverageExt:
    @pytest.mark.asyncio
    @patch("better_code_review_graph.credential_state.get_state")
    @patch("better_code_review_graph.credential_state.get_setup_url")
    async def test_setup_status(self, mock_url, mock_get_state):
        from better_code_review_graph.credential_state import CredentialState

        try:
            val = CredentialState.AWAITING_SETUP
        except AttributeError:
            val = CredentialState.awaiting_setup
        mock_get_state.return_value = val
        mock_url.return_value = "http://setup.url"

        result = json.loads(await setup.fn(action="status"))
        assert result["state"] == val.value
        assert result["setup_url"] == "http://setup.url"

    @pytest.mark.asyncio
    @patch("better_code_review_graph.credential_state.get_state")
    async def test_setup_start_already_configured(self, mock_get_state):
        from better_code_review_graph.credential_state import CredentialState

        mock_get_state.return_value = CredentialState.CONFIGURED

        result = json.loads(await setup.fn(action="start"))
        assert result["status"] == "already_configured"

    @pytest.mark.asyncio
    @patch("better_code_review_graph.credential_state.get_state")
    @patch("better_code_review_graph.credential_state.trigger_relay_setup")
    async def test_setup_start_success(self, mock_trigger, mock_get_state):
        from better_code_review_graph.credential_state import CredentialState

        mock_get_state.return_value = CredentialState.AWAITING_SETUP
        mock_trigger.return_value = "http://setup.url"

        result = json.loads(await setup.fn(action="start"))
        assert result["status"] == "setup_started"
        assert result["setup_url"] == "http://setup.url"

    @pytest.mark.asyncio
    @patch("better_code_review_graph.credential_state.get_state")
    @patch("better_code_review_graph.credential_state.trigger_relay_setup")
    async def test_setup_start_fail(self, mock_trigger, mock_get_state):
        from better_code_review_graph.credential_state import CredentialState

        mock_get_state.return_value = CredentialState.AWAITING_SETUP
        mock_trigger.return_value = None

        result = json.loads(await setup.fn(action="start"))
        assert result["status"] == "error"

    @pytest.mark.asyncio
    @patch("mcp_relay_core.set_local_mode")
    @patch("better_code_review_graph.credential_state.set_state")
    async def test_setup_skip(self, mock_set_state, mock_set_local):
        result = json.loads(await setup.fn(action="skip"))
        assert result["status"] == "ok"
        mock_set_local.assert_called_once()
        mock_set_state.assert_called_once()

    @pytest.mark.asyncio
    @patch("better_code_review_graph.credential_state.reset_state")
    async def test_setup_reset(self, mock_reset):
        result = json.loads(await setup.fn(action="reset"))
        assert result["status"] == "ok"
        mock_reset.assert_called_once()

    @pytest.mark.asyncio
    @patch("better_code_review_graph.credential_state.resolve_credential_state")
    @patch("better_code_review_graph.credential_state.get_state")
    async def test_setup_complete(self, mock_get_state, mock_resolve):
        from better_code_review_graph.credential_state import CredentialState

        mock_get_state.return_value = CredentialState.CONFIGURED

        result = json.loads(await setup.fn(action="complete"))
        assert result["status"] == "ok"
        assert result["state"] == "configured"
        mock_resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_unknown_action_suggestion(self):
        result = json.loads(await setup.fn(action="statu"))
        assert "Unknown action 'statu'. Did you mean 'status'?" in result["error"]

    @pytest.mark.asyncio
    async def test_setup_unknown_action_no_suggestion(self):
        result = json.loads(await setup.fn(action="zzzzzzzz"))
        assert "Unknown action 'zzzzzzzz'." in result["error"]
        assert "Did you mean" not in result["error"]


class TestServerHintsCoverage:
    @patch("better_code_review_graph.credential_state.get_state")
    @patch("better_code_review_graph.credential_state.get_setup_url")
    def test_maybe_include_setup_hint_url(self, mock_url, mock_get_state):
        from better_code_review_graph.credential_state import CredentialState

        mock_get_state.return_value = CredentialState.AWAITING_SETUP
        mock_url.return_value = "http://setup.url"

        result = {}
        _maybe_include_setup_hint(result)
        assert "_setup_hint" in result
        assert "http://setup.url" in result["_setup_hint"]

    @patch("better_code_review_graph.credential_state.get_state")
    @patch("better_code_review_graph.credential_state.get_setup_url")
    def test_maybe_include_setup_hint_no_url(self, mock_url, mock_get_state):
        from better_code_review_graph.credential_state import CredentialState

        mock_get_state.return_value = CredentialState.AWAITING_SETUP
        mock_url.return_value = None

        result = {}
        _maybe_include_setup_hint(result)
        assert "_setup_hint" in result
        assert "setup_start" in result["_setup_hint"]

    def test_maybe_include_setup_hint_not_awaiting(self):
        from better_code_review_graph.credential_state import CredentialState

        with patch(
            "better_code_review_graph.credential_state.get_state"
        ) as mock_get_state:
            mock_get_state.return_value = CredentialState.CONFIGURED
            result = {}
            _maybe_include_setup_hint(result)
            assert "_setup_hint" not in result


class TestServerStatusCoverage:
    def test_config_status_version_fallback(self):
        # Patch pkg_version where it's used - but it's imported locally in _config_status
        with patch("importlib.metadata.version") as mock_version:
            mock_version.side_effect = Exception("pkg not found")
            result = json.loads(_config_status(None))
            assert result["version"] == "dev"

    def test_help_file_not_found_fallback_unsupported_topic(self):
        # topic not in ("graph", "query")
        with patch("better_code_review_graph.server.files") as mock_files:
            mock_files.return_value.joinpath.return_value.read_text.side_effect = (
                FileNotFoundError("docs not found")
            )
            result = json.loads(help.fn(topic="review"))
            assert "Documentation not found for topic: review" in result["error"]
