"""TESTED_BY edges are derived from calls made inside test functions.

These run in the default suite on purpose. The pre-existing coverage for
``tests_for`` either seeded ``TESTED_BY`` rows by hand before querying them
(so it only exercised the read path) or lived behind the ``full`` marker,
which ``addopts`` deselects -- neither could notice that the parser emitted
no ``TESTED_BY`` edge at all.
"""

from pathlib import Path

from better_code_review_graph.graph import GraphStore
from better_code_review_graph.incremental import full_build, get_db_path
from better_code_review_graph.parser import CodeParser
from better_code_review_graph.tools import (
    _compute_untested_functions,
    query_graph,
)

SUBJECT = """\
def add(a: int, b: int) -> int:
    return a + b


def calculate(op: str, a: int, b: int) -> int:
    if op == "add":
        return add(a, b)
    return a * b
"""

# test_dispatch_path is deliberately NOT named after the function it covers --
# that is the case the naming-convention fallback in _handle_tests_for misses.
TESTS = """\
from calculator import add, calculate


def test_add():
    assert add(1, 2) == 3


def test_dispatch_path():
    assert calculate("add", 1, 2) == 3
"""


# A test calls more than its subject. These two fixtures pin down which of
# those calls become TESTED_BY -- see TestTestedByScope.
SUPPORT = """\
def build_fixture():
    return {"a": 1, "b": 2}
"""

MIXED_TEST = """\
from calculator import add
from support import build_fixture


def _local_helper(v):
    return v


def test_add_with_helpers():
    data = build_fixture()
    assert add(_local_helper(data["a"]), data["b"]) == 3
"""


def _write_repo(root: Path) -> None:
    (root / "calculator.py").write_text(SUBJECT)
    (root / "test_calculator.py").write_text(TESTS)
    (root / ".git").mkdir(exist_ok=True)


def _write_mixed_repo(root: Path) -> None:
    (root / "calculator.py").write_text(SUBJECT)
    (root / "support.py").write_text(SUPPORT)
    (root / "test_mixed.py").write_text(MIXED_TEST)
    (root / ".git").mkdir(exist_ok=True)


class TestParserEmitsTestedBy:
    def test_call_from_test_function_emits_tested_by(self, tmp_path):
        _write_repo(tmp_path)
        parser = CodeParser()

        _nodes, edges = parser.parse_file(tmp_path / "test_calculator.py")

        tested_by = [e for e in edges if e.kind == "TESTED_BY"]
        assert tested_by, (
            f"no TESTED_BY edge emitted, kinds={ {e.kind for e in edges} }"
        )
        # Source is the test, target is the function under test -- the direction
        # _handle_tests_for and _compute_untested_functions both read.
        assert all("test_" in Path(e.source).name for e in tested_by)
        assert any(e.target.endswith("::calculate") for e in tested_by)

    def test_call_outside_a_test_function_emits_no_tested_by(self, tmp_path):
        _write_repo(tmp_path)
        parser = CodeParser()

        _nodes, edges = parser.parse_file(tmp_path / "calculator.py")

        # calculate() calls add(), but neither is a test.
        assert any(e.kind == "CALLS" for e in edges)
        assert not [e for e in edges if e.kind == "TESTED_BY"]


class TestTestedByScope:
    """Pins the declared meaning of the edge: called directly by a test.

    Not "properly tested" -- a test also calls helpers, and no static rule
    separates intent from incidental use. One exclusion is applied (helpers
    defined in a test file); the rest is accepted and documented. A later
    change that widens or narrows this should have to edit these assertions.
    """

    def test_subject_called_by_test_gets_an_edge(self, tmp_path):
        _write_mixed_repo(tmp_path)

        _nodes, edges = CodeParser().parse_file(tmp_path / "test_mixed.py")

        targets = {e.target for e in edges if e.kind == "TESTED_BY"}
        assert any(t.endswith("::add") for t in targets)

    def test_helper_defined_in_the_test_file_is_excluded(self, tmp_path):
        _write_mixed_repo(tmp_path)

        _nodes, edges = CodeParser().parse_file(tmp_path / "test_mixed.py")

        targets = {e.target for e in edges if e.kind == "TESTED_BY"}
        assert not any(t.endswith("::_local_helper") for t in targets), (
            "a function defined in a test file is scaffolding, not a subject"
        )

    def test_helper_in_a_non_test_module_still_gets_an_edge(self, tmp_path):
        """Accepted false positive, asserted so it stays a decision.

        build_fixture() is test support, but it lives in support.py and
        nothing in the syntax says so. Consumers are told the edge means
        "called by a test" precisely because of cases like this.
        """
        _write_mixed_repo(tmp_path)

        _nodes, edges = CodeParser().parse_file(tmp_path / "test_mixed.py")

        targets = {e.target for e in edges if e.kind == "TESTED_BY"}
        assert any(t.endswith("::build_fixture") for t in targets)

    def test_call_nested_inside_a_helper_is_not_attributed_to_the_test(self, tmp_path):
        """Only the test's own call sites count.

        A call written inside a helper has that helper as its enclosing
        function, so it never reaches the TESTED_BY branch -- indirect reach
        is not silently credited to the test.
        """
        (tmp_path / "calculator.py").write_text(SUBJECT)
        (tmp_path / "test_indirect.py").write_text(
            "from calculator import add\n\n\n"
            "def _run(a, b):\n"
            "    return add(a, b)\n\n\n"
            "def test_indirect():\n"
            "    assert _run(1, 2) == 3\n"
        )
        (tmp_path / ".git").mkdir(exist_ok=True)

        _nodes, edges = CodeParser().parse_file(tmp_path / "test_indirect.py")

        targets = {e.target for e in edges if e.kind == "TESTED_BY"}
        assert not any(t.endswith("::add") for t in targets)


class TestTestsForFindsUnconventionallyNamedTests:
    def test_tests_for_resolves_test_named_after_behaviour(self, tmp_path):
        _write_repo(tmp_path)
        # query_graph reopens the store via get_db_path, so build into the
        # location it will read from rather than an arbitrary path.
        store = GraphStore(get_db_path(tmp_path))
        full_build(tmp_path, store)
        store.close()

        result = query_graph(
            "tests_for",
            str(tmp_path / "calculator.py") + "::calculate",
            repo_root=str(tmp_path),
        )

        names = [r.get("name") for r in result.get("results", [])]
        # Asserting on test_add instead would pass even without TESTED_BY,
        # because "test_" + "add" matches the naming fallback.
        assert "test_dispatch_path" in names, (
            f"expected the behaviour-named test for calculate(), got {names}"
        )

    def test_covered_function_is_not_reported_untested(self, tmp_path):
        _write_repo(tmp_path)
        store = GraphStore(tmp_path / "graph.db")
        full_build(tmp_path, store)

        impact = store.get_impact_radius([str(tmp_path / "calculator.py")])
        untested = _compute_untested_functions(impact)
        store.close()

        names = {u.get("name") for u in untested}
        assert "add" not in names, "add() is covered by test_add"
        assert "calculate" not in names, "calculate() is covered by test_dispatch_path"
