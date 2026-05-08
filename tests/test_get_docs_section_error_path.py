from unittest.mock import patch

from better_code_review_graph.tools import get_docs_section


class TestGetDocsSectionErrorPath:
    def test_get_docs_section_store_error_with_repo_root(self, tmp_path):
        """
        Verify that if _get_store raises an error but repo_root is provided,
        the function still searches for docs in the repo_root.
        """
        repo_root = tmp_path
        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        doc_file = docs_dir / "LLM-OPTIMIZED-REFERENCE.md"
        doc_file.write_text(
            '<section name="usage">Usage content</section>', encoding="utf-8"
        )

        with patch(
            "better_code_review_graph.tools._get_store",
            side_effect=ValueError("Store initialization failed"),
        ):
            result = get_docs_section("usage", repo_root=str(repo_root))

        assert result["status"] == "ok"
        assert result["section"] == "usage"
        assert result["content"] == "Usage content"

    def test_get_docs_section_store_error_without_repo_root(self):
        """
        Verify that if _get_store raises an error and no repo_root is provided,
        the function handles it gracefully (returns not_found).
        """
        with patch(
            "better_code_review_graph.tools._get_store",
            side_effect=RuntimeError("Generic failure"),
        ):
            result = get_docs_section("usage", repo_root=None)

        assert result["status"] == "not_found"
        assert "Section 'usage' not found" in result["error"]
