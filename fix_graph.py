import re

def process(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    # The safe optimizations in graph.py
    # Pattern:
    # rows = self._conn.execute(
    #     f"SELECT * FROM nodes WHERE file_path IN "  # noqa: S608
    #     f"(SELECT value FROM json_each(?)){frag}",
    #     (json.dumps(unique_files), *frag_params),
    # ).fetchall()
    # return [self._row_to_node(r) for r in rows]

    # Let's target exactly `get_nodes_by_files`, `get_nodes_by_qualified_names`, `get_edges_by_targets`

    # 1. get_nodes_by_files
    content = content.replace(").fetchall()\n        return [self._row_to_node(r) for r in rows]", ")\n        return [self._row_to_node(r) for r in rows]")

    # 2. get_nodes_by_qualified_names (same as above replacement)

    # 3. get_edges_by_targets
    content = content.replace(").fetchall()\n        return [self._row_to_edge(r) for r in rows]", ")\n        return [self._row_to_edge(r) for r in rows]")

    # 4. get_all_edges
    content = content.replace("cursor = self._conn.execute(\"SELECT * FROM edges\")\n        return [self._row_to_edge(r) for r in cursor]", "cursor = self._conn.execute(\"SELECT * FROM edges\")\n        return [self._row_to_edge(r) for r in cursor]")

    # Wait, `get_all_edges` already doesn't use `.fetchall()`!

    # 5. get_edges_among
    content = content.replace(").fetchall()\n        return [self._row_to_edge(r) for r in rows]", ")\n        return [self._row_to_edge(r) for r in rows]")

    # 6. get_nodes_by_size (if any)
    content = content.replace(").fetchall()\n        return [self._row_to_node(r) for r in rows]", ")\n        return [self._row_to_node(r) for r in rows]")

    with open(filepath, "w") as f:
        f.write(content)

process("src/better_code_review_graph/graph.py")
