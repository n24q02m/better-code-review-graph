"""Task 5b: parser populates Function source_text + upsert_node persists it.

Wires the parser to capture the raw source slice for Function-kind nodes so
that ``batch_summarize`` (Task 5) actually sees candidates in production.
The column was added in Task 5 but no code populated it -- this suite locks
in the populate + persist contract.
"""

from __future__ import annotations

from unittest.mock import patch


def test_parser_populates_source_text_for_functions(tmp_path):
    """Function-kind NodeInfo must carry source_text matching the file content span."""
    from better_code_review_graph.parser import CodeParser

    py_file = tmp_path / "x.py"
    py_file.write_text(
        "def alpha():\n    return 1\n\ndef beta(x):\n    return x * 2\n",
        encoding="utf-8",
    )
    parser = CodeParser()
    nodes, _edges = parser.parse_file(py_file)

    fns = [n for n in nodes if n.kind == "Function"]
    names = {n.name: n.source_text or "" for n in fns}
    assert "alpha" in names
    assert "beta" in names
    assert "def alpha():" in names["alpha"]
    assert "return 1" in names["alpha"]
    assert "def beta(x):" in names["beta"]
    assert "return x * 2" in names["beta"]


def test_parser_skips_source_text_for_non_function_kinds(tmp_path):
    """Class/Type/Test nodes should NOT capture source_text (None) -- saves DB space."""
    from better_code_review_graph.parser import CodeParser

    py_file = tmp_path / "y.py"
    py_file.write_text(
        "class A:\n    def method(self):\n        return 1\n",
        encoding="utf-8",
    )
    parser = CodeParser()
    nodes, _edges = parser.parse_file(py_file)

    for n in nodes:
        if n.kind == "Function":
            assert n.source_text is not None and n.source_text.strip() != ""
        else:
            assert n.source_text is None, (
                f"{n.kind} '{n.name}' should not capture source_text"
            )


def test_upsert_node_persists_source_text(tmp_path):
    """GraphStore.upsert_node should write source_text from NodeInfo."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        node_id = store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="x.py",
                line_start=1,
                line_end=3,
                language="python",
                source_text="def f():\n    return 1",
            ),
            file_hash="h",
        )
        row = store._conn.execute(
            "SELECT source_text FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] == "def f():\n    return 1"
    finally:
        store.close()


def test_upsert_node_handles_none_source_text(tmp_path):
    """source_text=None (default) writes NULL -- Class/Type/Test path."""
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import NodeInfo

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        node_id = store.upsert_node(
            NodeInfo(
                kind="Class",
                name="A",
                file_path="x.py",
                line_start=1,
                line_end=3,
                language="python",
            ),
            file_hash="h",
        )
        row = store._conn.execute(
            "SELECT source_text FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        assert row[0] is None
    finally:
        store.close()


def test_batch_summarize_picks_up_parser_populated_source(tmp_path, monkeypatch):
    """End-to-end: parse -> upsert -> batch_summarize sees the Function as a candidate."""
    import hull_core.config.models

    import better_code_review_graph.summarizer as summarizer_module
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.parser import CodeParser
    from better_code_review_graph.summarizer import batch_summarize

    cell = hull_core.config.models.ModelCell(
        task="chat",
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-test",
        model="gemini/gemini-2.5-flash",
    )
    monkeypatch.setattr(summarizer_module, "summary_cell", lambda: cell)

    py_file = tmp_path / "x.py"
    py_file.write_text("def alpha():\n    return 42\n", encoding="utf-8")

    store = GraphStore(str(tmp_path / "test.db"))
    try:
        parser = CodeParser()
        nodes, _edges = parser.parse_file(py_file)
        for node in nodes:
            store.upsert_node(node, file_hash="h")

        class _Fake:
            def __init__(self, c, auth_mode="no-auth"):
                self.cell = c
                self.calls = []

            async def chat(self, messages, **kwargs):
                self.calls.append(messages)
                return "Returns 42."

            async def aclose(self):
                return None

        fake = _Fake(cell)
        with patch.object(
            summarizer_module, "OpenAICompatClient", lambda c, auth_mode: fake
        ):
            result = batch_summarize(store, max_nodes=10)

        assert result.generated >= 1, (
            "parser-populated source_text should make function visible to batch_summarize"
        )
        assert fake.calls
    finally:
        store.close()
