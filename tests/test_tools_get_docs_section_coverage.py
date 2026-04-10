from unittest.mock import MagicMock, patch

from better_code_review_graph.tools import get_docs_section


class TestGetDocsSectionCoverage:
    def test_get_docs_section_value_error_fallback(self, tmp_path):
        """Cover line 1059: ValueError fallback."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "LLM-OPTIMIZED-REFERENCE.md").write_text(
            '<section name="test">content</section>', encoding="utf-8"
        )

        with patch(
            "better_code_review_graph.tools._get_store", side_effect=ValueError("fail")
        ):
            result = get_docs_section("test", repo_root=str(tmp_path))

        assert result["status"] == "ok"
        assert result["content"] == "content"

    def test_get_docs_section_runtime_error_fallback(self, tmp_path):
        """Cover line 1059: RuntimeError fallback."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "LLM-OPTIMIZED-REFERENCE.md").write_text(
            '<section name="test">content</section>', encoding="utf-8"
        )

        with patch(
            "better_code_review_graph.tools._get_store",
            side_effect=RuntimeError("fail"),
        ):
            result = get_docs_section("test", repo_root=str(tmp_path))

        assert result["status"] == "ok"
        assert result["content"] == "content"

    def test_get_docs_section_no_repo_root_store_success(self, tmp_path):
        """Cover line 1058: repo_root is None, _get_store succeeds."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "LLM-OPTIMIZED-REFERENCE.md").write_text(
            '<section name="test">content</section>', encoding="utf-8"
        )

        mock_store = MagicMock()
        with patch(
            "better_code_review_graph.tools._get_store",
            return_value=(mock_store, tmp_path),
        ):
            # repo_root=None is default
            result = get_docs_section("test")

        assert result["status"] == "ok"
        assert result["content"] == "content"

    def test_get_docs_section_subdir_root_addition(self, tmp_path):
        """Cover line 1058: repo_root is a subdir, _get_store returns parent root."""
        repo_root = tmp_path
        subdir = repo_root / "src"
        subdir.mkdir()

        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        (docs_dir / "LLM-OPTIMIZED-REFERENCE.md").write_text(
            '<section name="test">root content</section>', encoding="utf-8"
        )

        mock_store = MagicMock()
        # _get_store(subdir) returns (store, repo_root)
        with patch(
            "better_code_review_graph.tools._get_store",
            return_value=(mock_store, repo_root),
        ):
            result = get_docs_section("test", repo_root=str(subdir))

        assert result["status"] == "ok"
        assert result["content"] == "root content"

    def test_get_docs_section_root_already_in_search_roots(self, tmp_path):
        """Cover line 1057 branch where root is already in search_roots."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "LLM-OPTIMIZED-REFERENCE.md").write_text(
            '<section name="test">content</section>', encoding="utf-8"
        )

        mock_store = MagicMock()
        with patch(
            "better_code_review_graph.tools._get_store",
            return_value=(mock_store, tmp_path),
        ):
            # repo_root is tmp_path, _get_store also returns tmp_path
            result = get_docs_section("test", repo_root=str(tmp_path))

        assert result["status"] == "ok"
        assert result["content"] == "content"
