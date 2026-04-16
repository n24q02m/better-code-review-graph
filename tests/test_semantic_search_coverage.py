import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.tools import semantic_search_nodes


@pytest.fixture
def repo_with_scoring_nodes(tmp_path):
    """Create a temp repo with a graph seeded with nodes for scoring tests."""
    (tmp_path / ".git").mkdir()
    crg_dir = tmp_path / ".code-review-graph"
    crg_dir.mkdir()
    (crg_dir / ".gitignore").write_text("*\n")

    db_path = crg_dir / "graph.db"
    store = GraphStore(str(db_path))

    abs_f = str(tmp_path / "scoring.py")
    (tmp_path / "scoring.py").write_text("# scoring tests\n")

    nodes = [
        # Exact match
        NodeInfo(
            kind="Function",
            name="auth",
            file_path=abs_f,
            line_start=1,
            line_end=2,
            language="python",
        ),
        # Prefix match
        NodeInfo(
            kind="Function",
            name="auth_handler",
            file_path=abs_f,
            line_start=3,
            line_end=4,
            language="python",
        ),
        # Partial match (contains "auth" but not at start)
        NodeInfo(
            kind="Function",
            name="do_auth",
            file_path=abs_f,
            line_start=5,
            line_end=6,
            language="python",
        ),
        # Kind filter test - Function
        NodeInfo(
            kind="Class",
            name="AuthManager",
            file_path=abs_f,
            line_start=7,
            line_end=8,
            language="python",
        ),
    ]

    for node in nodes:
        store.upsert_node(node)

    store.commit()
    store.close()
    return tmp_path


class TestSemanticSearchScoringCoverage:
    def test_score_branches(self, repo_with_scoring_nodes):
        """Exercise all branches of the inner score() function."""
        # Query "auth"
        # "auth" -> score 0
        # "auth_handler" -> score 1
        # "do_auth" -> score 2 (doesn't start with auth)
        # "AuthManager" -> starts with "auth" (case insensitive) -> score 1

        result = semantic_search_nodes(
            query="auth", repo_root=str(repo_with_scoring_nodes)
        )
        assert result["status"] == "ok"
        assert result["search_mode"] == "keyword"

        names = [r["name"] for r in result["results"]]

        # Verify ordering based on scores
        # Score 0 (exact): auth
        # Score 1 (prefix): auth_handler, AuthManager
        # Score 2 (partial): do_auth

        assert "auth" in names
        assert "auth_handler" in names
        assert "do_auth" in names
        assert "AuthManager" in names

        auth_idx = names.index("auth")
        handler_idx = names.index("auth_handler")
        manager_idx = names.index("AuthManager")
        do_auth_idx = names.index("do_auth")

        # Exact before prefixes
        assert auth_idx < handler_idx
        assert auth_idx < manager_idx

        # Prefixes before partial
        assert handler_idx < do_auth_idx
        assert manager_idx < do_auth_idx

    def test_kind_filter_keyword_path(self, repo_with_scoring_nodes):
        """Exercise the kind filter in the keyword fallback path."""
        # Filter for Class
        result = semantic_search_nodes(
            query="auth", kind="Class", repo_root=str(repo_with_scoring_nodes)
        )
        assert result["status"] == "ok"
        assert len(result["results"]) == 1
        assert result["results"][0]["name"] == "AuthManager"
        assert result["results"][0]["kind"] == "Class"

        # Filter for Function
        result = semantic_search_nodes(
            query="auth", kind="Function", repo_root=str(repo_with_scoring_nodes)
        )
        assert result["status"] == "ok"
        for r in result["results"]:
            assert r["kind"] == "Function"

        names = [r["name"] for r in result["results"]]
        assert "AuthManager" not in names
