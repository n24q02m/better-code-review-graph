from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import query_graph


@pytest.fixture
def repo_with_graph(tmp_path):
    """Create a temp repo with .git, python files, and a seeded graph."""
    (tmp_path / ".git").mkdir()
    crg_dir = tmp_path / ".code-review-graph"
    crg_dir.mkdir()
    (crg_dir / ".gitignore").write_text("*\n")

    # Create source files
    auth_py = tmp_path / "auth.py"
    auth_py.write_text(
        "class AuthService:\n"
        "    def login(self, user, password):\n"
        "        return True\n"
        "\n"
        "    def logout(self):\n"
        "        pass\n"
    )
    main_py = tmp_path / "main.py"
    main_py.write_text(
        "from auth import AuthService\n"
        "\n"
        "def process():\n"
        "    svc = AuthService()\n"
        "    svc.login('admin', 'pass')\n"
    )

    # Seed graph
    db_path = crg_dir / "graph.db"
    store = GraphStore(str(db_path))

    abs_auth = str(auth_py)
    abs_main = str(main_py)

    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_auth,
            file_path=abs_auth,
            line_start=1,
            line_end=6,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="File",
            name=abs_main,
            file_path=abs_main,
            line_start=1,
            line_end=5,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Class",
            name="AuthService",
            file_path=abs_auth,
            line_start=1,
            line_end=6,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="login",
            file_path=abs_auth,
            line_start=2,
            line_end=3,
            language="python",
            parent_name="AuthService",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="process",
            file_path=abs_main,
            line_start=3,
            line_end=5,
            language="python",
        )
    )

    store.upsert_edge(
        EdgeInfo(
            kind="CONTAINS",
            source=abs_auth,
            target=f"{abs_auth}::AuthService",
            file_path=abs_auth,
        )
    )
    store.upsert_edge(
        EdgeInfo(
            kind="CONTAINS",
            source=f"{abs_auth}::AuthService",
            target=f"{abs_auth}::AuthService.login",
            file_path=abs_auth,
        )
    )
    store.upsert_edge(
        EdgeInfo(
            kind="CALLS",
            source=f"{abs_main}::process",
            target=f"{abs_auth}::AuthService.login",
            file_path=abs_main,
            line=5,
        )
    )

    store.commit()
    store.close()

    return tmp_path


class TestCallersOfCoverage:
    def test_callers_of_qualified_match_and_filtering(self, repo_with_graph):
        """Test callers_of returns correct nodes and filters out non-CALLS edges."""
        abs_auth = str(repo_with_graph / "auth.py")
        abs_main = str(repo_with_graph / "main.py")

        target_qn = f"{abs_auth}::AuthService.login"
        expected_caller = f"{abs_main}::process"
        not_expected_caller = f"{abs_auth}::AuthService"

        result = query_graph(
            pattern="callers_of",
            target=target_qn,
            repo_root=str(repo_with_graph),
        )

        assert result["status"] == "ok"
        qns = [r["qualified_name"] for r in result["results"]]
        assert expected_caller in qns
        assert not_expected_caller not in qns

        # Verify edges
        kinds = [e["kind"] for e in result["edges"]]
        assert "CALLS" in kinds
        assert "CONTAINS" not in kinds

    def test_callers_of_fallback_match(self, repo_with_graph):
        """Test callers_of fallback path when qualified edges are missing but name matches."""
        abs_auth = str(repo_with_graph / "auth.py")
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))

        # Add a node that is NOT called by its qualified name
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="helper",
                file_path=abs_auth,
                line_start=10,
                line_end=11,
                language="python",
            )
        )
        # Edge with unqualified target
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source=f"{abs_auth}::some_caller",
                target="helper",
                file_path=abs_auth,
                line=5,
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="some_caller",
                file_path=abs_auth,
                line_start=5,
                line_end=6,
                language="python",
            )
        )

        store.commit()
        store.close()

        target_qn = f"{abs_auth}::helper"
        result = query_graph(
            pattern="callers_of",
            target=target_qn,
            repo_root=str(repo_with_graph),
        )

        assert result["status"] == "ok"
        qns = [r["qualified_name"] for r in result["results"]]
        assert f"{abs_auth}::some_caller" in qns

    def test_callers_of_no_results(self, repo_with_graph):
        """Test callers_of with a target that has no callers."""
        abs_main = str(repo_with_graph / "main.py")
        target_qn = f"{abs_main}::process"

        result = query_graph(
            pattern="callers_of",
            target=target_qn,
            repo_root=str(repo_with_graph),
        )

        assert result["status"] == "ok"
        assert result["results"] == []
        assert result["edges"] == []
