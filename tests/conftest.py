"""Shared fixtures and test helpers for better-code-review-graph tests."""

from __future__ import annotations

import pytest


def pytest_addoption(parser):
    """Add --setup and --browser CLI options for E2E tests."""
    parser.addoption("--setup", choices=["relay", "env", "plugin"], default="env")
    parser.addoption("--browser", choices=["chrome", "brave", "edge"], default="chrome")


@pytest.fixture(autouse=True)
def force_local_embeddings(monkeypatch):
    """Force tests to use the local ONNX embedding backend.

    Prevents tests from attempting to call external APIs (Gemini, OpenAI, Jina, Cohere)
    even if API keys are present in the environment. This ensures reproducible tests
    and avoids hitting rate limits or incurring costs during CI.
    """
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
