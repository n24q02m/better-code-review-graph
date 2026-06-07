from pathlib import Path
from unittest.mock import patch

import pytest

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
from better_code_review_graph.tools import (
    _LAST_CALLERS_RESULT,
    _get_source_snippets,
    get_review_context,
    spot_check_last_callers,
)


@pytest.fixture
def repo_with_cache(tmp_path):
    """Setup a repo and populate _LAST_CALLERS_RESULT cache."""
    (tmp_path / ".git").mkdir()
    crg = tmp_path / ".code-review-graph"
    crg.mkdir()

    file_path = tmp_path / "test.py"
    file_path.write_text("def hello(): pass")

    _LAST_CALLERS_RESULT[str(tmp_path.resolve())] = {
        "pattern": "callers_of",
        "target": "test.py::hello",
        "edges": [
            {
                "file_path": str(file_path),
                "line": 1,
                "source_qualified": "other.py::main",
                "target_qualified": "test.py::hello",
            }
        ],
    }
    return tmp_path, file_path


def test_spot_check_handles_oserror(repo_with_cache):
    repo, file_path = repo_with_cache

    original_read_text = Path.read_text

    def side_effect(self, *args, **kwargs):
        if str(self) == str(file_path):
            raise OSError("Read error")
        return original_read_text(self, *args, **kwargs)

    with patch("better_code_review_graph.tools.Path.read_text", side_effect):
        result = spot_check_last_callers(n=1, repo_root=str(repo))

    assert result["status"] == "ok"
    assert len(result["samples"]) == 1
    assert result["samples"][0]["snippet"] == "(could not read file)"


def test_get_review_context_source_snippets_handles_oserror(tmp_path):
    """Test that _get_source_snippets handles OSError (via get_review_context)."""
    repo = tmp_path
    (repo / ".git").mkdir()
    crg = repo / ".code-review-graph"
    crg.mkdir()

    # Create a dummy database
    db_path = crg / "graph.db"
    store = GraphStore(str(db_path))

    file_path = repo / "changed.py"
    file_path.write_text("print('hello')")

    # Upsert a node so it's picked up by impact radius
    node = NodeInfo(
        kind="File",
        name=str(file_path),
        file_path=str(file_path),
        line_start=1,
        line_end=1,
        language="python",
    )
    store.upsert_node(node)
    store.commit()
    store.close()

    original_read_text = Path.read_text

    def side_effect(self, *args, **kwargs):
        if str(self).endswith("changed.py"):
            raise OSError("Read error")
        return original_read_text(self, *args, **kwargs)

    # Mock git changed files
    with patch(
        "better_code_review_graph.tools.get_changed_files", return_value=["changed.py"]
    ):
        with patch("better_code_review_graph.tools.Path.read_text", side_effect):
            result = get_review_context(repo_root=str(repo))

    assert result["status"] == "ok"
    snippets = result["context"].get("source_snippets", {})
    assert "changed.py" in snippets
    assert snippets["changed.py"] == "(could not read file)"


def test_get_source_snippets_handles_resolve_oserror(tmp_path):
    """Cover the OSError/ValueError branch in _get_source_snippets loop."""
    repo = tmp_path
    (repo / ".git").mkdir()

    file_path = repo / "bad_resolve.py"
    file_path.write_text("print(1)")

    original_resolve = Path.resolve

    # Track calls to resolve()
    calls = []

    def side_effect(self, *args, **kwargs):
        calls.append(str(self))
        # Initial root.resolve() must pass
        if self == repo and len(calls) == 1:
            return original_resolve(self, *args, **kwargs)

        # parent_raw.resolve(strict=True) on line 1882 should fail to put None in cache
        if self == repo:  # parent_raw
            raise OSError("Parent resolve error")

        # full_path_raw.resolve() on line 1890 should fail
        if str(self).endswith("bad_resolve.py"):
            raise OSError("Resolve error")

        return original_resolve(self, *args, **kwargs)

    with patch("better_code_review_graph.tools.Path.resolve", side_effect):
        snippets = _get_source_snippets(repo, ["bad_resolve.py"], [], 100)

    assert snippets == {}
