import logging
from unittest.mock import patch
from better_code_review_graph.summarizer import batch_summarize, BatchSummarizeResult
from better_code_review_graph.graph import GraphStore
from better_code_review_graph.parser import NodeInfo
import os

def test_repro(tmp_path):
    os.environ["GEMINI_API_KEY"] = "g-key"
    db_path = os.path.join(tmp_path, "test.db")
    store = GraphStore(db_path)
    nid = store.upsert_node(
        NodeInfo(kind="Function", name="f", file_path="x.py", line_start=1, line_end=2, language="python"),
        file_hash="h"
    )
    store._conn.execute("UPDATE nodes SET source_text='def f(): pass' WHERE id=?", (nid,))
    store._conn.commit()

    logger = logging.getLogger("better_code_review_graph.summarizer")
    print(f"Logger name: {logger.name}")
    print(f"Logger level: {logger.level}")
    print(f"Logger propagate: {logger.propagate}")
    print(f"Logger handlers: {logger.handlers}")

    # Simulate caplog behavior
    class CapLog:
        def __init__(self):
            self.records = []
            self.handler = logging.Handler()
            self.handler.emit = lambda record: self.records.append(record)
            logging.getLogger().addHandler(self.handler)
        @property
        def text(self):
            return "\n".join(r.getMessage() for r in self.records)

    caplog = CapLog()

    with patch("better_code_review_graph.summarizer.summarize_node", side_effect=RuntimeError("boom")):
        result = batch_summarize(store, max_nodes=1)

    print(f"Result errors: {result.errors}")
    print(f"Captured text:\n{caplog.text}")

if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_repro(tmp_dir)
