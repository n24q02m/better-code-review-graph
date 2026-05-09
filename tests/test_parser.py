"""Tests for the Tree-sitter parser module."""

from pathlib import Path

from better_code_review_graph.parser import CodeParser

FIXTURES = Path(__file__).parent / "fixtures"


class TestCodeParser:
    def setup_method(self):
        self.parser = CodeParser()

    def test_detect_language_python(self):
        assert self.parser.detect_language(Path("foo.py")) == "python"

    def test_detect_language_typescript(self):
        assert self.parser.detect_language(Path("foo.ts")) == "typescript"

    def test_detect_language_unknown(self):
        assert self.parser.detect_language(Path("foo.txt")) is None

    def test_parse_python_file(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_python.py")

        # Should have File node
        file_nodes = [n for n in nodes if n.kind == "File"]
        assert len(file_nodes) == 1

        # Should find classes
        classes = [n for n in nodes if n.kind == "Class"]
        class_names = {c.name for c in classes}
        assert "BaseService" in class_names
        assert "AuthService" in class_names

        # Should find functions
        funcs = [n for n in nodes if n.kind == "Function"]
        func_names = {f.name for f in funcs}
        assert "__init__" in func_names
        assert "authenticate" in func_names
        assert "create_auth_service" in func_names
        assert "process_request" in func_names

    def test_parse_python_edges(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_python.py")

        edge_kinds = {e.kind for e in edges}
        assert "CONTAINS" in edge_kinds
        assert "IMPORTS_FROM" in edge_kinds
        assert "CALLS" in edge_kinds

        # Should detect inheritance
        inherits = [e for e in edges if e.kind == "INHERITS"]
        assert len(inherits) >= 1
        assert any(
            "AuthService" in e.source and "BaseService" in e.target for e in inherits
        )

    def test_parse_python_imports(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_python.py")
        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        import_targets = {e.target for e in imports}
        assert "os" in import_targets
        assert "pathlib" in import_targets

    def test_parse_python_calls(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_python.py")
        calls = [e for e in edges if e.kind == "CALLS"]
        call_targets = {e.target for e in calls}
        assert "_validate_token" in call_targets
        assert "authenticate" in call_targets

    def test_parse_typescript_file(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_typescript.ts")

        classes = [n for n in nodes if n.kind == "Class"]
        class_names = {c.name for c in classes}
        assert "UserRepository" in class_names
        assert "UserService" in class_names

        funcs = [n for n in nodes if n.kind == "Function"]
        func_names = {f.name for f in funcs}
        assert "findById" in func_names or "handleGetUser" in func_names

    def test_parse_test_file(self):
        nodes, edges = self.parser.parse_file(FIXTURES / "test_sample.py")

        # Test functions should be detected
        tests = [n for n in nodes if n.kind == "Test"]
        test_names = {t.name for t in tests}
        assert "test_authenticate_valid" in test_names
        assert "test_process_request_ok" in test_names

    def test_calls_edge_same_file_resolution(self):
        """Call targets defined in the same file should be qualified."""
        nodes, edges = self.parser.parse_file(FIXTURES / "sample_python.py")
        calls = [e for e in edges if e.kind == "CALLS"]
        file_path = str(FIXTURES / "sample_python.py")

        # create_auth_service() calls AuthService() — a class defined in the same file
        auth_service_calls = [
            e for e in calls if e.target == f"{file_path}::AuthService"
        ]
        assert len(auth_service_calls) >= 1

    def test_calls_edge_cross_file_resolution(self):
        """Call targets imported from another file should resolve to that file's qualified name."""
        _, edges = self.parser.parse_file(FIXTURES / "caller_example.py")
        calls = [e for e in edges if e.kind == "CALLS"]

        sample_path = str((FIXTURES / "sample_python.py").resolve())
        # setup_and_run() calls create_auth_service(), imported from sample_python
        resolved_calls = [
            e for e in calls if e.target == f"{sample_path}::create_auth_service"
        ]
        assert len(resolved_calls) == 1

    def test_unresolved_calls_stay_bare(self):
        """Method calls and unknown calls should remain as bare names."""
        _, edges = self.parser.parse_file(FIXTURES / "sample_python.py")
        calls = [e for e in edges if e.kind == "CALLS"]
        # self._validate_token() is a method call — can't resolve the target file
        bare_calls = [e for e in calls if e.target == "_validate_token"]
        assert len(bare_calls) >= 1

    def test_calls_edge_decorated_function_resolution(self):
        """Decorated functions should be in defined_names and resolvable as call targets."""
        _, edges = self.parser.parse_file(FIXTURES / "sample_python.py")
        calls = [e for e in edges if e.kind == "CALLS"]
        file_path = str(FIXTURES / "sample_python.py")

        # guarded_process() calls process_request() — both in the same file,
        # but guarded_process is wrapped in a decorated_definition node
        resolved = [
            e
            for e in calls
            if e.target == f"{file_path}::process_request"
            and "guarded_process" in e.source
        ]
        assert len(resolved) == 1

    def test_multiple_calls_to_same_function(self):
        """Multiple calls to the same function on different lines should each produce an edge."""
        _, edges = self.parser.parse_file(FIXTURES / "multi_call_example.py")
        calls = [
            e for e in edges if e.kind == "CALLS" and "_internal_request" in e.target
        ]
        assert len(calls) == 2
        lines = {e.line for e in calls}
        assert len(lines) == 2  # distinct line numbers

    def test_parse_nonexistent_file(self):
        nodes, edges = self.parser.parse_file(Path("/nonexistent/file.py"))
        assert nodes == []
        assert edges == []

    def test_parse_unsupported_extension(self):
        nodes, edges = self.parser.parse_file(Path("readme.txt"))
        assert nodes == []
        assert edges == []


# --- Bare call target resolution tests (Task 2.2) ---


def test_calls_edge_target_qualified_go(tmp_path):
    """Go call targets should be resolved to qualified names when defined in same file."""
    parser = CodeParser()
    go_file = tmp_path / "main.go"
    go_file.write_text(
        """
package main

func FirebaseAuth() {}

func setupRoutes() {
    FirebaseAuth()
}
"""
    )
    nodes, edges = parser.parse_file(go_file)
    call_edges = [e for e in edges if e.kind == "CALLS"]
    assert len(call_edges) >= 1

    firebase_call = next(e for e in call_edges if "FirebaseAuth" in e.target)
    # Target should be qualified (contains ::), not bare
    assert "::" in firebase_call.target, (
        f"Expected qualified target, got bare name: {firebase_call.target}"
    )


def test_calls_edge_target_qualified_python(tmp_path):
    """Python call targets should be resolved to qualified names when defined in same file."""
    parser = CodeParser()
    py_file = tmp_path / "auth.py"
    py_file.write_text(
        """
def verify_token(token):
    pass

def login(request):
    verify_token(request.token)
"""
    )
    nodes, edges = parser.parse_file(py_file)
    call_edges = [e for e in edges if e.kind == "CALLS"]
    verify_call = next((e for e in call_edges if "verify_token" in e.target), None)
    assert verify_call is not None
    assert "::" in verify_call.target


def test_calls_edge_external_stays_bare(tmp_path):
    """External library calls (not defined in file) should remain bare."""
    parser = CodeParser()
    py_file = tmp_path / "app.py"
    py_file.write_text(
        """
import json

def handler():
    json.loads("{}")
"""
    )
    nodes, edges = parser.parse_file(py_file)
    call_edges = [e for e in edges if e.kind == "CALLS"]
    loads_call = next((e for e in call_edges if "loads" in e.target), None)
    assert loads_call is not None
    # External call -- stays bare (no local definition)
    assert "::" not in loads_call.target


# ---------------------------------------------------------------------------
# Phase 2 Task 9: parser + federation wiring
# ---------------------------------------------------------------------------


def test_parse_file_without_repo_registry_keeps_repo_id_empty(tmp_path):
    """Backwards-compat: no repo_registry -> all nodes get repo_id == ''."""
    parser = CodeParser()
    py_file = tmp_path / "mod.py"
    py_file.write_text("def foo():\n    return 1\n")

    nodes, edges = parser.parse_file(py_file)

    # Every node defaults to empty repo_id when no registry is wired in.
    assert nodes, "expected at least the File node"
    for node in nodes:
        assert node.repo_id == "", (
            f"expected empty repo_id for {node.kind}/{node.name}, got {node.repo_id!r}"
        )
    for edge in edges:
        assert edge.repo_id == "", (
            f"expected empty repo_id for edge {edge.kind} {edge.source}->{edge.target}"
        )


def test_parse_file_with_repo_registry_populates_node_repo_id(tmp_path):
    """When repo_registry is provided, every node's repo_id == registry.assign(path)."""
    from better_code_review_graph.federation import RepoRegistry
    from better_code_review_graph.graph import GraphStore

    repo = tmp_path / "myrepo"
    repo.mkdir()
    py_file = repo / "mod.py"
    py_file.write_text("def hello():\n    return 'hi'\n")

    db = tmp_path / "graph.db"
    store = GraphStore(db)
    try:
        registry = RepoRegistry(store)
        rid = registry.add(repo)

        parser = CodeParser()
        nodes, edges = parser.parse_file(py_file, repo_registry=registry)

        assert nodes
        for node in nodes:
            assert node.repo_id == rid, (
                f"expected repo_id={rid!r} for {node.kind}/{node.name}, "
                f"got {node.repo_id!r}"
            )
        # IMPORTS_FROM edges (none here) plus CONTAINS edges should also
        # carry the source repo's id.
        for edge in edges:
            assert edge.repo_id == rid
    finally:
        store.close()


def test_parse_file_cross_repo_resolution_via_dispatcher(tmp_path):
    """2-repo Python fixture: imports get cross-repo resolved when declared as dep.

    repo_a exposes ``lib_a/utils.py`` with ``retry()``. repo_b's
    ``pyproject.toml`` declares ``lib_a`` as a dependency and ``main.py``
    imports ``from lib_a.utils import retry``. The parser, given
    ``target_repos=[repo_a]``, should rewrite the IMPORTS_FROM edge
    target to ``<repo_a_id>:lib_a/utils.py::retry`` (or ``::utils`` —
    we accept either since the resolver may normalise to the module's
    own basename when the imported symbol name is not threaded through).
    """
    from better_code_review_graph.federation import RepoRegistry
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.resolver import TargetRepo

    # --- repo_a (target) ---
    repo_a = tmp_path / "repo_a"
    (repo_a / "lib_a").mkdir(parents=True)
    (repo_a / "lib_a" / "__init__.py").write_text("")
    (repo_a / "lib_a" / "utils.py").write_text("def retry():\n    pass\n")
    (repo_a / "pyproject.toml").write_text(
        '[project]\nname = "lib_a"\nversion = "0.1.0"\n'
    )

    # --- repo_b (source) ---
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    (repo_b / "pyproject.toml").write_text(
        '[project]\nname = "repo_b"\nversion = "0.1.0"\ndependencies = ["lib_a"]\n'
    )
    main_py = repo_b / "main.py"
    main_py.write_text("from lib_a.utils import retry\n\ndef go():\n    retry()\n")

    db = tmp_path / "graph.db"
    store = GraphStore(db)
    try:
        registry = RepoRegistry(store)
        rid_a = registry.add(repo_a)
        rid_b = registry.add(repo_b)

        target_repos = [
            TargetRepo(repo_id=rid_a, root=repo_a),
            TargetRepo(repo_id=rid_b, root=repo_b),
        ]

        parser = CodeParser()
        nodes, edges = parser.parse_file(
            main_py,
            repo_registry=registry,
            target_repos=target_repos,
        )

        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        assert imports, "expected at least one IMPORTS_FROM edge"
        cross = [e for e in imports if e.target.startswith(f"{rid_a}:")]
        assert len(cross) == 1, (
            f"expected the lib_a import to be resolved cross-repo, "
            f"got targets={[e.target for e in imports]}"
        )
        cross_edge = cross[0]
        # Format: <repo_id>:<file_path>::<symbol>
        assert "lib_a/utils.py" in cross_edge.target.replace("\\", "/")
        assert "::" in cross_edge.target
        # Edge originates in source repo, so its repo_id == source repo id.
        assert cross_edge.repo_id == rid_b
    finally:
        store.close()


def test_parse_file_cross_repo_unresolved_stays_within_repo(tmp_path):
    """Imports that don't resolve to any target repo keep their bare target.

    Stdlib imports (``import os``) aren't declared as deps in
    pyproject.toml so the resolver returns ``None`` and the edge keeps
    its single-repo bare target.
    """
    from better_code_review_graph.federation import RepoRegistry
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.resolver import TargetRepo

    repo = tmp_path / "solo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "solo"\nversion = "0.1.0"\n'
    )
    py_file = repo / "app.py"
    py_file.write_text("import os\n\ndef foo():\n    os.getcwd()\n")

    db = tmp_path / "graph.db"
    store = GraphStore(db)
    try:
        registry = RepoRegistry(store)
        rid = registry.add(repo)

        parser = CodeParser()
        nodes, edges = parser.parse_file(
            py_file,
            repo_registry=registry,
            target_repos=[TargetRepo(repo_id=rid, root=repo)],
        )

        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        assert imports
        for edge in imports:
            # Stays bare — not resolved cross-repo.
            assert ":" not in edge.target.split("/")[-1] or edge.target == "os"
            assert edge.target == "os"
            assert edge.repo_id == rid
    finally:
        store.close()


def test_build_resolver_stmt_per_language():
    """Cover every language branch of ``_build_resolver_stmt``."""
    fn = CodeParser._build_resolver_stmt

    assert fn("python", "lib_a.utils") == "import lib_a.utils"
    assert fn("javascript", "./foo") == 'import "./foo"'
    assert fn("typescript", "./bar") == 'import "./bar"'
    assert fn("tsx", "./baz") == 'import "./baz"'
    assert fn("go", "github.com/x/y") == 'import "github.com/x/y"'
    # Rust: bare path -> wrapped; already wrapped -> passed through.
    assert fn("rust", "foo::bar::Baz") == "use foo::bar::Baz;"
    assert fn("rust", "use foo::bar;") == "use foo::bar;"
    # Java + Kotlin both use ``import ...;``.
    assert fn("java", "com.example.Util") == "import com.example.Util;"
    assert fn("kotlin", "com.example.Helper") == "import com.example.Helper;"
    # Tier-2 fallback: any other language returns target verbatim.
    assert fn("ruby", "foo/bar") == "foo/bar"


def test_apply_federation_skips_when_path_outside_registry(tmp_path):
    """File outside any registered repo: repo_id stays empty (no exception)."""
    from better_code_review_graph.federation import RepoRegistry
    from better_code_review_graph.graph import GraphStore

    # Register a repo at one location; parse a file under a sibling
    # directory so registry.assign() raises ValueError, which the
    # parser swallows and leaves repo_id empty.
    registered = tmp_path / "registered"
    registered.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    py_file = elsewhere / "stray.py"
    py_file.write_text("def foo():\n    pass\n")

    db = tmp_path / "graph.db"
    store = GraphStore(db)
    try:
        registry = RepoRegistry(store)
        registry.add(registered)

        parser = CodeParser()
        nodes, edges = parser.parse_file(py_file, repo_registry=registry)

        # No assignment available -> repo_id stays at the dataclass default.
        for node in nodes:
            assert node.repo_id == ""
    finally:
        store.close()


def test_apply_federation_resolver_exception_swallowed(tmp_path, monkeypatch):
    """When the resolver raises, we leave the edge unchanged (single-repo)."""
    from better_code_review_graph.federation import RepoRegistry
    from better_code_review_graph.graph import GraphStore
    from better_code_review_graph.resolver import TargetRepo

    repo = tmp_path / "src_repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "src_repo"\nversion = "0.1.0"\ndependencies = ["lib_a"]\n'
    )
    py_file = repo / "main.py"
    py_file.write_text("import lib_a\n")

    other = tmp_path / "other"
    other.mkdir()

    db = tmp_path / "graph.db"
    store = GraphStore(db)
    try:
        registry = RepoRegistry(store)
        rid = registry.add(repo)
        rid_other = registry.add(other)

        # Force the resolver lookup (lazy import inside _apply_federation)
        # to raise so the except branch runs.
        def boom(*_args, **_kwargs):
            raise RuntimeError("synthetic resolver failure")

        monkeypatch.setattr(
            "better_code_review_graph.resolver.resolve_cross_repo_imports",
            boom,
        )

        parser = CodeParser()
        nodes, edges = parser.parse_file(
            py_file,
            repo_registry=registry,
            target_repos=[TargetRepo(repo_id=rid_other, root=other)],
        )

        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        assert imports
        # Edge target unchanged because resolver raised.
        assert imports[0].target == "lib_a"
        assert imports[0].repo_id == rid
    finally:
        store.close()


def test_apply_federation_target_repos_empty_skips_resolution(tmp_path):
    """target_repos=[] short-circuits cross-repo resolution path."""
    from better_code_review_graph.federation import RepoRegistry
    from better_code_review_graph.graph import GraphStore

    repo = tmp_path / "solo"
    repo.mkdir()
    py_file = repo / "x.py"
    py_file.write_text("import os\n")

    db = tmp_path / "graph.db"
    store = GraphStore(db)
    try:
        registry = RepoRegistry(store)
        rid = registry.add(repo)

        parser = CodeParser()
        nodes, edges = parser.parse_file(
            py_file,
            repo_registry=registry,
            target_repos=[],  # explicit empty list
        )
        for node in nodes:
            assert node.repo_id == rid
        # No edges rewritten.
        for edge in edges:
            if edge.kind == "IMPORTS_FROM":
                assert edge.target == "os"
    finally:
        store.close()
