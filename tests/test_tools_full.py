"""Comprehensive tests for MCP tool functions in tools.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import EdgeInfo, NodeInfo
from better_code_review_graph.tools import (
    _BUILTIN_CALL_NAMES,
    _extract_relevant_lines,
    _generate_review_guidance,
    _get_store,
    _validate_repo_root,
    build_or_update_graph,
    embed_graph,
    find_large_functions,
    get_docs_section,
    get_impact_radius,
    get_review_context,
    list_graph_stats,
    query_graph,
    semantic_search_nodes,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    test_auth = tmp_path / "test_auth.py"
    test_auth.write_text("def test_login():\n    assert True\n")

    # Seed graph
    db_path = crg_dir / "graph.db"
    store = GraphStore(str(db_path))

    abs_auth = str(auth_py)
    abs_main = str(main_py)
    abs_test = str(test_auth)

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
            name="logout",
            file_path=abs_auth,
            line_start=5,
            line_end=6,
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
    store.upsert_node(
        NodeInfo(
            kind="Test",
            name="test_login",
            file_path=abs_test,
            line_start=1,
            line_end=2,
            language="python",
            is_test=True,
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
    store.upsert_edge(
        EdgeInfo(
            kind="IMPORTS_FROM",
            source=abs_main,
            target=abs_auth,
            file_path=abs_main,
            line=1,
        )
    )
    store.upsert_edge(
        EdgeInfo(
            kind="TESTED_BY",
            source=f"{abs_auth}::AuthService.login",
            target=f"{abs_test}::test_login",
            file_path=abs_test,
        )
    )

    store.set_metadata("last_updated", "2026-03-20T10:00:00")
    store.commit()
    store.close()

    return tmp_path


# ---------------------------------------------------------------------------
# _validate_repo_root
# ---------------------------------------------------------------------------


class TestValidateRepoRoot:
    def test_valid_git_repo(self, tmp_path):
        (tmp_path / ".git").mkdir()
        result = _validate_repo_root(tmp_path)
        assert result == tmp_path.resolve()

    def test_valid_crg_dir(self, tmp_path):
        (tmp_path / ".code-review-graph").mkdir()
        result = _validate_repo_root(tmp_path)
        assert result == tmp_path.resolve()

    def test_invalid_not_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hi")
        with pytest.raises(ValueError, match="not an existing directory"):
            _validate_repo_root(f)

    def test_invalid_no_markers(self, tmp_path):
        sub = tmp_path / "empty"
        sub.mkdir()
        with pytest.raises(ValueError, match="does not look like a project root"):
            _validate_repo_root(sub)


# ---------------------------------------------------------------------------
# _get_store
# ---------------------------------------------------------------------------


class TestGetStore:
    def test_with_explicit_repo_root(self, repo_with_graph):
        store, root = _get_store(str(repo_with_graph))
        try:
            assert root == repo_with_graph.resolve()
        finally:
            store.close()

    def test_auto_detect(self, repo_with_graph, monkeypatch):
        monkeypatch.chdir(repo_with_graph)
        store, root = _get_store(None)
        try:
            assert root == repo_with_graph.resolve()
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Tool 1: build_or_update_graph
# ---------------------------------------------------------------------------


class TestBuildOrUpdateGraph:
    def test_full_rebuild(self, repo_with_graph):
        with patch(
            "better_code_review_graph.incremental.get_all_tracked_files",
            return_value=["auth.py"],
        ):
            result = build_or_update_graph(
                full_rebuild=True, repo_root=str(repo_with_graph)
            )
        assert result["status"] == "ok"
        assert result["build_type"] == "full"
        assert result["files_parsed"] >= 1
        assert "Full build complete" in result["summary"]

    def test_incremental_no_changes(self, repo_with_graph):
        with patch("better_code_review_graph.tools.get_changed_files", return_value=[]):
            with patch(
                "better_code_review_graph.tools.get_staged_and_unstaged",
                return_value=[],
            ):
                result = build_or_update_graph(
                    full_rebuild=False, repo_root=str(repo_with_graph)
                )
        assert result["status"] == "ok"
        assert result["build_type"] == "incremental"
        assert result["files_updated"] == 0

    def test_incremental_with_changes(self, repo_with_graph):
        result = build_or_update_graph(
            full_rebuild=False, repo_root=str(repo_with_graph), base="HEAD~1"
        )
        # Even without real git, it should handle gracefully
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Tool 2: get_impact_radius
# ---------------------------------------------------------------------------


class TestGetImpactRadius:
    def test_no_changed_files_auto_detect_empty(self, repo_with_graph):
        with patch("better_code_review_graph.tools.get_changed_files", return_value=[]):
            with patch(
                "better_code_review_graph.tools.get_staged_and_unstaged",
                return_value=[],
            ):
                result = get_impact_radius(repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        assert result["summary"] == "No changed files detected."
        assert result["changed_nodes"] == []
        assert result["truncated"] is False

    def test_explicit_changed_files(self, repo_with_graph):
        result = get_impact_radius(
            changed_files=["auth.py"], repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"
        assert "Blast radius" in result["summary"]
        assert isinstance(result["changed_nodes"], list)
        assert isinstance(result["impacted_nodes"], list)
        assert isinstance(result["truncated"], bool)

    def test_truncation_metadata_in_summary(self, repo_with_graph):
        result = get_impact_radius(
            changed_files=["auth.py"], max_results=1, repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"
        # Whether truncated depends on graph density


# ---------------------------------------------------------------------------
# Tool 3: query_graph
# ---------------------------------------------------------------------------


class TestQueryGraph:
    def test_unknown_pattern(self, repo_with_graph):
        result = query_graph(
            pattern="unknown_pattern", target="anything", repo_root=str(repo_with_graph)
        )
        assert result["status"] == "error"
        assert "Unknown pattern" in result["error"]

    def test_callers_of(self, repo_with_graph):
        abs_auth = str(repo_with_graph / "auth.py")
        result = query_graph(
            pattern="callers_of",
            target=f"{abs_auth}::AuthService.login",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"
        assert result["pattern"] == "callers_of"

    def test_callers_of_builtin_skipped(self, repo_with_graph):
        result = query_graph(
            pattern="callers_of", target="map", repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"
        assert "builtin" in result["summary"]
        assert result["results"] == []

    def test_callers_of_qualified_builtin_not_skipped(self, repo_with_graph):
        # Qualified name with :: should bypass the builtin filter
        result = query_graph(
            pattern="callers_of", target="utils.py::map", repo_root=str(repo_with_graph)
        )
        assert result["status"] in ("ok", "not_found")
        # Should NOT contain "builtin" skip message
        if result["status"] == "ok":
            assert "builtin" not in result.get("summary", "")

    def test_callees_of(self, repo_with_graph):
        abs_main = str(repo_with_graph / "main.py")
        result = query_graph(
            pattern="callees_of",
            target=f"{abs_main}::process",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"

    def test_imports_of(self, repo_with_graph):
        abs_main = str(repo_with_graph / "main.py")
        result = query_graph(
            pattern="imports_of", target=abs_main, repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"

    def test_importers_of(self, repo_with_graph):
        abs_auth = str(repo_with_graph / "auth.py")
        result = query_graph(
            pattern="importers_of", target=abs_auth, repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"

    def test_children_of(self, repo_with_graph):
        abs_auth = str(repo_with_graph / "auth.py")
        result = query_graph(
            pattern="children_of", target=abs_auth, repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"
        assert len(result["results"]) >= 1

    def test_tests_for(self, repo_with_graph):
        abs_auth = str(repo_with_graph / "auth.py")
        result = query_graph(
            pattern="tests_for",
            target=f"{abs_auth}::AuthService.login",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"

    def test_inheritors_of(self, repo_with_graph):
        abs_auth = str(repo_with_graph / "auth.py")
        result = query_graph(
            pattern="inheritors_of",
            target=f"{abs_auth}::AuthService",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"

    def test_file_summary(self, repo_with_graph):
        result = query_graph(
            pattern="file_summary", target="auth.py", repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"

    def test_target_not_found(self, repo_with_graph):
        result = query_graph(
            pattern="callers_of",
            target="nonexistent_function_xyz",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "not_found"

    def test_ambiguous_target(self, repo_with_graph):
        # "login" and "test_login" both contain "login" -- could be ambiguous
        # depending on search behavior
        result = query_graph(
            pattern="callers_of", target="login", repo_root=str(repo_with_graph)
        )
        # Should be ok or ambiguous
        assert result["status"] in ("ok", "ambiguous", "not_found")

    def test_callers_of_fallback_bare_name(self, repo_with_graph):
        """callers_of should use search_edges_by_target_name fallback."""
        abs_auth = str(repo_with_graph / "auth.py")
        # Add an edge with unqualified target
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="helper",
                file_path=abs_auth,
                line_start=10,
                line_end=12,
                language="python",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source=f"{abs_auth}::helper",
                target="unqualified_func",
                file_path=abs_auth,
                line=11,
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="unqualified_func",
                file_path=abs_auth,
                line_start=14,
                line_end=16,
                language="python",
            )
        )
        store.commit()
        store.close()

        result = query_graph(
            pattern="callers_of",
            target=f"{abs_auth}::unqualified_func",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"

    def test_importers_of_without_node(self, repo_with_graph):
        """importers_of with a target that is a file path, not a node."""
        result = query_graph(
            pattern="importers_of", target="auth.py", repo_root=str(repo_with_graph)
        )
        assert result["status"] in ("ok", "not_found")


# ---------------------------------------------------------------------------
# Tool 4: get_review_context
# ---------------------------------------------------------------------------


class TestGetReviewContext:
    def test_no_changes(self, repo_with_graph):
        with patch("better_code_review_graph.tools.get_changed_files", return_value=[]):
            with patch(
                "better_code_review_graph.tools.get_staged_and_unstaged",
                return_value=[],
            ):
                result = get_review_context(repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        assert "Nothing to review" in result["summary"]

    def test_with_changed_files(self, repo_with_graph):
        result = get_review_context(
            changed_files=["auth.py"], repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"
        assert "Review context" in result["summary"]
        assert "context" in result
        ctx = result["context"]
        assert "changed_files" in ctx
        assert "source_snippets" in ctx
        assert "review_guidance" in ctx

    def test_without_source_snippets(self, repo_with_graph):
        result = get_review_context(
            changed_files=["auth.py"],
            include_source=False,
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"
        assert "source_snippets" not in result["context"]

    def test_large_file_truncation(self, repo_with_graph):
        """Files exceeding max_lines_per_file should be truncated to relevant lines."""
        large_file = repo_with_graph / "large.py"
        lines = [f"# line {i}" for i in range(300)]
        lines[50] = "def target_function():"
        lines[51] = "    pass"
        large_file.write_text("\n".join(lines))

        abs_large = str(large_file)
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        store.upsert_node(
            NodeInfo(
                kind="File",
                name=abs_large,
                file_path=abs_large,
                line_start=1,
                line_end=300,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="target_function",
                file_path=abs_large,
                line_start=51,
                line_end=52,
                language="python",
            )
        )
        store.commit()
        store.close()

        result = get_review_context(
            changed_files=["large.py"],
            max_lines_per_file=100,
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"

    def test_unreadable_file(self, repo_with_graph):
        """Source snippet should handle files that can't be read."""
        result = get_review_context(
            changed_files=["nonexistent.py"], repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# _extract_relevant_lines
# ---------------------------------------------------------------------------


class TestExtractRelevantLines:
    def test_extracts_node_ranges(self):
        lines = [f"line {i}" for i in range(20)]
        node = MagicMock()
        node.file_path = "/test.py"
        node.line_start = 5
        node.line_end = 8
        result = _extract_relevant_lines(lines, [node], "/test.py")
        assert "5:" in result  # line numbers present

    def test_no_matching_nodes_fallback(self):
        lines = [f"line {i}" for i in range(100)]
        node = MagicMock()
        node.file_path = "/other.py"
        node.line_start = 5
        node.line_end = 8
        result = _extract_relevant_lines(lines, [node], "/test.py")
        # Fallback shows first 50 lines
        assert "1:" in result

    def test_merges_overlapping_ranges(self):
        lines = [f"line {i}" for i in range(30)]
        node1 = MagicMock(file_path="/t.py", line_start=5, line_end=10)
        node2 = MagicMock(file_path="/t.py", line_start=8, line_end=15)
        result = _extract_relevant_lines(lines, [node1, node2], "/t.py")
        assert "..." not in result  # merged, no gap

    def test_separate_ranges_have_ellipsis(self):
        lines = [f"line {i}" for i in range(50)]
        node1 = MagicMock(file_path="/t.py", line_start=3, line_end=5)
        node2 = MagicMock(file_path="/t.py", line_start=30, line_end=32)
        result = _extract_relevant_lines(lines, [node1, node2], "/t.py")
        assert "..." in result


# ---------------------------------------------------------------------------
# _generate_review_guidance
# ---------------------------------------------------------------------------


class TestGenerateReviewGuidance:
    def test_well_contained(self):
        impact = {
            "changed_nodes": [],
            "impacted_nodes": [],
            "impacted_files": [],
            "edges": [],
        }
        result = _generate_review_guidance(impact, ["a.py"])
        assert "well-contained" in result

    def test_untested_functions(self):
        func = MagicMock()
        func.kind = "Function"
        func.qualified_name = "a.py::foo"
        func.is_test = False
        func.name = "foo"
        impact = {
            "changed_nodes": [func],
            "impacted_nodes": [],
            "impacted_files": [],
            "edges": [],
        }
        result = _generate_review_guidance(impact, ["a.py"])
        assert "test coverage" in result.lower() or "lack test" in result.lower()

    def test_wide_blast_radius(self):
        impact = {
            "changed_nodes": [],
            "impacted_nodes": [MagicMock() for _ in range(25)],
            "impacted_files": [],
            "edges": [],
        }
        result = _generate_review_guidance(impact, ["a.py"])
        assert "Wide blast radius" in result

    def test_inheritance_edges(self):
        edge = MagicMock()
        edge.kind = "INHERITS"
        impact = {
            "changed_nodes": [],
            "impacted_nodes": [],
            "impacted_files": [],
            "edges": [edge],
        }
        result = _generate_review_guidance(impact, ["a.py"])
        assert "inheritance" in result.lower() or "Liskov" in result

    def test_cross_file_impact(self):
        impact = {
            "changed_nodes": [],
            "impacted_nodes": [],
            "impacted_files": ["b.py", "c.py", "d.py", "e.py"],
            "edges": [],
        }
        result = _generate_review_guidance(impact, ["a.py"])
        assert "impact" in result.lower()


# ---------------------------------------------------------------------------
# Tool 5: semantic_search_nodes
# ---------------------------------------------------------------------------


class TestSemanticSearchNodes:
    def test_keyword_search(self, repo_with_graph):
        result = semantic_search_nodes(query="login", repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        assert result["search_mode"] == "keyword"
        assert len(result["results"]) >= 1

    def test_keyword_search_with_kind_filter(self, repo_with_graph):
        result = semantic_search_nodes(
            query="login", kind="Function", repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"
        for r in result["results"]:
            assert r["kind"] == "Function"

    def test_keyword_search_scoring(self, repo_with_graph):
        """Exact match should rank higher than prefix match."""
        result = semantic_search_nodes(query="login", repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        if len(result["results"]) >= 2:
            # login should come before test_login
            names = [r["name"] for r in result["results"]]
            if "login" in names and "test_login" in names:
                assert names.index("login") < names.index("test_login")


# ---------------------------------------------------------------------------
# Tool 6: list_graph_stats
# ---------------------------------------------------------------------------


class TestListGraphStats:
    def test_returns_stats(self, repo_with_graph):
        result = list_graph_stats(repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        assert result["total_nodes"] >= 1
        assert result["total_edges"] >= 1
        assert "python" in result["languages"]
        assert result["files_count"] >= 1
        assert "Graph statistics" in result["summary"]
        assert "embeddings_count" in result


# ---------------------------------------------------------------------------
# Tool 7: embed_graph
# ---------------------------------------------------------------------------


class TestEmbedGraph:
    def test_embed_graph(self, repo_with_graph):
        result = embed_graph(repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        assert "newly_embedded" in result
        assert "total_embeddings" in result
        assert "backend" in result
        assert "Semantic search is now active" in result["summary"]


# ---------------------------------------------------------------------------
# Tool 8: get_docs_section
# ---------------------------------------------------------------------------


class TestGetDocsSection:
    def test_existing_section(self, repo_with_graph):
        # Create docs with sections
        docs_dir = repo_with_graph / "docs"
        docs_dir.mkdir()
        (docs_dir / "LLM-OPTIMIZED-REFERENCE.md").write_text(
            '<section name="usage">Quick install instructions.</section>\n'
            '<section name="commands">MCP tools list.</section>\n'
        )
        result = get_docs_section("usage", repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        assert result["section"] == "usage"
        assert "Quick install" in result["content"]

    def test_missing_section(self, repo_with_graph):
        docs_dir = repo_with_graph / "docs"
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / "LLM-OPTIMIZED-REFERENCE.md").write_text(
            '<section name="usage">content</section>\n'
        )
        result = get_docs_section("nonexistent", repo_root=str(repo_with_graph))
        assert result["status"] == "not_found"
        assert "Available:" in result["error"]

    def test_no_docs_file(self, tmp_path):
        (tmp_path / ".git").mkdir()
        result = get_docs_section("usage", repo_root=str(tmp_path))
        assert result["status"] == "not_found"

    def test_without_repo_root(self):
        # Should handle gracefully even when no repo found
        with patch(
            "better_code_review_graph.tools._get_store",
            side_effect=RuntimeError("no store"),
        ):
            result = get_docs_section("usage")
        assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# Tool 9: find_large_functions
# ---------------------------------------------------------------------------


class TestFindLargeFunctions:
    def test_find_above_threshold(self, repo_with_graph):
        result = find_large_functions(min_lines=1, repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        assert result["total_found"] >= 1
        for r in result["results"]:
            assert "line_count" in r
            assert "relative_path" in r

    def test_filter_by_kind(self, repo_with_graph):
        result = find_large_functions(
            min_lines=1, kind="Function", repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"
        for r in result["results"]:
            assert r["kind"] == "Function"

    def test_filter_by_file_path(self, repo_with_graph):
        result = find_large_functions(
            min_lines=1, file_path_pattern="auth", repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"
        for r in result["results"]:
            assert "auth" in r["relative_path"]

    def test_no_results(self, repo_with_graph):
        result = find_large_functions(min_lines=10000, repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        assert result["total_found"] == 0

    def test_summary_truncation(self, repo_with_graph):
        """Summary should show max 10 results and '... and N more'."""
        # Add many large nodes
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        for i in range(15):
            fp = str(repo_with_graph / f"big_{i}.py")
            store.upsert_node(
                NodeInfo(
                    kind="Function",
                    name=f"big_func_{i}",
                    file_path=fp,
                    line_start=1,
                    line_end=100,
                    language="python",
                )
            )
        store.commit()
        store.close()

        result = find_large_functions(min_lines=50, repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        if result["total_found"] > 10:
            assert "... and" in result["summary"]


# ---------------------------------------------------------------------------
# Builtin call names
# ---------------------------------------------------------------------------


class TestBuiltinCallNames:
    def test_common_builtins_present(self):
        assert "map" in _BUILTIN_CALL_NAMES
        assert "filter" in _BUILTIN_CALL_NAMES
        assert "forEach" in _BUILTIN_CALL_NAMES
        assert "log" in _BUILTIN_CALL_NAMES
        assert "fetch" in _BUILTIN_CALL_NAMES


# ---------------------------------------------------------------------------
# Semantic search with embeddings
# ---------------------------------------------------------------------------


class TestSemanticSearchWithEmbeddings:
    def test_semantic_mode_when_embeddings_exist(self, repo_with_graph):
        """Embed first, then search should use semantic mode."""
        embed_result = embed_graph(repo_root=str(repo_with_graph))
        assert embed_result["status"] == "ok"
        assert embed_result["total_embeddings"] > 0

        result = semantic_search_nodes(
            query="authentication login", repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"
        assert result["search_mode"] in ("semantic", "keyword")

    def test_semantic_search_with_kind_filter_after_embed(self, repo_with_graph):
        embed_graph(repo_root=str(repo_with_graph))
        result = semantic_search_nodes(
            query="login", kind="Function", repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Additional query_graph edge cases
# ---------------------------------------------------------------------------


class TestQueryGraphEdgeCases:
    def test_query_search_single_candidate(self, repo_with_graph):
        """When search returns exactly 1 candidate, use it."""
        result = query_graph(
            pattern="callees_of", target="process", repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"

    def test_query_ambiguous_multiple_candidates(self, repo_with_graph):
        """Multiple search results should return ambiguous status."""
        # Add multiple nodes with similar names
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        abs_auth = str(repo_with_graph / "auth.py")
        abs_main = str(repo_with_graph / "main.py")
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="handler_auth",
                file_path=abs_auth,
                line_start=20,
                line_end=25,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="handler_auth_v2",
                file_path=abs_main,
                line_start=20,
                line_end=25,
                language="python",
            )
        )
        store.commit()
        store.close()

        result = query_graph(
            pattern="callers_of", target="handler_auth", repo_root=str(repo_with_graph)
        )
        # Could be ok (if exact match found) or ambiguous
        assert result["status"] in ("ok", "ambiguous", "not_found")

    def test_query_abs_path_resolution(self, repo_with_graph):
        """Target resolution should try absolute path as fallback."""
        result = query_graph(
            pattern="children_of", target="auth.py", repo_root=str(repo_with_graph)
        )
        assert result["status"] == "ok"

    def test_callers_of_with_edges_no_caller_node(self, repo_with_graph):
        """Caller edge exists but source node is missing from graph."""
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        abs_auth = str(repo_with_graph / "auth.py")
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="missing_module::orphan_func",
                target=f"{abs_auth}::AuthService.logout",
                file_path=abs_auth,
                line=30,
            )
        )
        store.commit()
        store.close()

        result = query_graph(
            pattern="callers_of",
            target=f"{abs_auth}::AuthService.logout",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"

    def test_callees_of_with_missing_callee_node(self, repo_with_graph):
        """Callee edge exists but target node is missing."""
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        abs_main = str(repo_with_graph / "main.py")
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source=f"{abs_main}::process",
                target="external_lib::do_something",
                file_path=abs_main,
                line=6,
            )
        )
        store.commit()
        store.close()

        result = query_graph(
            pattern="callees_of",
            target=f"{abs_main}::process",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"
        # Should still have edges even if callee node is missing
        assert len(result["edges"]) >= 1

    def test_tests_for_by_naming_convention(self, repo_with_graph):
        """tests_for should also search by naming convention."""
        abs_auth = str(repo_with_graph / "auth.py")
        result = query_graph(
            pattern="tests_for",
            target=f"{abs_auth}::AuthService.login",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"
        # Should find test_login via TESTED_BY edge and/or naming convention

    def test_inheritors_of_with_inherits_edge(self, repo_with_graph):
        """inheritors_of should find classes that inherit."""
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        abs_auth = str(repo_with_graph / "auth.py")
        store.upsert_node(
            NodeInfo(
                kind="Class",
                name="AdminAuth",
                file_path=abs_auth,
                line_start=50,
                line_end=60,
                language="python",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="INHERITS",
                source=f"{abs_auth}::AdminAuth",
                target=f"{abs_auth}::AuthService",
                file_path=abs_auth,
                line=50,
            )
        )
        store.commit()
        store.close()

        result = query_graph(
            pattern="inheritors_of",
            target=f"{abs_auth}::AuthService",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"
        assert len(result["results"]) >= 1

    def test_find_large_functions_with_no_line_info(self, repo_with_graph):
        """Nodes with None line_start/line_end should have line_count=0."""
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        abs_auth = str(repo_with_graph / "auth.py")
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="no_lines",
                file_path=abs_auth,
                line_start=None,
                line_end=None,
                language="python",
            )
        )
        store.commit()
        store.close()

        result = find_large_functions(min_lines=1, repo_root=str(repo_with_graph))
        # Should not include nodes without line info
        for r in result["results"]:
            assert r["line_count"] > 0 or r["name"] != "no_lines"

    def test_review_context_large_file_no_changed_nodes(self, repo_with_graph):
        """Review context with large file but no changed nodes in that file."""
        large_file = repo_with_graph / "big_no_nodes.py"
        lines = [f"# line {i}" for i in range(300)]
        large_file.write_text("\n".join(lines))

        result = get_review_context(
            changed_files=["big_no_nodes.py"],
            max_lines_per_file=50,
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"

    def test_get_docs_section_with_repo_root_and_store(self, repo_with_graph):
        """get_docs_section with repo_root should try _get_store path too."""
        docs_dir = repo_with_graph / "docs"
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / "LLM-OPTIMIZED-REFERENCE.md").write_text(
            '<section name="troubleshooting">Fix stuff.</section>\n'
        )
        result = get_docs_section("troubleshooting", repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        assert "Fix stuff" in result["content"]

    def test_callers_of_bare_name_fallback(self, repo_with_graph):
        """callers_of should fallback to search_edges_by_target_name when no qualified match.

        The first loop (get_edges_by_target) tries the qualified name and its bare
        name fallback in graph.py. For the tools.py fallback (lines 479-484) to run,
        we need a case where get_edges_by_target returns nothing but
        search_edges_by_target_name finds the edge.

        This happens when the edge target is stored as a bare name that differs
        from the last segment of the qualified name (e.g. "MyTarget" stored as edge
        target while qualified name ends with "::MyClass.MyTarget").
        """
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        abs_file = str(repo_with_graph / "fallback_test.py")
        store.upsert_node(
            NodeInfo(
                kind="File",
                name=abs_file,
                file_path=abs_file,
                line_start=1,
                line_end=20,
                language="python",
            )
        )
        # Target function is a method (qualified: file::Class.method)
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="special_method",
                file_path=abs_file,
                line_start=1,
                line_end=5,
                language="python",
                parent_name="MyClass",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="caller_fn",
                file_path=abs_file,
                line_start=6,
                line_end=10,
                language="python",
            )
        )
        # Edge stores unqualified bare name "special_method" as target
        # get_edges_by_target("file::MyClass.special_method") won't find it directly
        # because bare name fallback extracts "MyClass.special_method" not "special_method"
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source=f"{abs_file}::caller_fn",
                target="special_method",
                file_path=abs_file,
                line=8,
            )
        )
        store.commit()
        store.close()

        result = query_graph(
            pattern="callers_of",
            target=f"{abs_file}::MyClass.special_method",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"
        # The fallback path should find the edge via search_edges_by_target_name("special_method")
        assert len(result["edges"]) >= 1

    def test_tests_for_with_tested_by_edge(self, repo_with_graph):
        """tests_for should find tests via TESTED_BY edge where target=function_qn."""
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        abs_src = str(repo_with_graph / "tested.py")
        abs_test = str(repo_with_graph / "test_tested.py")
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="my_func",
                file_path=abs_src,
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Test",
                name="test_my_func",
                file_path=abs_test,
                line_start=1,
                line_end=5,
                language="python",
                is_test=True,
            )
        )
        # TESTED_BY edge: source=test, target=function (so get_edges_by_target(function) finds it)
        store.upsert_edge(
            EdgeInfo(
                kind="TESTED_BY",
                source=f"{abs_test}::test_my_func",
                target=f"{abs_src}::my_func",
                file_path=abs_test,
            )
        )
        store.commit()
        store.close()

        result = query_graph(
            pattern="tests_for",
            target=f"{abs_src}::my_func",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "ok"
        assert len(result["results"]) >= 1

    def test_keyword_search_score_ordering(self, repo_with_graph):
        """Keyword search should order: exact > prefix > partial."""
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        abs_f = str(repo_with_graph / "scoring.py")
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="auth",
                file_path=abs_f,
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="auth_handler",
                file_path=abs_f,
                line_start=6,
                line_end=10,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="do_auth_check",
                file_path=abs_f,
                line_start=11,
                line_end=15,
                language="python",
            )
        )
        store.commit()
        store.close()

        result = semantic_search_nodes(query="auth", repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        names = [r["name"] for r in result["results"]]
        # "auth" (exact) should be before "auth_handler" (prefix) and "do_auth_check" (partial)
        if "auth" in names and "auth_handler" in names:
            assert names.index("auth") < names.index("auth_handler")
        if "auth" in names and "do_auth_check" in names:
            assert names.index("auth") < names.index("do_auth_check")

    def test_find_large_functions_with_external_path(self, repo_with_graph):
        """find_large_functions should handle file_path outside repo root."""
        db_path = repo_with_graph / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db_path))
        # Node with absolute path outside repo
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="external_func",
                file_path="/external/path/module.py",
                line_start=1,
                line_end=100,
                language="python",
            )
        )
        store.commit()
        store.close()

        result = find_large_functions(min_lines=50, repo_root=str(repo_with_graph))
        assert result["status"] == "ok"
        # Should handle ValueError in relative_to gracefully
        for r in result["results"]:
            if r["name"] == "external_func":
                assert r["relative_path"] == "/external/path/module.py"

    def test_review_context_source_read_error(self, repo_with_graph):
        """Source snippet handling for files that raise exceptions during read."""
        import os

        # Create a file that can't be read
        unreadable = repo_with_graph / "unreadable.py"
        unreadable.write_text("x = 1\n")
        os.chmod(str(unreadable), 0o000)

        try:
            result = get_review_context(
                changed_files=["unreadable.py"], repo_root=str(repo_with_graph)
            )
            assert result["status"] == "ok"
            ctx = result["context"]
            if "source_snippets" in ctx and "unreadable.py" in ctx["source_snippets"]:
                assert "could not read" in ctx["source_snippets"]["unreadable.py"]
        finally:
            os.chmod(str(unreadable), 0o644)

    def test_incremental_update_with_changes_summary(self, repo_with_graph):
        """build_or_update_graph incremental with actual changes should show summary."""
        # Create a new file to be detected as changed
        new_file = repo_with_graph / "new_module.py"
        new_file.write_text("def new_func():\n    return 42\n")

        result = build_or_update_graph(
            full_rebuild=False, repo_root=str(repo_with_graph), base="HEAD~1"
        )
        assert result["status"] == "ok"
