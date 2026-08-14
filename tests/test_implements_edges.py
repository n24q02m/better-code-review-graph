"""Source-to-graph coverage for IMPLEMENTS edge production."""

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.incremental import full_build, get_db_path
from better_code_review_graph.tools import query_graph


def test_implements_edge_is_produced_by_full_build(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "storage.py").write_text(
        "from abc import ABC, abstractmethod\n"
        "\n"
        "class Storage(ABC):\n"
        "    @abstractmethod\n"
        "    def put(self): ...\n"
        "\n"
        "class DiskStorage(Storage):\n"
        "    def put(self): pass\n"
    )

    store = GraphStore(get_db_path(repo))
    try:
        result = full_build(repo, store)
        assert result["errors"] == []
        implements = [
            edge for edge in store.get_all_edges() if edge.kind == "IMPLEMENTS"
        ]
        assert any(
            edge.source_qualified.endswith("::DiskStorage")
            and edge.target_qualified.endswith("::Storage")
            for edge in implements
        ), [(edge.source_qualified, edge.target_qualified) for edge in implements]
    finally:
        store.close()

    response = query_graph(
        "inheritors_of",
        str(repo / "storage.py") + "::Storage",
        repo_root=str(repo),
    )
    assert response["status"] == "ok"
    assert any(result["name"] == "DiskStorage" for result in response["results"])
