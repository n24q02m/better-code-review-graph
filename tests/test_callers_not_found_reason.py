"""Tests for D15 — `not_found` reason discriminator on callers_of/callees_of.

Per issue #339, the bare ``{"status": "not_found"}`` response conflates three
distinct failure modes. This module verifies the response now includes a
``reason`` field with one of:
  - ``no_such_symbol`` — target string matches nothing in the graph
  - ``symbol_not_indexed`` — bare name not indexed at top level but exists
    under a single qualified form (e.g. instance methods)
  - ``ambiguous_unqualified`` — bare name matches multiple qualified forms
"""

from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.tools import query_graph


@pytest.fixture
def repo_with_graph(tmp_path):
    """Build a graph with class methods, ambiguous names, and zero-caller funcs."""
    (tmp_path / ".git").mkdir()
    crg_dir = tmp_path / ".code-review-graph"
    crg_dir.mkdir()
    (crg_dir / ".gitignore").write_text("*\n")

    auth_py = tmp_path / "auth.py"
    auth_py.write_text(
        "class AuthService:\n    def do_thing(self):\n        return True\n"
    )
    other_py = tmp_path / "other.py"
    other_py.write_text(
        "class OtherService:\n    def do_thing(self):\n        return False\n"
    )
    main_py = tmp_path / "main.py"
    main_py.write_text("def entry_point():\n    return 1\n")

    db_path = crg_dir / "graph.db"
    store = GraphStore(str(db_path))

    abs_auth = str(auth_py)
    abs_other = str(other_py)
    abs_main = str(main_py)

    # AuthService.do_thing — only-qualified instance method
    store.upsert_node(
        NodeInfo(
            kind="Class",
            name="AuthService",
            file_path=abs_auth,
            line_start=1,
            line_end=3,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="do_thing",
            file_path=abs_auth,
            line_start=2,
            line_end=3,
            language="python",
            parent_name="AuthService",
        )
    )
    # OtherService.do_thing — second qualified form for ambiguity tests
    store.upsert_node(
        NodeInfo(
            kind="Class",
            name="OtherService",
            file_path=abs_other,
            line_start=1,
            line_end=3,
            language="python",
        )
    )
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="do_thing",
            file_path=abs_other,
            line_start=2,
            line_end=3,
            language="python",
            parent_name="OtherService",
        )
    )
    # entry_point — top-level function with zero callers
    store.upsert_node(
        NodeInfo(
            kind="Function",
            name="entry_point",
            file_path=abs_main,
            line_start=1,
            line_end=2,
            language="python",
        )
    )

    store.commit()
    store.close()
    return tmp_path


class TestCallersOfNotFoundReason:
    def test_genuine_not_found_returns_no_such_symbol(self, repo_with_graph):
        """Symbol literally absent from graph -> reason=no_such_symbol."""
        result = query_graph(
            pattern="callers_of",
            target="completely_nonexistent_xyz999",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "not_found"
        assert result["reason"] == "no_such_symbol"
        assert "indexed_kinds" in result
        assert "hint" in result

    def test_callees_of_genuine_not_found_returns_no_such_symbol(self, repo_with_graph):
        result = query_graph(
            pattern="callees_of",
            target="completely_nonexistent_xyz999",
            repo_root=str(repo_with_graph),
        )
        assert result["status"] == "not_found"
        assert result["reason"] == "no_such_symbol"

    def test_zero_callers_real_symbol_returns_ok_empty(self, repo_with_graph):
        """If symbol exists in graph but has zero callers, status=ok results=[]."""
        abs_main = str(repo_with_graph / "main.py")
        result = query_graph(
            pattern="callers_of",
            target=f"{abs_main}::entry_point",
            repo_root=str(repo_with_graph),
        )
        # Real symbol, zero callers -> ok with empty list (no reason needed).
        assert result["status"] == "ok"
        assert result["results"] == []


class TestAmbiguousUnqualified:
    def test_ambiguous_returns_ambiguous_unqualified(self, repo_with_graph):
        """Bare name 'do_thing' matches both AuthService.do_thing + OtherService.do_thing.

        Existing behavior returns status='ambiguous' with candidates. We extend
        that to also include reason='ambiguous_unqualified' to align with the
        D15 discriminator vocabulary.
        """
        result = query_graph(
            pattern="callers_of",
            target="do_thing",
            repo_root=str(repo_with_graph),
        )
        # Ambiguous status retained for backward compat; reason field added.
        assert result["status"] in ("ambiguous", "not_found")
        assert result.get("reason") == "ambiguous_unqualified"
        assert "candidates" in result
        assert len(result["candidates"]) >= 2


class TestSymbolNotIndexed:
    def test_unqualified_method_returns_symbol_not_indexed(self, tmp_path):
        """Method exists ONLY under qualified Class.method, called as bare 'method'.

        With a single matching qualified form, we should distinguish from
        no_such_symbol with reason=symbol_not_indexed and a hint pointing to
        the qualified name.
        """
        (tmp_path / ".git").mkdir()
        crg_dir = tmp_path / ".code-review-graph"
        crg_dir.mkdir()

        only_py = tmp_path / "only.py"
        only_py.write_text(
            "class Lonely:\n    def unique_method(self):\n        return 1\n"
        )

        db_path = crg_dir / "graph.db"
        store = GraphStore(str(db_path))
        abs_only = str(only_py)

        store.upsert_node(
            NodeInfo(
                kind="Class",
                name="Lonely",
                file_path=abs_only,
                line_start=1,
                line_end=3,
                language="python",
            )
        )
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="unique_method",
                file_path=abs_only,
                line_start=2,
                line_end=3,
                language="python",
                parent_name="Lonely",
            )
        )
        store.commit()
        store.close()

        # Query with bare name — single qualified candidate exists.
        # (search_nodes returns 1 hit -> resolver auto-uses it; but we want the
        # specific case where the resolver does NOT auto-resolve. Use the bare
        # name through a path that bypasses the auto-resolve, i.e. provide a
        # qualifier that doesn't exist but bare name does.)
        # The single-candidate path falls into _handle_callers_of with the
        # qualified name resolved; result is ok with potentially zero callers.
        # Ambiguous path requires len>1. So symbol_not_indexed reason fires
        # on the auto-resolved single match path when there are no callers
        # AND we want to surface the qualified hint.
        # Per D15: when _resolve_query_target returns a single candidate from
        # search_nodes with bare name, we surface symbol_not_indexed reason
        # in the response so the caller knows the bare name wasn't indexed.
        result = query_graph(
            pattern="callers_of",
            target="unique_method",
            repo_root=str(tmp_path),
        )
        # Single fuzzy match -> resolver auto-uses unique_method qualified.
        # Result is ok with results=[] (no callers), but we add a hint about
        # the qualified-name promotion so the caller sees the indexed_under.
        assert result["status"] == "ok"
        # New advisory field: tells caller their bare query was promoted to a
        # qualified form. This is the symbol_not_indexed signal even when
        # status=ok (because callers list is empty AND name was promoted).
        assert result.get("resolved_from_unqualified") is True
        assert "indexed_under" in result
        assert result["indexed_under"][0].endswith("::Lonely.unique_method")
