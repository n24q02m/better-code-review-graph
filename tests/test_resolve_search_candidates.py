from unittest.mock import MagicMock

from better_code_review_graph.graph import GraphNode
from better_code_review_graph.tools import _resolve_search_candidates


def make_node(kind, name, qualified_name):
    return GraphNode(
        id=1,
        kind=kind,
        name=name,
        qualified_name=qualified_name,
        file_path="test.py",
        line_start=1,
        line_end=10,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        repo_id="",
        extra={},
    )


def test_resolve_no_candidates():
    store = MagicMock()
    store.search_nodes.return_value = []

    node, target, error, promoted = _resolve_search_candidates(
        store, "missing", "some_pattern", "missing", repo="myrepo", as_of="abc"
    )

    store.search_nodes.assert_called_once_with(
        "missing", limit=5, repo="myrepo", as_of="abc"
    )
    assert node is None
    assert target == "missing"
    assert error is None
    assert promoted == []


def test_resolve_single_candidate_no_promotion():
    store = MagicMock()
    node_obj = make_node("Function", "foo", "test.py::foo")
    store.search_nodes.return_value = [node_obj]

    # original_target contains "::", so no promotion
    node, target, error, promoted = _resolve_search_candidates(
        store, "test.py::foo", "some_pattern", "test.py::foo"
    )

    assert node == node_obj
    assert target == "test.py::foo"
    assert error is None
    assert promoted == []


def test_resolve_single_candidate_with_promotion():
    store = MagicMock()
    node_obj = make_node("Function", "foo", "test.py::foo")
    store.search_nodes.return_value = [node_obj]

    # original_target does NOT contain "::", and result DOES, so it's promoted
    node, target, error, promoted = _resolve_search_candidates(
        store, "foo", "some_pattern", "foo"
    )

    assert node == node_obj
    assert target == "test.py::foo"
    assert error is None
    assert promoted == ["test.py::foo"]


def test_resolve_single_candidate_file_no_promotion():
    store = MagicMock()
    node_obj = make_node("File", "test.py", "test.py")
    store.search_nodes.return_value = [node_obj]

    # original_target does NOT contain "::", and result DOES NOT either, so no promotion
    node, target, error, promoted = _resolve_search_candidates(
        store, "test.py", "some_pattern", "test.py"
    )

    assert node == node_obj
    assert target == "test.py"
    assert error is None
    assert promoted == []


def test_resolve_auto_pick_callers_of():
    store = MagicMock()
    fn_node = make_node("Function", "auth", "auth.py::auth")
    file_node = make_node("File", "auth.py", "auth.py")
    store.search_nodes.return_value = [fn_node, file_node]

    node, target, error, promoted = _resolve_search_candidates(
        store, "auth", "callers_of", "auth"
    )

    assert node == fn_node
    assert target == "auth.py::auth"
    assert error is None
    assert promoted == ["auth.py::auth"]


def test_resolve_auto_pick_callees_of():
    store = MagicMock()
    fn_node = make_node("Function", "auth", "auth.py::auth")
    file_node = make_node("File", "auth.py", "auth.py")
    store.search_nodes.return_value = [fn_node, file_node]

    node, target, error, promoted = _resolve_search_candidates(
        store, "auth", "callees_of", "auth"
    )

    assert node == fn_node
    assert target == "auth.py::auth"
    assert error is None
    assert promoted == ["auth.py::auth"]


def test_resolve_no_auto_pick_if_qualified_target():
    store = MagicMock()
    fn_node = make_node("Function", "auth", "auth.py::auth")
    file_node = make_node("File", "auth.py", "auth.py")
    store.search_nodes.return_value = [fn_node, file_node]

    # original_target has "::", so auto-pick should NOT trigger
    node, target, error, promoted = _resolve_search_candidates(
        store, "auth.py::auth", "callers_of", "auth.py::auth"
    )

    assert node is None
    assert error is not None
    assert error["status"] == "ambiguous"
    assert len(error["candidates"]) == 2


def test_resolve_no_auto_pick_if_other_kinds_present():
    store = MagicMock()
    fn_node = make_node("Function", "auth", "auth.py::auth")
    file_node = make_node("File", "auth.py", "auth.py")
    class_node = make_node("Class", "Auth", "auth.py::Auth")
    store.search_nodes.return_value = [fn_node, file_node, class_node]

    node, target, error, promoted = _resolve_search_candidates(
        store, "auth", "callers_of", "auth"
    )

    assert node is None
    assert error is not None
    assert error["status"] == "ambiguous"


def test_resolve_no_auto_pick_if_multiple_functions():
    store = MagicMock()
    fn1 = make_node("Function", "auth", "a.py::auth")
    fn2 = make_node("Function", "auth", "b.py::auth")
    store.search_nodes.return_value = [fn1, fn2]

    node, target, error, promoted = _resolve_search_candidates(
        store, "auth", "callers_of", "auth"
    )

    assert node is None
    assert error is not None
    assert error["status"] == "ambiguous"


def test_resolve_ambiguous_non_call_graph():
    store = MagicMock()
    fn_node = make_node("Function", "auth", "auth.py::auth")
    file_node = make_node("File", "auth.py", "auth.py")
    store.search_nodes.return_value = [fn_node, file_node]

    node, target, error, promoted = _resolve_search_candidates(
        store, "auth", "children_of", "auth"
    )

    assert node is None
    assert error is not None
    assert error["status"] == "ambiguous"
    assert error["reason"] == "ambiguous_unqualified"
    assert "candidates" in error
    assert error["indexed_kinds"] == ["File", "Function"]
    assert "auth.py::auth" in error["indexed_under"]
    assert "auth.py" in error["indexed_under"]
