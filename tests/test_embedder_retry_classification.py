"""Regression tests for retry misclassification of permanent embedding errors.

Transport layers (hull-core's ``ProviderError``, httpx errors) can collapse a
provider's PERMANENT 4xx (auth 401/403, not-found 404, cohere's 422
"unsupported output_dimension") into a generically-shaped error whose message
contains "connection" or a 5xx-ish status. ``_is_retryable`` substring-matches
the error text, so a naive permanent-4xx message that mentions "connection"
would burn the full 3-attempt retry budget before failing.

These tests lock in classification on error SEMANTICS (message text): a
permanent 4xx is NOT retried (fails fast and loud), while a genuine
connection/timeout/429 IS.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hull_core.providers.openai_spec import ProviderError

import better_code_review_graph.embeddings as embeddings_module
from better_code_review_graph.embeddings import (
    _MAX_RETRIES,
    CloudEmbeddingBackend,
    _is_retryable,
)


class TestIsRetryableClassification:
    """``_is_retryable`` must classify on error semantics, not the class name."""

    def test_unsupported_dimension_is_not_retryable(self):
        # Provider body text: the tricky shape -- a permanent 422 whose
        # transport repr may carry connection/5xx shape around it.
        exc = ProviderError(
            502,
            "provider returned 502: transport error calling /embeddings: "
            'CohereException - {"message": "768 is not a valid output_dimension, '
            'use one of 256, 512, 1024, 1536"}',
        )
        assert _is_retryable(exc) is False

    def test_genuine_connection_error_is_retryable(self):
        exc = ProviderError(
            502, "transport error calling /embeddings: connection reset"
        )
        assert _is_retryable(exc) is True

    def test_rate_limit_is_retryable(self):
        exc = ProviderError(429, "rate limit exceeded")
        assert _is_retryable(exc) is True

    def test_timeout_is_retryable(self):
        exc = ProviderError(504, "Request timed out.")
        assert _is_retryable(exc) is True

    def test_invalid_api_key_is_not_retryable(self):
        exc = ProviderError(401, "invalid api key")
        assert _is_retryable(exc) is False

    def test_model_not_found_404_is_not_retryable(self):
        exc = ProviderError(404, "model does not exist")
        assert _is_retryable(exc) is False


class TestPermanentErrorNotRetriedAtBatchLevel:
    """The retry loop must fail fast on a permanent error, not burn 3 attempts."""

    def test_permanent_422_fails_fast_without_retries(self):
        # A permanent 422 must be raised after a SINGLE provider call.
        backend = CloudEmbeddingBackend(model="cohere/embed-v4.0")
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ProviderError(
                422,
                "768 is not a valid output_dimension, use one of 256, 512, 1024, 1536",
            )

        with patch.object(
            embeddings_module, "_post_embeddings", side_effect=side_effect
        ):
            with pytest.raises(ProviderError):
                backend.embed_texts(["test"], dimensions=1024)

        assert call_count == 1

    def test_genuine_connection_error_is_retried_to_exhaustion(self):
        # Contrast: a genuine connection error IS retried up to _MAX_RETRIES,
        # proving the fix narrows only the permanent class.
        backend = CloudEmbeddingBackend(model="cohere/embed-v4.0")
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ProviderError(502, "transport error: connection reset by peer")

        with patch.object(
            embeddings_module, "_post_embeddings", side_effect=side_effect
        ):
            with patch("time.sleep"):  # keep the retry loop instant
                with pytest.raises(ProviderError):
                    backend.embed_texts(["test"], dimensions=1024)

        assert call_count == _MAX_RETRIES
