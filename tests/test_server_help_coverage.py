import json
from unittest.mock import patch

from better_code_review_graph.server import help


def test_help_suggestion():
    """Test help with a topic that triggers a suggestion."""
    result_str = help(topic="graphh")
    result = json.loads(result_str)
    assert "error" in result
    assert "Did you mean 'graph'?" in result["error"]
    assert "graph" in result["valid_topics"]


def test_help_no_suggestion():
    """Test help with a topic that does not trigger a suggestion."""
    result_str = help(topic="zzz")
    result = json.loads(result_str)
    assert "error" in result
    # For "zzz", difflib.get_close_matches should return nothing with default cutoff
    assert "Did you mean" not in result["error"]
    assert "zzz" in result["error"]


@patch("better_code_review_graph.server.files")
def test_help_file_not_found_fallback_graph(mock_files):
    """Test help fallback for graph topic when file is missing."""
    mock_files.return_value.joinpath.return_value.read_text.side_effect = (
        FileNotFoundError()
    )

    with patch("better_code_review_graph.server.get_docs_section") as mock_get_docs:
        mock_get_docs.return_value = {"status": "ok", "content": "fallback content"}

        result = help(topic="graph")
        assert result == "fallback content"
        mock_get_docs.assert_called_once()


@patch("better_code_review_graph.server.files")
def test_help_file_not_found_fallback_fail(mock_files):
    """Test help fallback failure when file is missing."""
    mock_files.return_value.joinpath.return_value.read_text.side_effect = (
        FileNotFoundError()
    )

    with patch("better_code_review_graph.server.get_docs_section") as mock_get_docs:
        mock_get_docs.return_value = {"status": "error"}

        result_str = help(topic="graph")
        result = json.loads(result_str)
        assert "error" in result
        assert "Documentation not found for topic: graph" in result["error"]


@patch("better_code_review_graph.server.files")
def test_help_file_not_found_other_topic(mock_files):
    """Test help failure for non-fallback topic when file is missing."""
    mock_files.return_value.joinpath.return_value.read_text.side_effect = (
        FileNotFoundError()
    )

    result_str = help(topic="review")
    result = json.loads(result_str)
    assert "error" in result
    assert "Documentation not found for topic: review" in result["error"]
