"""Cohere output_dimension negotiation.

Cohere validates the requested embedding width against a fixed set and rejects
anything outside it before returning any vector, so the storage width (768) has
to be widened to a supported value on the way out and trimmed on the way back.
Sending 768 straight through produced ``768 is not a valid output_dimension``
and made the whole cohere leg of the fallback chain dead.

The trimming is only meaning-preserving on a Matryoshka model, which is why the
default chain pins embed-v4.0: the v3 models emit a fixed 1024-wide vector that
is not Matryoshka, so no prefix of it is a valid embedding.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.embeddings import (
    _COHERE_OUTPUT_DIMENSIONS,
    _COHERE_WIDTH_SELECTABLE_MODELS,
    _DEFAULT_EMBEDDING_CHAIN,
    CloudEmbeddingBackend,
    _cohere_output_dimension,
    _cohere_supports_width_selection,
)
from better_code_review_graph.relay_schema import _EMBEDDING_SUGGESTED

STORAGE_DIMS = 768


def _resp(dim: int, count: int = 1) -> MagicMock:
    resp = MagicMock()
    resp.data = [{"index": i, "embedding": [0.1] * dim} for i in range(count)]
    return resp


# ---------------------------------------------------------------------------
# Width selection
# ---------------------------------------------------------------------------


class TestOutputDimensionSelection:
    @pytest.mark.parametrize(
        ("requested", "expected"),
        [
            (768, 1024),  # the storage width: the case that was broken
            (1, 256),
            (256, 256),
            (257, 512),
            (512, 512),
            (1024, 1024),
            (1025, 1536),
            (1536, 1536),
        ],
    )
    def test_widens_to_the_narrowest_supported_value(self, requested, expected):
        assert _cohere_output_dimension(requested) == expected

    def test_returns_none_when_nothing_is_wide_enough(self):
        """Caller then omits the parameter and takes Cohere's default width."""
        assert _cohere_output_dimension(max(_COHERE_OUTPUT_DIMENSIONS) + 1) is None

    def test_every_selectable_value_is_accepted_by_cohere(self):
        """Whatever the storage width becomes, the negotiated value stays legal."""
        for requested in range(1, max(_COHERE_OUTPUT_DIMENSIONS) + 1):
            assert _cohere_output_dimension(requested) in _COHERE_OUTPUT_DIMENSIONS

    def test_storage_width_is_not_directly_requestable(self):
        """Guards the premise: if 768 ever became legal, this dance is pointless."""
        assert STORAGE_DIMS not in _COHERE_OUTPUT_DIMENSIONS


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class TestCohereDispatch:
    def test_requests_a_supported_width_and_trims_the_result(self):
        backend = CloudEmbeddingBackend(model="cohere/embed-v4.0", api_key="k")
        with patch("mcp_core.llm.embedding", return_value=_resp(1024)) as m:
            vectors = backend.embed_texts(["hello"], dimensions=STORAGE_DIMS)

        assert m.call_args.kwargs["dimensions"] == 1024
        assert len(vectors[0]) == STORAGE_DIMS

    def test_never_sends_an_unsupported_width(self):
        backend = CloudEmbeddingBackend(model="cohere/embed-v4.0", api_key="k")
        with patch("mcp_core.llm.embedding", return_value=_resp(1024)) as m:
            backend.embed_texts(["hello"], dimensions=STORAGE_DIMS)
        assert m.call_args.kwargs["dimensions"] in _COHERE_OUTPUT_DIMENSIONS

    def test_other_providers_keep_the_exact_width(self):
        """The negotiation is cohere-specific; nobody else pays for it."""
        backend = CloudEmbeddingBackend(
            model="openai/text-embedding-3-large", api_key="k"
        )
        with patch("mcp_core.llm.embedding", return_value=_resp(STORAGE_DIMS)) as m:
            backend.embed_texts(["hello"], dimensions=STORAGE_DIMS)
        assert m.call_args.kwargs["dimensions"] == STORAGE_DIMS

    def test_a_model_that_cannot_select_a_width_is_left_alone(self):
        """A pinned v3 model must keep failing loudly, not get silently sliced.

        Cohere accepts output_dimension when it equals the model's native width,
        so widening 768 to 1024 would succeed against v3 and hand back a vector
        we would then slice -- and v3 is not Matryoshka, so that slice is
        meaningless. Sending 768 unchanged makes the provider reject it instead.
        """
        backend = CloudEmbeddingBackend(
            model="cohere/embed-multilingual-v3.0", api_key="k"
        )
        with patch("mcp_core.llm.embedding", return_value=_resp(1024)) as m:
            backend.embed_texts(["hello"], dimensions=STORAGE_DIMS)
        assert m.call_args.kwargs["dimensions"] == STORAGE_DIMS

    def test_an_unknown_cohere_model_is_left_alone(self):
        """Unrecognised models fail loudly rather than being assumed Matryoshka."""
        backend = CloudEmbeddingBackend(model="cohere/embed-v9-imaginary", api_key="k")
        with patch("mcp_core.llm.embedding", return_value=_resp(1024)) as m:
            backend.embed_texts(["hello"], dimensions=STORAGE_DIMS)
        assert m.call_args.kwargs["dimensions"] == STORAGE_DIMS

    def test_bare_model_name_is_recognised(self):
        """The chain uses a cohere/ prefix, but a bare name resolves too."""
        assert _cohere_supports_width_selection("embed-v4.0")
        assert _cohere_supports_width_selection("cohere/embed-v4.0")
        assert not _cohere_supports_width_selection("cohere/embed-multilingual-v3.0")

    def test_no_dimensions_requested_stays_omitted(self):
        backend = CloudEmbeddingBackend(model="cohere/embed-v4.0", api_key="k")
        with patch("mcp_core.llm.embedding", return_value=_resp(1536)) as m:
            backend.embed_texts(["hello"], dimensions=None)
        assert "dimensions" not in m.call_args.kwargs
        assert m.call_args.kwargs["input_type"] == "search_document"


# ---------------------------------------------------------------------------
# Chain
# ---------------------------------------------------------------------------


class TestDefaultChain:
    def test_cohere_leg_pins_a_matryoshka_model(self):
        cohere = [m for m in _DEFAULT_EMBEDDING_CHAIN if m.startswith("cohere/")]
        assert cohere == ["cohere/embed-v4.0"]

    def test_no_v3_cohere_model_in_the_chain(self):
        """v3 is fixed-width and not Matryoshka -- it cannot reach 768."""
        assert not [
            m
            for m in _DEFAULT_EMBEDDING_CHAIN
            if m.startswith("cohere/embed-multilingual-v3")
        ]

    def test_the_pinned_model_is_one_the_negotiation_is_valid_for(self):
        """Ties the two constants together: the chain cannot drift off the list."""
        cohere = [m for m in _DEFAULT_EMBEDDING_CHAIN if m.startswith("cohere/")][0]
        assert _cohere_supports_width_selection(cohere)
        assert cohere.split("/", 1)[1] in _COHERE_WIDTH_SELECTABLE_MODELS

    def test_relay_suggestions_match_the_chain(self):
        """The setup form must not advertise a model the chain no longer uses."""
        assert _EMBEDDING_SUGGESTED == list(_DEFAULT_EMBEDDING_CHAIN)


# ---------------------------------------------------------------------------
# Live round-trip (opt-in: needs a real key)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not (os.getenv("COHERE_API_KEY") or os.getenv("CO_API_KEY")),
    reason="needs a real Cohere key",
)
def test_live_round_trip_returns_storage_width():
    """The negotiated width is accepted by the real API, not just by our mock."""
    backend = CloudEmbeddingBackend(model="cohere/embed-v4.0")
    vectors = backend.embed_texts(["def parse(path): ..."], dimensions=STORAGE_DIMS)
    assert len(vectors) == 1
    assert len(vectors[0]) == STORAGE_DIMS
