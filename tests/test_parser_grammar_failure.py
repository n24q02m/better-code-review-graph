"""A broken tree-sitter grammar must fail loudly, not parse zero nodes.

``CodeParser._get_parser`` used to catch every exception from
``tree_sitter_language_pack.get_parser`` and return ``None``, which
``parse_bytes`` turned into an empty ``([], [])``. A host that cannot
resolve its grammar cache therefore produced a *successful-looking* build
containing no nodes at all -- the exact failure that took a full CI run
plus a hand-built experiment to diagnose.

These tests pin both halves of the split this file's fix introduces:
infrastructure breakage raises, unsupported languages stay quiet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from better_code_review_graph.parser import (
    CodeParser,
    GrammarUnavailableError,
)

#: The verbatim error tree_sitter_language_pack raises on a host whose
#: grammar cache directory cannot be resolved -- e.g. under a redirected
#: HOME on a network-restricted Linux runner.
_CACHE_ERROR = "Download error: Could not determine system cache directory"


@pytest.fixture
def broken_grammar(monkeypatch):
    """Make every ``tslp.get_parser`` call fail the way a cache-less host does."""

    def _boom(name):
        raise RuntimeError(_CACHE_ERROR)

    monkeypatch.setattr(
        "better_code_review_graph.parser.tslp.get_parser",
        _boom,
    )


class TestGrammarFailureIsLoud:
    """Infrastructure breakage must reach the caller."""

    def test_parse_bytes_raises_instead_of_returning_empty(self, broken_grammar):
        """The regression itself: silent ``([], [])`` becomes a raised error."""
        parser = CodeParser()
        with pytest.raises(GrammarUnavailableError):
            parser.parse_bytes(Path("sample.py"), b"def outer():\n    return 1\n")

    def test_error_names_the_language_the_original_cause_and_a_remedy(
        self, broken_grammar
    ):
        """A bare raise is not enough -- the message has to be actionable."""
        parser = CodeParser()
        with pytest.raises(GrammarUnavailableError) as excinfo:
            parser.parse_bytes(Path("sample.py"), b"x = 1\n")

        message = str(excinfo.value)
        assert "python" in message, "the failing language must be named"
        assert _CACHE_ERROR in message, "the underlying cause must be quoted"
        assert "cache" in message.lower(), "the message must point at a remedy"
        # The original exception stays attached for tracebacks / logging.
        assert isinstance(excinfo.value.__cause__, RuntimeError)

    def test_parse_file_propagates_too(self, broken_grammar, tmp_path):
        """``parse_file`` only absorbs read errors, never grammar errors."""
        source_file = tmp_path / "sample.py"
        source_file.write_text("def outer():\n    return 1\n")

        parser = CodeParser()
        with pytest.raises(GrammarUnavailableError):
            parser.parse_file(source_file)

    def test_every_supported_language_is_covered(self, broken_grammar):
        """The guard applies to the whole supported set, not just Python."""
        parser = CodeParser()
        for suffix in (".py", ".ts", ".go", ".rs", ".java", ".sol"):
            with pytest.raises(GrammarUnavailableError):
                parser.parse_bytes(Path(f"sample{suffix}"), b"x")

    def test_full_build_reports_the_failure_instead_of_an_empty_graph(
        self, broken_grammar, tmp_path
    ):
        """The build path must surface the cause, not report a clean zero.

        ``incremental.full_build`` already records per-file failures into a
        returned ``errors`` list; swallowing inside ``_get_parser`` meant that
        channel stayed empty while the graph came out empty too.
        """
        from better_code_review_graph.graph import GraphStore
        from better_code_review_graph.incremental import full_build

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "mod.py").write_text("def outer():\n    return 1\n")

        store = GraphStore(str(tmp_path / "graph.db"))
        try:
            result = full_build(repo, store)
        finally:
            store.close()

        assert result["total_nodes"] == 0
        assert result["errors"], "a zero-node build must not report zero errors"
        assert any(_CACHE_ERROR in e["error"] for e in result["errors"])


class TestUnsupportedLanguageStaysQuiet:
    """Valid 'nothing to do here' cases must not become crashes."""

    def test_unknown_extension_returns_empty_without_touching_the_grammar(
        self, broken_grammar
    ):
        """A ``.txt`` file is not an error -- and never loads a grammar.

        The booby-trapped ``get_parser`` stays armed here on purpose: reaching
        it at all would raise, so passing proves the unsupported-extension path
        short-circuits before any grammar work.
        """
        parser = CodeParser()
        nodes, edges = parser.parse_bytes(Path("notes.txt"), b"just prose\n")
        assert (nodes, edges) == ([], [])

    def test_unsupported_extension_on_disk_returns_empty(
        self, broken_grammar, tmp_path
    ):
        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b,c\n")

        parser = CodeParser()
        assert CodeParser().parse_file(data_file) == ([], [])
        assert parser.detect_language(data_file) is None

    def test_get_parser_returns_none_for_a_language_crg_does_not_map(self):
        """``_get_parser`` keeps its quiet ``None`` for out-of-set languages.

        This is the branch that must NOT raise: it means "crg does not handle
        this language", which is a fact about the extension map, not a broken
        host.
        """
        parser = CodeParser()
        assert parser._get_parser("brainfuck") is None

    def test_out_of_set_language_stays_quiet_even_when_grammars_are_broken(
        self, broken_grammar
    ):
        """Classification is by supported-set membership, not by luck."""
        parser = CodeParser()
        assert parser._get_parser("brainfuck") is None


class TestHealthyHostIsUnaffected:
    """The fix must not disturb a working install."""

    def test_real_python_parse_still_extracts_nodes(self):
        parser = CodeParser()
        nodes, _edges = parser.parse_bytes(
            Path("sample.py"), b"def outer():\n    return 1\n"
        )
        assert [n for n in nodes if n.kind == "Function"]
