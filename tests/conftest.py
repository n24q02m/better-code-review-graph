"""Shared fixtures and test helpers for better-code-review-graph tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


def pytest_addoption(parser):
    """Add --setup and --browser CLI options for E2E tests."""
    parser.addoption("--setup", choices=["relay", "env", "plugin"], default="env")
    parser.addoption("--browser", choices=["chrome", "brave", "edge"], default="chrome")


from better_code_review_graph.graph import GraphStore  # noqa: E402
from better_code_review_graph.parser import EdgeInfo, NodeInfo  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolate_global_git_config() -> None:
    """Strip global git config so test-created repos commit deterministically."""
    os.environ.setdefault("GIT_CONFIG_GLOBAL", "/dev/null")


@pytest.fixture(scope="session", autouse=True)
def _allow_temporal_migration_without_git() -> None:
    """Opt the test session into the no-git fallback path of migration 005."""
    os.environ["CRG_TEST_ALLOW_NO_GIT"] = "1"


@pytest.fixture(autouse=True)
def force_local_embeddings(monkeypatch):
    """Force tests to use the local ONNX embedding backend."""
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")


@pytest.fixture(autouse=True)
def mock_credential_state(monkeypatch):
    """Prevent tests from triggering real relay sessions."""
    from better_code_review_graph import server as _srv
    from better_code_review_graph.credential_state import CredentialState

    def _noop_hint(result: dict) -> dict:
        return result

    monkeypatch.setattr(_srv, "_maybe_include_setup_hint", _noop_hint)
    monkeypatch.setattr(
        "better_code_review_graph.credential_state._state",
        CredentialState.CONFIGURED,
    )


@pytest.fixture(autouse=True)
def mock_qwen3_embed():
    """Mock qwen3_embed.TextEmbedding to avoid model downloads during tests."""
    import numpy as np

    with patch("qwen3_embed.TextEmbedding") as mock_cls:
        mock_model = MagicMock()
        mock_cls.return_value = mock_model

        def mock_embed(texts, **kwargs):
            dim = kwargs.get("dim", 768)
            for _ in texts:
                yield np.zeros(dim)

        mock_model.embed.side_effect = mock_embed

        def mock_query_embed(text, **kwargs):
            dim = kwargs.get("dim", 768)
            return [np.zeros(dim)]

        mock_model.query_embed.side_effect = mock_query_embed

        yield mock_model


@pytest.fixture
def tmp_graph_store(tmp_path):
    """Create a temporary GraphStore for testing."""
    db_path = tmp_path / "graph.db"
    store = GraphStore(str(db_path))
    yield store
    store.close()


def _make_node(
    name: str,
    kind: str,
    qualified_name: str,
    **kwargs,
) -> NodeInfo:
    """Helper to create a NodeInfo for testing."""
    if "::" in qualified_name:
        default_file_path = qualified_name.split("::")[0]
    else:
        default_file_path = "test.py"

    return NodeInfo(
        kind=kind,
        name=name,
        file_path=kwargs.get("file_path", default_file_path),
        line_start=kwargs.get("line_start", 1),
        line_end=kwargs.get("line_end", 10),
        language=kwargs.get("language", "python"),
        parent_name=kwargs.get("parent_name"),
        params=kwargs.get("params"),
        return_type=kwargs.get("return_type"),
        modifiers=kwargs.get("modifiers"),
        is_test=kwargs.get("is_test", False),
        extra=kwargs.get("extra", {}),
    )


def _make_edge(
    kind: str,
    source: str,
    target: str,
    file_path: str,
    line: int = 1,
    **kwargs,
) -> EdgeInfo:
    """Helper to create an EdgeInfo for testing."""
    return EdgeInfo(
        kind=kind,
        source=source,
        target=target,
        file_path=file_path,
        line=line,
        extra=kwargs.get("extra", {}),
    )
