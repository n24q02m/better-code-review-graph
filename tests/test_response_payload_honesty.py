"""Failed reads must not be reported as factual zeroes and empty lists.

Four helpers on the query/response path caught every exception and returned
a value that is indistinguishable from a real, successful answer:

* ``_build_response_header`` reported ``embeddings_count: 0`` when the
  embedding store could not be opened. Zero is a documented instruction --
  ``docs/recipes.md`` tells the caller "if ``embeddings_count == 0`` ... run
  ``graph action=embed`` first" -- and running embed cannot fix a store that
  will not open, so the caller loops.
* the same helper reported ``graph_last_updated: null`` for an unreadable
  metadata table, which reads as "never built".
* ``_list_kinds_in_graph`` returned ``[]`` for a broken graph, which reaches
  the user as ``indexed_kinds: []``: "nothing is indexed, rebuild".
* ``_scan_dynamic_dispatch_hints`` and ``CodeParser._apply_federation``
  degrade correctly but did so at ``debug`` and at no level at all
  respectively, so nobody could tell degraded output from complete output.

The first three are wrong answers. The last two are right answers delivered
silently. Both are covered here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.parser import CodeParser, EdgeInfo
from better_code_review_graph.tools import (
    _build_response_header,
    _handle_not_found,
    _list_kinds_in_graph,
    _scan_dynamic_dispatch_hints,
)

_BOOM = "disk I/O error"


def _loud(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


class TestEmbeddingsCountDoesNotFakeZero:
    def test_unreadable_embedding_store_is_not_reported_as_zero(self, tmp_path):
        """Zero is documented advice to run embed; it cannot fix this."""
        with patch(
            "better_code_review_graph.tools.EmbeddingStore",
            side_effect=RuntimeError(_BOOM),
        ):
            header = _build_response_header(None, tmp_path / "graph.db")

        assert header["embeddings_count"] != 0, (
            "reporting 0 sends the caller to 'graph action=embed' "
            "(docs/recipes.md) for a store that will not open"
        )
        assert header["embeddings_count"] is None
        assert _BOOM in header["embeddings_error"]

    def test_unreadable_embedding_store_is_logged_above_debug(self, tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        with patch(
            "better_code_review_graph.tools.EmbeddingStore",
            side_effect=RuntimeError(_BOOM),
        ):
            _build_response_header(None, tmp_path / "graph.db")

        loud = _loud(caplog)
        assert loud, f"nothing above debug; got {[r.message for r in caplog.records]}"
        assert any(_BOOM in r.getMessage() for r in loud)

    def test_keyword_only_stays_true_when_the_store_is_unreadable(self, tmp_path):
        """A store that will not open cannot serve semantic search either."""
        with patch(
            "better_code_review_graph.tools.EmbeddingStore",
            side_effect=RuntimeError(_BOOM),
        ):
            header = _build_response_header(None, tmp_path / "graph.db")
        assert header["keyword_only"] is True


class TestLastUpdatedDoesNotFakeNeverBuilt:
    def test_unreadable_metadata_carries_an_explicit_error(self):
        bad_store = MagicMock()
        bad_store.get_metadata.side_effect = RuntimeError(_BOOM)

        header = _build_response_header(bad_store, None, keyword_only=False)

        assert header["graph_last_updated"] is None
        assert _BOOM in header["graph_last_updated_error"], (
            "a null timestamp reads as 'never built'; the read failure must "
            "be stated separately"
        )

    def test_unreadable_metadata_is_logged_above_debug(self, caplog):
        caplog.set_level(logging.DEBUG)
        bad_store = MagicMock()
        bad_store.get_metadata.side_effect = RuntimeError(_BOOM)

        _build_response_header(bad_store, None, keyword_only=False)

        loud = _loud(caplog)
        assert loud, f"nothing above debug; got {[r.message for r in caplog.records]}"
        assert any(_BOOM in r.getMessage() for r in loud)


class TestIndexedKindsDoesNotFakeEmpty:
    def test_unreadable_graph_returns_none_not_empty_list(self):
        bad_store = MagicMock()
        bad_store._conn.execute.side_effect = RuntimeError(_BOOM)

        assert _list_kinds_in_graph(bad_store) is None, (
            "[] is a factual claim that nothing is indexed"
        )

    def test_unreadable_graph_is_logged_above_debug(self, caplog):
        caplog.set_level(logging.DEBUG)
        bad_store = MagicMock()
        bad_store._conn.execute.side_effect = RuntimeError(_BOOM)

        _list_kinds_in_graph(bad_store)

        loud = _loud(caplog)
        assert loud, f"nothing above debug; got {[r.message for r in caplog.records]}"
        assert any(_BOOM in r.getMessage() for r in loud)

    def test_not_found_response_does_not_claim_an_empty_graph(self):
        """The user-visible payload must not say "nothing is indexed"."""
        bad_store = MagicMock()
        bad_store._conn.execute.side_effect = RuntimeError(_BOOM)

        result = _handle_not_found(bad_store, "some_symbol")

        assert result["indexed_kinds"] != [], (
            "an empty list here tells the user to rebuild a graph that is "
            "not actually empty"
        )
        assert result["indexed_kinds"] is None
        assert "not 'nothing indexed'" in result["indexed_kinds_error"]

    def test_genuinely_empty_graph_still_reports_an_empty_list(self, tmp_graph_store):
        """A real empty graph is a fact and must keep saying so."""
        result = _handle_not_found(tmp_graph_store, "missing")

        assert result["indexed_kinds"] == []
        assert "indexed_kinds_error" not in result


class TestDegradedScansAnnounceThemselves:
    def test_dispatch_hint_scan_narrowing_is_logged_above_debug(self, tmp_path, caplog):
        """Narrowing the scan is correct; doing it silently is not."""
        caplog.set_level(logging.DEBUG)
        target = tmp_path / "target.py"
        target.write_text("def fn():\n    return 1\n")
        node = MagicMock()
        node.language = "python"
        node.file_path = str(target)

        store = MagicMock()
        store.get_edges_by_target.side_effect = RuntimeError(_BOOM)

        hits = _scan_dynamic_dispatch_hints(store, node, "fn")

        # Behaviour is unchanged: the scan still runs over the target file.
        assert isinstance(hits, list)

        loud = _loud(caplog)
        assert loud, (
            "the caller receives a narrower hint set with no way to know; "
            f"got {[r.message for r in caplog.records]}"
        )
        assert any(_BOOM in r.getMessage() for r in loud)

    def test_healthy_dispatch_hint_scan_stays_quiet(self, tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        target = tmp_path / "target.py"
        target.write_text("def fn():\n    return 1\n")
        node = MagicMock()
        node.language = "python"
        node.file_path = str(target)

        store = MagicMock()
        store.get_edges_by_target.return_value = []

        _scan_dynamic_dispatch_hints(store, node, "fn")

        assert not _loud(caplog)


class TestFederationResolverFailureIsAnnounced:
    @pytest.fixture
    def federation_args(self, tmp_path):
        src = tmp_path / "repo_a"
        src.mkdir()
        (src / "mod.py").write_text("import other\n")

        registry = MagicMock()
        registry.assign.return_value = "repo-a"
        entry = MagicMock()
        entry.repo_id = "repo-a"
        entry.path = src
        registry.entries.return_value = [entry]

        edge = EdgeInfo(
            kind="IMPORTS_FROM",
            source="mod.py::mod",
            target="other",
            file_path=str(src / "mod.py"),
            extra={"import_stmt": "import other"},
        )
        return {
            "path": src / "mod.py",
            "language": "python",
            "nodes": [],
            "edges": [edge],
            "repo_registry": registry,
            "target_repos": [MagicMock()],
        }

    def test_resolver_failure_is_logged_above_debug(self, federation_args, caplog):
        """Today this except swallows to `resolved = None` with no log."""
        caplog.set_level(logging.DEBUG)
        with patch(
            "better_code_review_graph.resolver.resolve_cross_repo_imports",
            side_effect=RuntimeError(_BOOM),
        ):
            CodeParser()._apply_federation(**federation_args)

        # Behaviour is unchanged: the edge keeps its single-repo target.
        assert federation_args["edges"][0].target == "other"

        loud = _loud(caplog)
        assert loud, (
            "cross-repo resolution failed and produced no record at any "
            f"level; got {[r.message for r in caplog.records]}"
        )
        assert any(_BOOM in r.getMessage() for r in loud)

    def test_successful_resolution_stays_quiet(self, federation_args, caplog):
        caplog.set_level(logging.DEBUG)
        with patch(
            "better_code_review_graph.resolver.resolve_cross_repo_imports",
            return_value="repo-b::other",
        ):
            CodeParser()._apply_federation(**federation_args)

        assert federation_args["edges"][0].target == "repo-b::other"
        assert not _loud(caplog)


class TestHealthyHeaderUnchanged:
    def test_no_db_path_still_reports_zero_not_an_error(self):
        """``db_path=None`` never attempts a read, so nothing failed."""
        header = _build_response_header(None, None)

        assert header["embeddings_count"] == 0
        assert header["keyword_only"] is True
        assert header["graph_last_updated"] is None
        assert "embeddings_error" not in header
        assert "graph_last_updated_error" not in header

    def test_working_store_reports_the_real_count(self, tmp_path):
        with patch("better_code_review_graph.tools.EmbeddingStore") as mock_emb:
            mock_emb.return_value.count.return_value = 42
            header = _build_response_header(None, tmp_path / "graph.db")

        assert header["embeddings_count"] == 42
        assert header["keyword_only"] is False
        assert "embeddings_error" not in header


class TestAlembicDoesNotDisableApplicationLogging:
    """Regression guard for a defect that silently defanged log assertions.

    ``migrations/env.py`` calls ``logging.config.fileConfig``, whose
    ``disable_existing_loggers`` argument defaults to ``True``. Every
    ``better_code_review_graph.*`` logger is created at import time, long
    before any migration runs, so the default set ``disabled = True`` on all
    of them for the rest of the process.

    Production never hit this: ``GraphStore`` builds its Alembic ``Config``
    programmatically and leaves ``config_file_name`` unset, so ``env.py``
    skips the ``fileConfig`` call. The test suite did hit it, because
    ``tests/test_alembic_baseline.py`` loads ``alembic.ini`` directly. From
    that point on, every log-based assertion in the run was inspecting a
    logger that could not emit -- such tests passed alone and quietly stopped
    testing anything in the full run.
    """

    def test_running_migrations_from_alembic_ini_leaves_logging_alive(self, tmp_path):
        from alembic import command
        from alembic.config import Config

        from better_code_review_graph import tools as tools_module

        repo_root = Path(__file__).resolve().parent.parent
        cfg = Config(str(repo_root / "alembic.ini"))
        cfg.set_main_option("script_location", str(repo_root / "migrations"))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'g.db'}")
        command.upgrade(cfg, "head")

        assert not tools_module.logger.disabled, (
            "alembic's fileConfig disabled the application loggers; every "
            "log-based assertion after this point is silently inert"
        )
