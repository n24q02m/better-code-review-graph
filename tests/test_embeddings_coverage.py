from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.embeddings import CloudEmbeddingBackend, EmbeddingStore
from better_code_review_graph.graph import GraphNode


def _make_node(name="test", qn="f.py::test", kind="Function"):
    return GraphNode(
        id=1,
        kind=kind,
        name=name,
        qualified_name=qn,
        file_path="f.py",
        line_start=1,
        line_end=5,
        language="python",
        parent_name=None,
        params=None,
        return_type=None,
        is_test=False,
        file_hash=None,
        extra={},
    )


class TestEmbeddingsCoverage:
    def test_embed_nodes_exception_handling(self, tmp_path):
        """Verify that embed_nodes handles exceptions from the backend."""
        db = tmp_path / "test.db"
        backend = MagicMock()
        backend.name = "mock"
        backend.embed_texts.side_effect = Exception("Embedding failed")

        store = EmbeddingStore(db, backend)
        node = _make_node()

        # After fix, it should return 0 and not raise exception
        result = store.embed_nodes([node])
        assert result == 0

        store.close()

    def test_embed_batch_inner_retryable_exception(self):
        """Verify that _embed_batch_inner retries on transient errors."""
        backend = CloudEmbeddingBackend(api_key="test")
        with (
            patch.object(backend, "_call_provider") as mock_call,
            patch("time.sleep"),
        ):  # Skip delay
            # First call fails with rate limit, second succeeds
            mock_call.side_effect = [Exception("rate limit exceeded"), [[0.1] * 768]]

            result = backend.embed_texts(["hello"])
            assert len(result) == 1
            assert mock_call.call_count == 2

    def test_embed_batch_inner_non_retryable_exception(self):
        """Verify that _embed_batch_inner does not retry on fatal errors."""
        backend = CloudEmbeddingBackend(api_key="test")
        with patch.object(backend, "_call_provider") as mock_call:
            mock_call.side_effect = Exception("Fatal error")

            with pytest.raises(Exception, match="Fatal error"):
                backend.embed_texts(["hello"])

            assert mock_call.call_count == 1

    def test_embed_batch_inner_exhaust_retries(self):
        """Verify that _embed_batch_inner raises after exhausting retries."""
        backend = CloudEmbeddingBackend(api_key="test")
        with patch.object(backend, "_call_provider") as mock_call, patch("time.sleep"):
            mock_call.side_effect = Exception("rate limit")

            with pytest.raises(Exception, match="rate limit"):
                backend.embed_texts(["hello"])

            # _MAX_RETRIES is 3
            assert mock_call.call_count == 3
