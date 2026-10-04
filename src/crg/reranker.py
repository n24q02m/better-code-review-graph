from __future__ import annotations

import math
from functools import lru_cache
from itertools import islice
from typing import Any


class LocalRerankError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def _get_reranker(model_name: str):
    from fastretrieval import TextCrossEncoder

    return TextCrossEncoder(model_name=model_name)


def _candidate_text(candidate: dict[str, Any]) -> str:
    return "\n".join(
        str(candidate.get(field) or "")
        for field in ("kind", "qualified_name", "file_path")
    )


def rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    model_name: str,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    try:
        scores = list(
            islice(
                _get_reranker(model_name).rerank(
                    query, [_candidate_text(candidate) for candidate in candidates]
                ),
                len(candidates) + 1,
            )
        )
    except Exception as error:
        raise LocalRerankError(
            f"local reranker {model_name!r} failed ({type(error).__name__})"
        ) from error
    if len(scores) != len(candidates):
        raise LocalRerankError("local reranker returned the wrong score count")

    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, (candidate, raw_score) in enumerate(
        zip(candidates, scores, strict=True)
    ):
        try:
            score = float(raw_score)
        except (TypeError, ValueError, OverflowError) as error:
            raise LocalRerankError(
                "local reranker returned an invalid score"
            ) from error
        if not math.isfinite(score):
            raise LocalRerankError("local reranker returned a non-finite score")
        enriched = dict(candidate)
        enriched["rerank_score"] = score
        ranked.append((score, index, enriched))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked]
