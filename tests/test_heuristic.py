"""Extra tests for heuristic scanner to close coverage gaps."""

from __future__ import annotations

from unittest.mock import patch

from better_code_review_graph.security.heuristic import (
    _default_rules_dir,
    _load_rules_from_dir,
    _parse_simple_yaml,
)


def test_parse_simple_yaml_skips_empty_key():
    # Line 88: if not key: continue
    yaml = ": value\nvalid: key"
    data = _parse_simple_yaml(yaml)
    assert "valid" in data
    assert "" not in data


def test_load_rules_from_dir_handles_string_languages(tmp_path):
    # Line 131: if isinstance(languages, str): language_iter = [languages]
    f = tmp_path / "rule.yaml"
    f.write_text(
        "id: test-id\nseverity: high\npattern: foo\nlanguages: python\nmessage: msg\n",
        encoding="utf-8",
    )
    rules = _load_rules_from_dir(tmp_path)
    assert len(rules) == 1
    assert rules[0].languages == frozenset({"python"})


def test_default_rules_dir_fallback_on_module_not_found():
    # Lines 162-164: catch ModuleNotFoundError/OSError
    with patch(
        "better_code_review_graph.security.heuristic.files",
        side_effect=ModuleNotFoundError,
    ):
        path = _default_rules_dir()
        # Should fall back to the repo path
        assert "rules" in path.parts
        assert "heuristic" in path.parts


def test_default_rules_dir_fallback_on_not_a_directory():
    # Line 161-164: if not path.is_dir(): ... catch ...
    with patch("better_code_review_graph.security.heuristic.files"):
        with patch(
            "better_code_review_graph.security.heuristic.Path.is_dir",
            return_value=False,
        ):
            path = _default_rules_dir()
            assert "rules" in path.parts
