from better_code_review_graph.parser import EdgeInfo


class TestGraphSearchEdgesByTargetNames:
    def test_search_edges_by_target_names_empty(self, tmp_graph_store):
        assert tmp_graph_store.search_edges_by_target_names([]) == []

    def test_search_edges_by_target_names_basic(self, tmp_graph_store):
        # Setup edges
        tmp_graph_store.upsert_edge(
            EdgeInfo(
                kind="CALLS", source="src1", target="target1", file_path="f1.py", line=1
            )
        )
        tmp_graph_store.upsert_edge(
            EdgeInfo(
                kind="CALLS", source="src2", target="target2", file_path="f1.py", line=2
            )
        )
        tmp_graph_store.upsert_edge(
            EdgeInfo(
                kind="CALLS", source="src3", target="target1", file_path="f1.py", line=3
            )
        )
        tmp_graph_store.commit()

        # Search for target1
        edges = tmp_graph_store.search_edges_by_target_names(["target1"])
        assert len(edges) == 2
        sources = {e.source_qualified for e in edges}
        assert sources == {"src1", "src3"}

        # Search for both target1 and target2
        edges = tmp_graph_store.search_edges_by_target_names(["target1", "target2"])
        assert len(edges) == 3

    def test_search_edges_by_target_names_kind_filtering(self, tmp_graph_store):
        # Setup edges with different kinds
        tmp_graph_store.upsert_edge(
            EdgeInfo(
                kind="CALLS", source="src1", target="target1", file_path="f1.py", line=1
            )
        )
        tmp_graph_store.upsert_edge(
            EdgeInfo(
                kind="REFERENCES",
                source="src2",
                target="target1",
                file_path="f1.py",
                line=2,
            )
        )
        tmp_graph_store.commit()

        # Default search (CALLS)
        edges = tmp_graph_store.search_edges_by_target_names(["target1"])
        assert len(edges) == 1
        assert edges[0].kind == "CALLS"

        # Explicit CALLS search
        edges = tmp_graph_store.search_edges_by_target_names(["target1"], kind="CALLS")
        assert len(edges) == 1
        assert edges[0].kind == "CALLS"

        # REFERENCES search
        edges = tmp_graph_store.search_edges_by_target_names(
            ["target1"], kind="REFERENCES"
        )
        assert len(edges) == 1
        assert edges[0].kind == "REFERENCES"

    def test_search_edges_by_target_names_deduplication(self, tmp_graph_store):
        tmp_graph_store.upsert_edge(
            EdgeInfo(
                kind="CALLS", source="src1", target="target1", file_path="f1.py", line=1
            )
        )
        tmp_graph_store.commit()

        # Duplicate names in input
        edges = tmp_graph_store.search_edges_by_target_names(["target1", "target1"])
        assert len(edges) == 1

    def test_search_edges_by_target_name_wrapper(self, tmp_graph_store):
        tmp_graph_store.upsert_edge(
            EdgeInfo(
                kind="CALLS", source="src1", target="target1", file_path="f1.py", line=1
            )
        )
        tmp_graph_store.commit()

        # Test search_edges_by_target_name (singular)
        edges = tmp_graph_store.search_edges_by_target_name("target1")
        assert len(edges) == 1
        assert edges[0].target_qualified == "target1"

    def test_search_edges_by_target_names_temporal(self, tmp_graph_store):
        # Setup edges with temporal metadata (simulated via _conn if needed,
        # but let's see if we can use as_of directly if we know what it does)
        # _temporal_filter(as_of="") -> AND valid_to_sha IS NULL

        # Insert a currently valid edge
        tmp_graph_store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="src_now",
                target="target_now",
                file_path="f1.py",
                line=1,
            )
        )
        tmp_graph_store.commit()

        # Insert an old edge (manually via SQL because upsert_edge doesn't support setting valid_to_sha)
        tmp_graph_store._conn.execute(
            "INSERT INTO edges (kind, source_qualified, target_qualified, file_path, line, valid_to_sha, updated_at) "
            "VALUES ('CALLS', 'src_old', 'target_old', 'f1.py', 10, 'some_sha', 12345)"
        )
        tmp_graph_store.commit()

        # Default search (as_of="") should only find currently valid edges
        edges = tmp_graph_store.search_edges_by_target_names(
            ["target_now", "target_old"]
        )
        assert len(edges) == 1
        assert edges[0].target_qualified == "target_now"

        # Search as_of="some_sha" should find the old edge
        # According to _temporal_filter, it looks for valid_from_sha = ? OR valid_to_sha = ?
        edges = tmp_graph_store.search_edges_by_target_names(
            ["target_old"], as_of="some_sha"
        )
        assert len(edges) == 1
        assert edges[0].target_qualified == "target_old"
