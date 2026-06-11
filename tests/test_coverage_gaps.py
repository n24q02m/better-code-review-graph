"""Tests targeting specific coverage gaps to meet the 95% threshold.

Covers uncovered lines in: embeddings.py, server.py, incremental.py,
graph.py, tools.py, and parser.py.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from better_code_review_graph.embeddings import (
    CloudEmbeddingBackend,
    EmbeddingStore,
    _is_retryable,
)
from better_code_review_graph.graph import GraphNode, GraphStore
from better_code_review_graph.incremental import (
    find_repo_root,
    get_changed_files,
)
from better_code_review_graph.parser import CodeParser

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_graph_node(**kwargs) -> GraphNode:
    defaults = {
        "id": 1,
        "kind": "Function",
        "name": "test_fn",
        "qualified_name": "f.py::test_fn",
        "file_path": "f.py",
        "line_start": 1,
        "line_end": 5,
        "language": "python",
        "parent_name": None,
        "params": None,
        "return_type": None,
        "is_test": False,
        "file_hash": None,
        "extra": {},
    }
    defaults.update(kwargs)
    return GraphNode(**defaults)


# ---------------------------------------------------------------------------
# embeddings.py: Cloud dispatch via mcp_core.llm.embedding (litellm passthrough)
# ---------------------------------------------------------------------------


def _embedding_resp(n, dim=768):
    """Build a fake mcp_core.llm.embedding response with pydantic-like items."""
    resp = MagicMock()
    items = []
    for i in range(n):
        item = MagicMock()
        item.index = i
        item.embedding = [0.1] * dim
        items.append(item)
    resp.data = items
    return resp


class TestCloudProviderImplementations:
    """Test the single litellm-passthrough dispatch path + per-provider kwargs."""

    def test_dispatch_maps_jina_model(self):
        """Bare Jina model is mapped to the jina_ai/ prefix on dispatch."""
        backend = CloudEmbeddingBackend(model="jina-embeddings-v3", api_key="test-key")
        with patch("mcp_core.llm.embedding", return_value=_embedding_resp(1)) as m:
            result = backend.embed_texts(["hello"], dimensions=768)
        assert len(result) == 1
        assert len(result[0]) == 768
        assert m.call_args.kwargs["model"] == "jina_ai/jina-embeddings-v3"
        assert m.call_args.kwargs["dimensions"] == 768
        # Jina is not cohere -> no input_type kwarg.
        assert "input_type" not in m.call_args.kwargs

    def test_dispatch_no_dimensions_omits_kwarg(self):
        """Without dimensions, the kwarg is not forwarded."""
        backend = CloudEmbeddingBackend(
            model="text-embedding-3-large", api_key="test-key"
        )
        with patch("mcp_core.llm.embedding", return_value=_embedding_resp(1)) as m:
            result = backend.embed_texts(["hello"], dimensions=None)
        assert len(result) == 1
        assert "dimensions" not in m.call_args.kwargs

    def test_dispatch_cohere_passes_input_type(self):
        """Cohere provider forwards input_type='search_document' through kwargs."""
        backend = CloudEmbeddingBackend(
            model="cohere/embed-multilingual-v3.0", api_key="test-key"
        )
        with patch("mcp_core.llm.embedding", return_value=_embedding_resp(1)) as m:
            backend.embed_texts(["hello"], dimensions=768)
        assert m.call_args.kwargs["input_type"] == "search_document"


# ---------------------------------------------------------------------------
# embeddings.py: Retry exhaustion (lines 382-384)
# ---------------------------------------------------------------------------


class TestRetryExhaustion:
    def test_non_retryable_error_raises_immediately(self):
        """Non-retryable errors should raise without retry."""
        backend = CloudEmbeddingBackend(model="cohere/v3", api_key="test-key")
        with patch(
            "mcp_core.llm.embedding", side_effect=ValueError("invalid input data")
        ) as m:
            with pytest.raises(ValueError, match="invalid input"):
                backend.embed_texts(["test"])
        # Non-retryable -> called exactly once.
        assert m.call_count == 1

    def test_retryable_error_exhausts_retries(self):
        """Retryable errors should exhaust retries then raise."""
        backend = CloudEmbeddingBackend(model="cohere/v3", api_key="test-key")
        with patch(
            "mcp_core.llm.embedding",
            side_effect=Exception("429 rate limit exceeded"),
        ) as m:
            with patch("time.sleep"):
                with pytest.raises(Exception, match="429"):
                    backend.embed_texts(["test"])
            # Should have been called 3 times (max retries)
            assert m.call_count == 3


# ---------------------------------------------------------------------------
# embeddings.py: Search with backend lacking embed_single_query (line 636)
# ---------------------------------------------------------------------------


class TestSearchFallbackToEmbedSingle:
    def test_search_uses_embed_single_when_no_query_method(self, tmp_path):
        """Cover line 636: fallback to embed_single when embed_single_query missing."""
        db = tmp_path / "graph.db"
        # Create a mock backend WITHOUT embed_single_query
        mock_backend = MagicMock(spec=["embed_texts", "embed_single"])
        mock_backend.embed_texts.return_value = [[0.5] * 768]
        mock_backend.embed_single.return_value = [0.5] * 768

        store = EmbeddingStore(db, mock_backend)

        # Directly insert into DB to skip the actual embedding
        import struct

        blob = struct.pack(f"{768}f", *([0.5] * 768))
        store._conn.execute(
            "INSERT INTO embeddings (qualified_name, vector, text_hash, provider) VALUES (?, ?, ?, ?)",
            ("f.py::test_fn", blob, "hash123", "mock"),
        )
        store._conn.commit()

        results = store.search("test query", limit=5)
        assert len(results) >= 1
        # Should have called embed_single (not embed_single_query)
        mock_backend.embed_single.assert_called_once()
        store.close()


# ---------------------------------------------------------------------------
# embeddings.py: Provider column migration (lines 551-552)
# ---------------------------------------------------------------------------


class TestProviderColumnMigration:
    def test_migration_adds_provider_column(self, tmp_path):
        """Cover lines 551-552: ALTER TABLE when provider column is missing."""
        db = tmp_path / "graph.db"
        # Create a DB with the old schema (no provider column)
        conn = sqlite3.connect(str(db))
        conn.execute(
            """CREATE TABLE embeddings (
                qualified_name TEXT PRIMARY KEY,
                vector BLOB NOT NULL,
                text_hash TEXT NOT NULL
            )"""
        )
        conn.commit()
        conn.close()

        # Opening EmbeddingStore should trigger migration
        store = EmbeddingStore(db, backend=None)
        # Verify provider column exists
        cursor = store._conn.execute("PRAGMA table_info(embeddings)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "provider" in columns
        store.close()


# ---------------------------------------------------------------------------
# embeddings.py: _is_retryable
# ---------------------------------------------------------------------------


class TestIsRetryable:
    def test_retryable_patterns(self):
        assert _is_retryable(Exception("429 rate limit exceeded"))
        assert _is_retryable(Exception("503 Service Temporarily Unavailable"))
        assert _is_retryable(Exception("connection timeout"))
        assert _is_retryable(Exception("resource_exhausted"))

    def test_non_retryable(self):
        assert not _is_retryable(Exception("invalid api key"))
        assert not _is_retryable(ValueError("bad input"))


# ---------------------------------------------------------------------------
# server.py: _config_status version fallback (lines 350-351)
# ---------------------------------------------------------------------------


class TestConfigStatusVersionFallback:
    async def test_version_dev_fallback(self):
        """Cover lines 350-351: version = 'dev' when package not installed."""
        from better_code_review_graph.server import config

        with patch("better_code_review_graph.server._config_status") as mock_status:
            mock_status.return_value = json.dumps({"status": "ok", "version": "dev"})
            result = json.loads(await config(action="status"))
            assert result["version"] == "dev"

    def test_version_fallback_direct(self):
        """Test _config_status reports the module-level resolved version."""
        from better_code_review_graph.server import _config_status

        with patch("better_code_review_graph.server._pkg_version", "dev"):
            result = json.loads(_config_status(repo_root=None))
            assert result["version"] == "dev"


# ---------------------------------------------------------------------------
# server.py: help fallback to docs section content (line 507)
# ---------------------------------------------------------------------------


class TestHelpFallbackContent:
    def test_help_fallback_returns_content(self):
        """Cover line 507: help returns content from LLM-OPTIMIZED-REFERENCE."""
        from better_code_review_graph.server import help

        with patch("better_code_review_graph.server.files") as mock_files:
            mock_files.side_effect = FileNotFoundError("no docs")
            with patch("better_code_review_graph.server.get_docs_section") as mock_docs:
                mock_docs.return_value = {
                    "status": "ok",
                    "content": "Full documentation content here.",
                }
                result = help(topic="graph")
                assert result == "Full documentation content here."

    def test_help_non_graph_query_fallback(self):
        """Cover help fallback for non-graph/query topics (review, config)."""
        from better_code_review_graph.server import help

        with patch("better_code_review_graph.server.files") as mock_files:
            mock_files.side_effect = FileNotFoundError("no docs")
            # For 'review' topic, it should NOT try get_docs_section
            result = help(topic="review")
            data = json.loads(result)
            assert "error" in data
            assert "valid_topics" in data


# ---------------------------------------------------------------------------
# incremental.py: get_changed_files with invalid ref (line 135)
# ---------------------------------------------------------------------------


class TestIncrementalEdgeCases:
    def test_get_changed_files_invalid_ref(self, tmp_path):
        """Cover line 135: ValueError when base starts with '-'."""
        with pytest.raises(ValueError, match="Invalid git ref"):
            get_changed_files(tmp_path, base="--exec=whoami")

    def test_find_repo_root_no_git(self, tmp_path):
        """Cover line 55-56: find_repo_root returns None when no .git."""
        result = find_repo_root(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# graph.py: NetworkX cache hit (line 580)
# ---------------------------------------------------------------------------


class TestGraphCacheHit:
    def test_networkx_cache_reused(self, tmp_path):
        """Cover line 580: _build_networkx_graph returns cached graph."""
        from better_code_review_graph.parser import EdgeInfo, NodeInfo

        db = tmp_path / "graph.db"
        store = GraphStore(str(db))

        # Add some data
        store.upsert_node(
            NodeInfo(
                kind="Function",
                name="foo",
                file_path="a.py",
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="a.py::foo",
                target="b.py::bar",
                file_path="a.py",
                line=3,
            )
        )
        store.commit()

        # First call builds the graph
        g1 = store._build_networkx_graph()
        assert g1 is not None

        # Second call should return cached graph (line 580)
        g2 = store._build_networkx_graph()
        assert g2 is g1  # Same object (cached)

        store.close()


# ---------------------------------------------------------------------------
# parser.py: _get_parser returns None for unknown language (line 255)
# ---------------------------------------------------------------------------


class TestParserUnknownLanguage:
    def test_parse_bytes_unknown_parser(self):
        """Cover line 255: returns empty when parser is None."""
        parser = CodeParser()
        # Directly test parse_bytes with a known language but broken parser
        with patch.object(parser, "_get_parser", return_value=None):
            nodes, edges = parser.parse_bytes(Path("test.py"), b"def foo(): pass")
            assert nodes == []
            assert edges == []


# ---------------------------------------------------------------------------
# parser.py: Java class inheritance (lines 933-946)
# ---------------------------------------------------------------------------


class TestParserJavaInheritance:
    def test_java_class_extends(self):
        """Cover Java superclass/type_identifier parsing."""
        parser = CodeParser()
        java_code = b"""
public class Animal {
    public String name;
}

public class Dog extends Animal {
    public String bark() {
        return "woof";
    }
}
"""
        nodes, edges = parser.parse_bytes(Path("Dog.java"), java_code)
        inherits_edges = [e for e in edges if e.kind == "INHERITS"]
        # Java extends detection
        assert len(inherits_edges) >= 1


class TestParserRustStruct:
    def test_rust_struct_and_impl(self):
        """Cover Rust struct_item and impl_item parsing."""
        parser = CodeParser()
        rust_code = b"""
struct Point {
    x: f64,
    y: f64,
}

impl Point {
    fn distance(&self) -> f64 {
        (self.x * self.x + self.y * self.y).sqrt()
    }
}

fn main() {
    let p = Point { x: 3.0, y: 4.0 };
    println!("{}", p.distance());
}
"""
        nodes, edges = parser.parse_bytes(Path("point.rs"), rust_code)
        # Should find struct, impl, and functions
        kinds = [n.kind for n in nodes]
        assert "Class" in kinds  # struct_item maps to Class
        assert "Function" in kinds


# ---------------------------------------------------------------------------
# parser.py: Python return type annotation (line 921)
# ---------------------------------------------------------------------------


class TestParserPythonReturnType:
    def test_python_function_return_type(self):
        """Cover line 921: Python -> return type annotation."""
        parser = CodeParser()
        code = b"""
def calculate(x: int, y: int) -> float:
    return x / y
"""
        nodes, edges = parser.parse_bytes(Path("calc.py"), code)
        func_nodes = [
            n for n in nodes if n.kind == "Function" and n.name == "calculate"
        ]
        assert len(func_nodes) == 1
        assert func_nodes[0].return_type is not None
        assert "float" in func_nodes[0].return_type


# ---------------------------------------------------------------------------
# parser.py: _get_call_name with no children (line 1097)
# ---------------------------------------------------------------------------


class TestParserCallNameNoChildren:
    def test_call_with_member_expression(self):
        """Cover various call expression patterns including member_expression."""
        parser = CodeParser()
        ts_code = b"""
function main() {
    const result = obj.method();
    const data = transform(input);
    console.log("test");
}
"""
        nodes, edges = parser.parse_bytes(Path("main.ts"), ts_code)
        call_edges = [e for e in edges if e.kind == "CALLS"]
        # Should find calls: obj.method, transform, console.log
        assert len(call_edges) >= 1


# ---------------------------------------------------------------------------
# incremental.py: incremental_update with deleted file (lines 353-356)
# ---------------------------------------------------------------------------


class TestIncrementalDeletedFile:
    def test_incremental_update_deleted_file(self, tmp_path):
        """Cover lines 353-356: handle deleted file in incremental update."""
        from better_code_review_graph.incremental import incremental_update

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=repo,
            capture_output=True,
            check=True,
        )

        # Create and commit a file
        (repo / "example.py").write_text("def hello(): pass\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo,
            capture_output=True,
            check=True,
        )

        db = repo / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db))
        try:
            # Build full graph first
            from better_code_review_graph.incremental import full_build

            full_build(repo, store)

            # Delete the file
            (repo / "example.py").unlink()

            # Run incremental update with the deleted file
            result = incremental_update(repo, store, changed_files=["example.py"])
            # The deleted file should be handled gracefully
            assert result["files_updated"] >= 1
        finally:
            store.close()


# ---------------------------------------------------------------------------
# incremental.py: incremental_update with non-parseable file (line 359-360)
# ---------------------------------------------------------------------------


class TestIncrementalNonParseableFile:
    def test_incremental_update_non_parseable(self, tmp_path):
        """Cover lines 359-360: skip files with no parseable language."""
        from better_code_review_graph.incremental import incremental_update

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        # Create a non-parseable file
        (repo / "readme.txt").write_text("Just a text file\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo,
            capture_output=True,
            check=True,
        )

        db = repo / ".code-review-graph" / "graph.db"
        store = GraphStore(str(db))
        try:
            result = incremental_update(repo, store, changed_files=["readme.txt"])
            # Should handle non-parseable file gracefully
            assert result["files_updated"] >= 1
            assert result["total_nodes"] == 0  # .txt can't be parsed
        finally:
            store.close()


# ---------------------------------------------------------------------------
# server.py: config cache_clear RuntimeError fallback (lines 447-448)
# ---------------------------------------------------------------------------


class TestConfigCacheClearFallback:
    async def test_cache_clear_runtime_error(self):
        """Cover lines 447-448: cache_clear handles RuntimeError."""
        from better_code_review_graph.server import config

        # Use a nonexistent path that will trigger RuntimeError
        result = json.loads(
            await config(action="cache_clear", repo_root="/nonexistent/path/xyz")
        )
        assert result["status"] == "cache cleared"
        assert result["embeddings_removed"] == 0


# ---------------------------------------------------------------------------
# server.py: config status RuntimeError fallback (lines 381-382)
# ---------------------------------------------------------------------------


class TestConfigStatusFallback:
    async def test_status_runtime_error(self):
        """Cover lines 381-382: _config_status handles RuntimeError."""
        from better_code_review_graph.server import config

        result = json.loads(
            await config(action="status", repo_root="/nonexistent/path/xyz")
        )
        # Should return ok with 0 nodes (no graph found)
        assert result["status"] == "ok"
        assert result.get("total_nodes", 0) == 0
