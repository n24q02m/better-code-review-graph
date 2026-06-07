from pathlib import Path
from unittest.mock import MagicMock, patch

from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.tools import _lookup_node_directly


def test_lookup_node_by_qualified_name(tmp_graph_store, tmp_path):
    # Setup: node in store
    node_info = NodeInfo(
        kind="Function",
        name="my_func",
        file_path="src/lib.py",
        line_start=1,
        line_end=10,
        language="python",
    )
    tmp_graph_store.upsert_node(node_info)

    # Target is the qualified name (in this case, it might be the same as name if no parent)
    # GraphStore._make_qualified uses file_path::name or file_path::parent.name
    qn = "src/lib.py::my_func"

    node = _lookup_node_directly(tmp_graph_store, tmp_path, qn)
    assert node is not None
    assert node.qualified_name == qn


def test_lookup_node_by_relative_file_path(tmp_graph_store, tmp_path):
    # Create a real file so .resolve() works
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    lib_file = src_dir / "lib.py"
    lib_file.touch()

    abs_path = str(lib_file.resolve())

    node_info = NodeInfo(
        kind="File",
        name=abs_path,
        file_path=abs_path,
        line_start=1,
        line_end=100,
        language="python",
    )
    tmp_graph_store.upsert_node(node_info)

    # Lookup by relative path
    node = _lookup_node_directly(tmp_graph_store, tmp_path, "src/lib.py")
    assert node is not None
    assert node.file_path == abs_path


def test_lookup_fails_outside_root(tmp_graph_store, tmp_path):
    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "other.py"
    outside_file.touch()

    abs_path = str(outside_file.resolve())
    node_info = NodeInfo(
        kind="File",
        name=abs_path,
        file_path=abs_path,
        line_start=1,
        line_end=100,
        language="python",
    )
    tmp_graph_store.upsert_node(node_info)

    # Attempt to lookup with ../ outside root
    node = _lookup_node_directly(tmp_graph_store, tmp_path, "../outside/other.py")
    assert node is None


def test_lookup_fails_on_symlink(tmp_graph_store, tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    real_file = src_dir / "real.py"
    real_file.touch()

    link_file = src_dir / "link.py"
    link_file.symlink_to(real_file)

    abs_path = str(real_file.resolve())
    node_info = NodeInfo(
        kind="File",
        name=abs_path,
        file_path=abs_path,
        line_start=1,
        line_end=100,
        language="python",
    )
    tmp_graph_store.upsert_node(node_info)

    # Lookup by link should fail because of is_symlink() check
    node = _lookup_node_directly(tmp_graph_store, tmp_path, "src/link.py")
    assert node is None


def test_lookup_handles_oserror_on_resolve(tmp_graph_store, tmp_path):
    with patch.object(Path, "resolve", side_effect=OSError("Inaccessible")):
        node = _lookup_node_directly(tmp_graph_store, tmp_path, "some/path.py")
        assert node is None


def test_lookup_handles_valueerror_on_resolve(tmp_graph_store, tmp_path):
    # ValueError can happen in some edge cases of resolve or is_relative_to
    with patch.object(Path, "resolve", side_effect=ValueError("Invalid path")):
        node = _lookup_node_directly(tmp_graph_store, tmp_path, "some/path.py")
        assert node is None


def test_lookup_node_with_as_of(tmp_graph_store, tmp_path):
    # We need to simulate temporal nodes.
    # GraphStore.get_node uses as_of in its query.

    node_info = NodeInfo(
        kind="Function",
        name="old_func",
        file_path="src/lib.py",
        line_start=1,
        line_end=10,
        language="python",
    )
    # Manually insert with specific SHA if possible, but upsert_node doesn't take it easily.
    # However, GraphStore.get_node(target, as_of=as_of) will filter by as_of.
    # If we just use standard upsert, it might have valid_from_sha=40 zeros if CRG_TEST_ALLOW_NO_GIT=1

    tmp_graph_store.upsert_node(node_info)
    qn = "src/lib.py::old_func"

    # It should find it with empty as_of (latest)
    assert _lookup_node_directly(tmp_graph_store, tmp_path, qn, as_of="") is not None

    # If we pass a different as_of, it might not find it unless we've set up the SHAs.
    # For the purpose of testing that _lookup_node_directly PASSES as_of,
    # we can mock the store.

    mock_store = MagicMock()
    _lookup_node_directly(mock_store, tmp_path, "some_target", as_of="some_sha")
    mock_store.get_node.assert_any_call("some_target", as_of="some_sha")
