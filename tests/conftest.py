"""Shared fixtures and test helpers for better-code-review-graph tests."""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser):
    """Add --setup and --browser CLI options for E2E tests."""
    parser.addoption("--setup", choices=["relay", "env", "plugin"], default="env")
    parser.addoption("--browser", choices=["chrome", "brave", "edge"], default="chrome")


from better_code_review_graph.graph import GraphStore  # noqa: E402
from better_code_review_graph.parser import EdgeInfo, NodeInfo  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _allow_temporal_migration_without_git() -> None:
    """Opt the test session into the no-git fallback path of migration 005.

    The Phase 3 Task 6 BREAKING migration (``005_temporal_columns``)
    reads ``git rev-parse HEAD`` from the repo containing the graph DB
    so it can backfill ``valid_from_sha``. Production deployments
    always satisfy this invariant — CRG only indexes git repos. The
    test suite, however, creates throwaway DBs in ``tmp_path`` /
    ``tempfile.NamedTemporaryFile`` paths that live outside any git
    repo, and many legacy tests deliberately probe code paths that
    assume those tmp dirs are NOT inside a git repo (see
    ``test_incremental.py::TestFindRepoRoot::test_returns_none_without_git``).

    Setting ``CRG_TEST_ALLOW_NO_GIT=1`` flips migration 005 to use the
    documented in-memory sentinel SHA (40 zeros) when no ``.git``
    ancestor is reachable. The migration still aborts with the
    actionable :class:`RuntimeError` in production code paths where
    the env var is unset. Tests that exercise the abort path
    explicitly clear this env var via ``monkeypatch.delenv``.
    """
    os.environ["CRG_TEST_ALLOW_NO_GIT"] = "1"


@pytest.fixture(autouse=True)
def force_local_embeddings(monkeypatch):
    """Force tests to use the local ONNX embedding backend.

    Prevents tests from attempting to hit Cohere/LiteLLM APIs if API keys
    happen to be present in the CI environment.
    """
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")


@pytest.fixture(autouse=True)
def mock_credential_state(monkeypatch):
    """Prevent tests from triggering real relay sessions.

    Patches _maybe_include_setup_hint to passthrough and
    resolve_credential_state to set CONFIGURED state.
    """
    from better_code_review_graph import server as _srv
    from better_code_review_graph.credential_state import CredentialState

    def _noop_hint(result: dict) -> dict:
        return result

    monkeypatch.setattr(_srv, "_maybe_include_setup_hint", _noop_hint)
    monkeypatch.setattr(
        "better_code_review_graph.credential_state._state",
        CredentialState.CONFIGURED,
    )


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
    """Helper to create a NodeInfo for testing.

    The ``qualified_name`` is only used to derive defaults for ``file_path``
    (everything before ``::``).  The actual qualified name stored in the DB is
    computed by ``GraphStore._make_qualified()`` from the NodeInfo fields.

    Common kwargs: file_path, line_start, line_end, language, parent_name,
    params, return_type, modifiers, is_test, extra.
    """
    # Derive file_path from qualified_name if not provided
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
    """Helper to create an EdgeInfo for testing.

    ``source`` and ``target`` map to EdgeInfo.source and EdgeInfo.target
    (which are stored as source_qualified / target_qualified in the DB).
    """
    return EdgeInfo(
        kind=kind,
        source=source,
        target=target,
        file_path=file_path,
        line=line,
        extra=kwargs.get("extra", {}),
    )
