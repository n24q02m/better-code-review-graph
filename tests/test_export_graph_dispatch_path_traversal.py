from pathlib import Path

from better_code_review_graph.tools import export_graph_dispatch


def test_export_graph_dispatch_path_traversal_blocked(
    tmp_path, _allow_temporal_migration_without_git
):
    (tmp_path / ".code-review-graph").mkdir()
    # Try to write outside the repo root
    output_path = str(tmp_path / "../out.graphml")
    result = export_graph_dispatch(
        repo_root=str(tmp_path), format="graphml", output_path=output_path
    )

    assert result["status"] == "error"
    assert "must be relative to repo root" in result["error"]


def test_export_graph_dispatch_inside_repo_allowed(
    tmp_path, _allow_temporal_migration_without_git
):
    (tmp_path / ".code-review-graph").mkdir()
    # Write inside the repo root
    output_path = str(tmp_path / "out.graphml")
    result = export_graph_dispatch(
        repo_root=str(tmp_path), format="graphml", output_path=output_path
    )

    assert result["status"] == "ok"
    assert "bytes" in result
    assert Path(output_path).exists()
