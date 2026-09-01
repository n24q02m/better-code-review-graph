import math
from itertools import count

import pytest

import better_code_review_graph.reranker as reranker
from better_code_review_graph.reranker import LocalRerankError, rerank_candidates

CANDIDATES = [
    {
        "kind": "Function",
        "qualified_name": "pkg.alpha",
        "file_path": "src/a.py",
        "similarity_score": 0.91,
    },
    {
        "kind": "Class",
        "qualified_name": "pkg.Beta",
        "file_path": "src/b.py",
        "similarity_score": 0.88,
    },
]


class FakeCrossEncoder:
    def __init__(self, scores):
        self.scores = scores
        self.documents = None

    def rerank(self, query, documents):
        self.documents = list(documents)
        return iter(self.scores)


def test_rerank_uses_stable_text_and_preserves_vector_score(monkeypatch):
    model = FakeCrossEncoder([0.2, 0.9])
    monkeypatch.setattr(reranker, "_get_reranker", lambda _name: model)
    result = rerank_candidates("find beta", CANDIDATES, model_name="model/id")
    assert [row["qualified_name"] for row in result] == ["pkg.Beta", "pkg.alpha"]
    assert result[0]["similarity_score"] == 0.88
    assert result[0]["rerank_score"] == 0.9
    assert model.documents == [
        "Function\npkg.alpha\nsrc/a.py",
        "Class\npkg.Beta\nsrc/b.py",
    ]


def test_rerank_preserves_original_order_for_ties(monkeypatch):
    model = FakeCrossEncoder([0.5, 0.5])
    monkeypatch.setattr(reranker, "_get_reranker", lambda _name: model)
    result = rerank_candidates("q", CANDIDATES, model_name="model/id")
    assert [row["qualified_name"] for row in result] == ["pkg.alpha", "pkg.Beta"]


@pytest.mark.parametrize("scores", [[0.1], [0.1, math.nan], [0.1, "not-a-score"]])
def test_rerank_rejects_incomplete_or_nonfinite_scores(monkeypatch, scores):
    monkeypatch.setattr(
        reranker, "_get_reranker", lambda _name: FakeCrossEncoder(scores)
    )
    with pytest.raises(LocalRerankError):
        rerank_candidates("q", CANDIDATES, model_name="model/id")


def test_rerank_bounds_overproducing_score_iterator(monkeypatch):
    class GuardedInfiniteScores:
        def __iter__(self):
            for index in count():
                if index > len(CANDIDATES):
                    raise AssertionError("score iterator consumed beyond bound")
                yield 0.1

    monkeypatch.setattr(
        reranker,
        "_get_reranker",
        lambda _name: FakeCrossEncoder(GuardedInfiniteScores()),
    )
    with pytest.raises(LocalRerankError, match="wrong score count"):
        rerank_candidates("q", CANDIDATES, model_name="model/id")
