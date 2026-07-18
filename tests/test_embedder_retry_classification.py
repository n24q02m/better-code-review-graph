"""Regression tests for retry misclassification of permanent embedding errors.

litellm wraps a provider's PERMANENT 4xx (auth 401/403, not-found 404, cohere's
422 "unsupported output_dimension") in an ``APIConnectionError`` whose class name
contains "connection" and whose ``status_code`` is a synthetic 500. The old
``_is_retryable`` substring-matched the exception repr against a pattern set that
included "connection", so it classified those permanent errors as retryable and
the batch loop retried them 3x before giving up -- wasted latency on the error
path, then a delayed failure.

These tests lock in classification on error SEMANTICS (message text), not the
exception class name or the synthetic status code: a wrapped permanent 4xx is
NOT retried (fails fast and loud), while a genuine connection/timeout/429 IS.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from litellm.exceptions import APIConnectionError, RateLimitError

from better_code_review_graph.embeddings import (
    _MAX_RETRIES,
    CloudEmbeddingBackend,
    _is_retryable,
)

# The exact provider body cohere returns for an unsupported output_dimension,
# as litellm surfaces it after wrapping the 422 in APIConnectionError.
_COHERE_422_BODY = (
    'CohereException - {"message": "768 is not a valid output_dimension, '
    'use one of 256, 512, 1024, 1536"}'
)


def _wrapped_422() -> APIConnectionError:
    """A litellm APIConnectionError wrapping cohere's 422 dims rejection."""
    return APIConnectionError(
        message=_COHERE_422_BODY, llm_provider="cohere", model="embed-v4.0"
    )


class TestIsRetryableClassification:
    """`_is_retryable` must classify on error semantics, not the class name."""

    def test_wrapped_422_unsupported_dimension_is_not_retryable(self):
        exc = _wrapped_422()
        # Guard: this really is the tricky shape (class name -> "connection",
        # synthetic 500) that fooled the old substring matcher.
        assert "connection" in str(exc).lower()
        assert getattr(exc, "status_code", None) == 500

        assert _is_retryable(exc) is False

    def test_genuine_connection_error_is_retryable(self):
        exc = APIConnectionError(
            message="Connection error.", llm_provider="cohere", model="embed-v4.0"
        )
        assert _is_retryable(exc) is True

    def test_rate_limit_is_retryable(self):
        exc = RateLimitError(
            message="rate limit exceeded", llm_provider="cohere", model="embed-v4.0"
        )
        assert _is_retryable(exc) is True

    def test_timeout_is_retryable(self):
        exc = APIConnectionError(
            message="Request timed out.", llm_provider="cohere", model="embed-v4.0"
        )
        assert _is_retryable(exc) is True

    def test_invalid_api_key_is_not_retryable(self):
        exc = APIConnectionError(
            message="AuthenticationError - invalid api key",
            llm_provider="cohere",
            model="embed-v4.0",
        )
        assert _is_retryable(exc) is False

    def test_model_not_found_404_is_not_retryable(self):
        exc = APIConnectionError(
            message="NotFoundError - model does not exist (404)",
            llm_provider="cohere",
            model="embed-v4.0",
        )
        assert _is_retryable(exc) is False


class TestPermanentErrorNotRetriedAtBatchLevel:
    """The retry loop must fail fast on a permanent error, not burn 3 attempts."""

    def test_wrapped_422_fails_fast_without_retries(self):
        # Reproduces the propagation finding: a wrapped permanent 422 must be
        # raised after a SINGLE provider call, not retried 3x.
        with patch.dict(os.environ, {}, clear=True):
            backend = CloudEmbeddingBackend(
                model="cohere/embed-v4.0", api_key="test-key"
            )
            call_count = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise _wrapped_422()

            with patch("mcp_core.llm.embedding", side_effect=side_effect):
                with patch("time.sleep"):  # would be skipped anyway; guard latency
                    with pytest.raises(APIConnectionError):
                        backend.embed_texts(["test"], dimensions=768)

            assert call_count == 1

    def test_genuine_connection_error_is_retried_to_exhaustion(self):
        # Contrast: a genuine connection error IS retried up to _MAX_RETRIES,
        # proving the fix narrows only the permanent class.
        with patch.dict(os.environ, {}, clear=True):
            backend = CloudEmbeddingBackend(
                model="cohere/embed-v4.0", api_key="test-key"
            )
            call_count = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise APIConnectionError(
                    message="Connection error.",
                    llm_provider="cohere",
                    model="embed-v4.0",
                )

            with patch("mcp_core.llm.embedding", side_effect=side_effect):
                with patch("time.sleep"):
                    with pytest.raises(APIConnectionError):
                        backend.embed_texts(["test"], dimensions=768)

            assert call_count == _MAX_RETRIES
