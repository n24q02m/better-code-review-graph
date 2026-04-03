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

    Required to avoid network calls to OpenAI/Cohere in tests and
    to prevent CI from failing due to missing API keys.
    """
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
