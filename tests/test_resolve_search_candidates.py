from unittest.mock import MagicMock

from better_code_review_graph.graph import GraphNode
from better_code_review_graph.tools import _resolve_search_candidates


def test_resolve_single_candidate_no_promotion():
    store = MagicMock()
    node = GraphNode(
        id=1,
        kind="Function",
        name="login",
        qualified_name="login",
        file_path="auth.py",
        line_start=10,
        line_end=20,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )
    store.search_nodes.return_value = [node]

    res_node, res_name, res_err, res_promoted = _resolve_search_candidates(
        store, "login", "callers_of", "login"
    )

    assert res_node == node
    assert res_name == "login"
    assert res_err is None
    assert res_promoted == []


def test_resolve_single_candidate_with_promotion():
    store = MagicMock()
    node = GraphNode(
        id=1,
        kind="Function",
        name="login",
        qualified_name="auth::login",
        file_path="auth.py",
        line_start=10,
        line_end=20,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )
    store.search_nodes.return_value = [node]

    # original_target does not have ::, but qualified_name does
    res_node, res_name, res_err, res_promoted = _resolve_search_candidates(
        store, "login", "callers_of", "login"
    )

    assert res_node == node
    assert res_name == "auth::login"
    assert res_err is None
    assert res_promoted == ["auth::login"]


def test_resolve_auto_pick_function():
    store = MagicMock()
    func_node = GraphNode(
        id=1,
        kind="Function",
        name="auth",
        qualified_name="auth::auth",
        file_path="auth.py",
        line_start=10,
        line_end=20,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )
    file_node = GraphNode(
        id=2,
        kind="File",
        name="auth.py",
        qualified_name="auth.py",
        file_path="auth.py",
        line_start=1,
        line_end=100,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )
    store.search_nodes.return_value = [func_node, file_node]

    # pattern is callers_of, original_target has no ::
    res_node, res_name, res_err, res_promoted = _resolve_search_candidates(
        store, "auth", "callers_of", "auth"
    )

    # Should auto-pick the function
    assert res_node == func_node
    assert res_name == "auth::auth"
    assert res_err is None
    assert res_promoted == ["auth::auth"]


def test_resolve_ambiguous_no_auto_pick_multiple_functions():
    store = MagicMock()
    node1 = GraphNode(
        id=1,
        kind="Function",
        name="login",
        qualified_name="auth::login",
        file_path="auth.py",
        line_start=10,
        line_end=20,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )
    node2 = GraphNode(
        id=2,
        kind="Function",
        name="login",
        qualified_name="other::login",
        file_path="other.py",
        line_start=5,
        line_end=15,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )
    store.search_nodes.return_value = [node1, node2]

    res_node, res_name, res_err, res_promoted = _resolve_search_candidates(
        store, "login", "callers_of", "login"
    )

    assert res_node is None
    assert res_name == "login"
    assert res_err["status"] == "ambiguous"
    assert res_err["reason"] == "ambiguous_unqualified"
    assert len(res_err["candidates"]) == 2
    assert res_promoted == []


def test_resolve_ambiguous_non_call_pattern():
    store = MagicMock()
    func_node = GraphNode(
        id=1,
        kind="Function",
        name="auth",
        qualified_name="auth::auth",
        file_path="auth.py",
        line_start=10,
        line_end=20,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )
    file_node = GraphNode(
        id=2,
        kind="File",
        name="auth.py",
        qualified_name="auth.py",
        file_path="auth.py",
        line_start=1,
        line_end=100,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )
    store.search_nodes.return_value = [func_node, file_node]

    # pattern is query_graph (or anything not callers/callees), should not auto-pick
    res_node, res_name, res_err, res_promoted = _resolve_search_candidates(
        store, "auth", "query_graph", "auth"
    )

    assert res_node is None
    assert res_err["status"] == "ambiguous"


def test_resolve_ambiguous_with_non_call_kind():
    store = MagicMock()
    func_node = GraphNode(
        id=1,
        kind="Function",
        name="Auth",
        qualified_name="auth::Auth",
        file_path="auth.py",
        line_start=10,
        line_end=20,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )
    class_node = GraphNode(
        id=2,
        kind="Class",
        name="Auth",
        qualified_name="auth::AuthClass",
        file_path="auth.py",
        line_start=1,
        line_end=100,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )
    store.search_nodes.return_value = [func_node, class_node]

    res_node, res_name, res_err, res_promoted = _resolve_search_candidates(
        store, "Auth", "callers_of", "Auth"
    )

    # Should not auto-pick because of Class node
    assert res_node is None
    assert res_err["status"] == "ambiguous"


def test_resolve_no_candidates():
    store = MagicMock()
    store.search_nodes.return_value = []

    res_node, res_name, res_err, res_promoted = _resolve_search_candidates(
        store, "nonexistent", "callers_of", "nonexistent"
    )

    assert res_node is None
    assert res_name == "nonexistent"
    assert res_err is None
    assert res_promoted == []
