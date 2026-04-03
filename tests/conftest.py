"""Shared fixtures and test helpers for better-code-review-graph tests."""

from __future__ import annotations

import pytest

from better_code_review_graph.graph import GraphStore


def pytest_addoption(parser):
    """Add --setup and --browser CLI options for E2E tests."""
    parser.addoption("--setup", choices=["relay", "env", "plugin"], default="env")
    parser.addoption("--browser", choices=["chrome", "brave", "edge"], default="chrome")


@pytest.fixture(autouse=True)
def force_local_embeddings(monkeypatch):
    """Force tests to use the local ONNX embedding backend."""
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")


@pytest.fixture
def store(tmp_path):
    """Provide a GraphStore instance for testing."""
    db_path = tmp_path / "test_graph.db"
    return GraphStore(db_path)


@pytest.fixture
def parser():
    """Provide a Parser instance for testing."""
    from better_code_review_graph.parser import Parser

    return Parser()
