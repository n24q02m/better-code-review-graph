import os
import tempfile
from pathlib import Path

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.tools import _lookup_node_directly


class TestLookupNodeDirectly:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.store = GraphStore(self.tmp_db.name)

        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name).resolve()

        yield

        self.store.close()
        os.unlink(self.tmp_db.name)
        self.tmp_dir.cleanup()

    def test_direct_qualified_name_lookup(self):
        # Seed a node. Qualified name will be file_path::name
        file_path = str(self.root / "file.py")
        node_info = NodeInfo(
            kind="Function",
            name="my_func",
            file_path=file_path,
            line_start=1,
            line_end=10,
            language="python",
        )
        self.store.upsert_node(node_info)
        qualified_name = f"{file_path}::my_func"

        # Test lookup by qualified name
        node = _lookup_node_directly(self.store, self.root, qualified_name)
        assert node is not None
        assert node.qualified_name == qualified_name

    def test_path_based_lookup_success(self):
        # Create a file
        file_path = self.root / "auth.py"
        file_path.touch()

        # Seed a node with absolute path as qualified name (Kind="File" does this)
        abs_path = str(file_path.resolve())
        node_info = NodeInfo(
            kind="File",
            name=abs_path,
            file_path=abs_path,
            line_start=1,
            line_end=50,
            language="python",
        )
        self.store.upsert_node(node_info)

        # Test lookup by relative path
        node = _lookup_node_directly(self.store, self.root, "auth.py")
        assert node is not None
        assert node.qualified_name == abs_path

    def test_path_based_lookup_outside_root_fails(self):
        # Create another temp dir to act as "outside"
        with tempfile.TemporaryDirectory() as outside_dir_name:
            outside_root = Path(outside_dir_name).resolve()
            outside_file = outside_root / "outside.py"
            outside_file.touch()

            # Seed a node with absolute path as qualified name
            abs_outside_path = str(outside_file)
            node_info = NodeInfo(
                kind="File",
                name=abs_outside_path,
                file_path=abs_outside_path,
                line_start=1,
                line_end=10,
                language="python",
            )
            self.store.upsert_node(node_info)

            # Try to lookup using a relative path that escapes the root
            # We want to trigger the fallback logic, so first lookup must fail.
            # "target" should be something like "../outside.py"

            # Since our root is a temp dir, and outside_dir is another temp dir,
            # they are siblings or at least in /tmp.

            relative_target = os.path.relpath(outside_file, self.root)

            node = _lookup_node_directly(self.store, self.root, relative_target)
            # It should fail because full_target.is_relative_to(root_resolved) will be False
            assert node is None

    def test_path_based_lookup_symlink_fails(self):
        # Create a file and a symlink to it
        file_path = self.root / "real.py"
        file_path.touch()
        link_path = self.root / "link.py"
        try:
            link_path.symlink_to(file_path)
        except OSError:
            pytest.skip("Symlinks not supported on this platform/filesystem")

        # Seed a node with absolute path of the real file
        abs_real_path = str(file_path.resolve())
        node_info = NodeInfo(
            kind="File",
            name=abs_real_path,
            file_path=abs_real_path,
            line_start=1,
            line_end=10,
            language="python",
        )
        self.store.upsert_node(node_info)

        # Test lookup by symlink path - should fail due to symlink check in _lookup_node_directly
        node = _lookup_node_directly(self.store, self.root, "link.py")
        assert node is None

    def test_lookup_failure(self):
        node = _lookup_node_directly(self.store, self.root, "missing.py")
        assert node is None

    def test_as_of_parameter(self):
        file_path = self.root / "versioned.py"
        file_path.touch()
        abs_path = str(file_path.resolve())

        node_info = NodeInfo(
            kind="File",
            name=abs_path,
            file_path=abs_path,
            line_start=1,
            line_end=10,
            language="python",
        )
        self.store.upsert_node(node_info)

        # Lookup with a specific SHA should fail
        node = _lookup_node_directly(
            self.store, self.root, "versioned.py", as_of="some-sha"
        )
        assert node is None

        # Lookup without as_of should succeed
        node = _lookup_node_directly(self.store, self.root, "versioned.py")
        assert node is not None
