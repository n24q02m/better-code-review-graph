"""Tests for #319: stage-mapped recipes hints in help output.

`help(topic="recipes")` should return operational recipe templates so
agents do not have to derive from first principles how to combine the 5
tools for common workflows.
"""

from __future__ import annotations

import json

from better_code_review_graph.server import help


def test_help_recipes_topic_returns_recipes_doc():
    out = help(topic="recipes")
    # Not a JSON error response -- it should be the doc text.
    assert "Recipes" in out
    assert "Stage 0" in out
    assert "Stage 4" in out


def test_help_unknown_topic_includes_recipes_in_valid_list():
    out = help(topic="bogus")
    payload = json.loads(out)
    assert payload.get("error", "").startswith("Unknown topic")
    assert "recipes" in payload["valid_topics"]


def test_recipes_doc_mentions_each_tool():
    """Sanity-check the recipes doc references all 5 tools."""
    out = help(topic="recipes")
    for tool in ("graph", "query", "review", "config"):
        assert tool in out
