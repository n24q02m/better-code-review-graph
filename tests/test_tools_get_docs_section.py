from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from better_code_review_graph.tools import get_docs_section


def test_get_docs_section_value_error_fallback(tmp_path):
    """get_docs_section should handle ValueError from _get_store."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    docs_file = docs_dir / "LLM-OPTIMIZED-REFERENCE.md"
    docs_file.write_text(
        '<section name="usage">ValueError fallback works!</section>',
        encoding="utf-8",
    )

    with patch(
        "better_code_review_graph.tools._get_store",
        side_effect=ValueError("Invalid repo root"),
    ):
        result = get_docs_section("usage", repo_root=str(tmp_path))

    assert result["status"] == "ok"
    assert result["content"] == "ValueError fallback works!"


def test_get_docs_section_runtime_error_fallback(tmp_path):
    """get_docs_section should handle RuntimeError from _get_store."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    docs_file = docs_dir / "LLM-OPTIMIZED-REFERENCE.md"
    docs_file.write_text(
        '<section name="usage">RuntimeError fallback works!</section>',
        encoding="utf-8",
    )

    with patch(
        "better_code_review_graph.tools._get_store",
        side_effect=RuntimeError("Store init failed"),
    ):
        result = get_docs_section("usage", repo_root=str(tmp_path))

    assert result["status"] == "ok"
    assert result["content"] == "RuntimeError fallback works!"


def test_get_docs_section_different_root_appended(tmp_path):
    """get_docs_section should append root from _get_store if not in search_roots."""
    # repo_root will be tmp_path
    # we'll mock _get_store to return a DIFFERENT path
    other_root = tmp_path / "other"
    other_root.mkdir()

    docs_dir = other_root / "docs"
    docs_dir.mkdir()
    docs_file = docs_dir / "LLM-OPTIMIZED-REFERENCE.md"
    docs_file.write_text(
        '<section name="usage">Other root works!</section>',
        encoding="utf-8",
    )

    mock_store = MagicMock()
    with patch(
        "better_code_review_graph.tools._get_store",
        return_value=(mock_store, other_root),
    ):
        # Even if repo_root is provided, it should also check the root from _get_store
        result = get_docs_section("usage", repo_root=str(tmp_path))

    assert result["status"] == "ok"
    assert result["content"] == "Other root works!"


def test_get_docs_section_same_root_not_appended_twice(tmp_path):
    """get_docs_section should NOT append root from _get_store if already in search_roots."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    docs_file = docs_dir / "LLM-OPTIMIZED-REFERENCE.md"
    docs_file.write_text(
        '<section name="usage">Same root works!</section>',
        encoding="utf-8",
    )

    mock_store = MagicMock()
    with patch(
        "better_code_review_graph.tools._get_store",
        return_value=(mock_store, Path(tmp_path).resolve()),
    ):
        # repo_root is tmp_path. _get_store returns tmp_path.
        result = get_docs_section("usage", repo_root=str(tmp_path))

    assert result["status"] == "ok"
    assert result["content"] == "Same root works!"


def test_get_docs_section_no_repo_root_no_store(tmp_path):
    """get_docs_section should handle no repo_root and _get_store failure."""
    with patch(
        "better_code_review_graph.tools._get_store",
        side_effect=ValueError("No repo found"),
    ):
        result = get_docs_section("usage")

    assert result["status"] == "not_found"
