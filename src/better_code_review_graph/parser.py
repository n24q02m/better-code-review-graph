"""Tree-sitter based multi-language code parser.

Extracts structural nodes (classes, functions, imports, types) and edges
(calls, inheritance, contains) from source files.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

import tree_sitter_language_pack as tslp

if TYPE_CHECKING:
    from .federation import RepoRegistry
    from .resolver import TargetRepo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models for extracted entities
# ---------------------------------------------------------------------------


@dataclass
class NodeInfo:
    kind: str  # File, Class, Function, Type, Test
    name: str
    file_path: str
    # Line numbers may be None for nodes discovered without positional info
    # (e.g. placeholders inserted from qualified-name references). The SQLite
    # schema stores these columns as nullable INTEGERs.
    line_start: int | None
    line_end: int | None
    language: str = ""
    parent_name: str | None = None  # enclosing class/module
    params: str | None = None
    return_type: str | None = None
    modifiers: str | None = None
    is_test: bool = False
    extra: dict = field(default_factory=dict)
    # Raw source slice for Function-kind nodes (line_start..line_end inclusive).
    # Populated by the parser only for kind == "Function" so batch_summarize has
    # candidates without re-reading files. Class/Type/Test/File leave this None
    # to avoid bloating the DB with content that is irrelevant for LLM summaries.
    source_text: str | None = None
    # Phase 2 Task 9: federation scoping. Empty string is the single-repo
    # default and matches the SQLite ``DEFAULT ''`` on the ``nodes.repo_id``
    # column added in alembic revision ``003_federation``. The federation
    # driver populates this via ``RepoRegistry.assign(path)``.
    repo_id: str = ""


@dataclass
class EdgeInfo:
    kind: str  # CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON
    source: str  # qualified name or path
    target: str  # qualified name or path
    file_path: str
    line: int = 0
    extra: dict = field(default_factory=dict)
    # Phase 2 Task 9: federation scoping. Same shape and rationale as
    # ``NodeInfo.repo_id``; for cross-repo edges this is the *source*
    # repo's id (the edge originates in that repo).
    repo_id: str = ""


# ---------------------------------------------------------------------------
# Language extension mapping
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".rb": "ruby",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".php": "php",
    ".sol": "solidity",
}

# Tree-sitter node type mappings per language
# Maps (language) -> dict of semantic role -> list of TS node types
_CLASS_TYPES: dict[str, list[str]] = {
    "python": ["class_definition"],
    "javascript": ["class_declaration", "class"],
    "typescript": ["class_declaration", "class"],
    "tsx": ["class_declaration", "class"],
    "go": ["type_declaration"],
    "rust": ["struct_item", "enum_item", "impl_item"],
    "java": ["class_declaration", "interface_declaration", "enum_declaration"],
    "c": ["struct_specifier", "type_definition"],
    "cpp": ["class_specifier", "struct_specifier"],
    "csharp": [
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "struct_declaration",
    ],
    "ruby": ["class", "module"],
    "kotlin": ["class_declaration", "object_declaration"],
    "swift": ["class_declaration", "struct_declaration", "protocol_declaration"],
    "php": ["class_declaration", "interface_declaration"],
    "solidity": [
        "contract_declaration",
        "interface_declaration",
        "library_declaration",
        "struct_declaration",
        "enum_declaration",
        "error_declaration",
        "user_defined_type_definition",
    ],
}

_FUNCTION_TYPES: dict[str, list[str]] = {
    "python": ["function_definition"],
    "javascript": ["function_declaration", "method_definition", "arrow_function"],
    "typescript": ["function_declaration", "method_definition", "arrow_function"],
    "tsx": ["function_declaration", "method_definition", "arrow_function"],
    "go": ["function_declaration", "method_declaration"],
    "rust": ["function_item"],
    "java": ["method_declaration", "constructor_declaration"],
    "c": ["function_definition"],
    "cpp": ["function_definition"],
    "csharp": ["method_declaration", "constructor_declaration"],
    "ruby": ["method", "singleton_method"],
    "kotlin": ["function_declaration"],
    "swift": ["function_declaration"],
    "php": ["function_definition", "method_declaration"],
    # Solidity: events and modifiers use kind="Function" because the graph
    # schema has no dedicated kind for them.  State variables are also modeled
    # as Function nodes (public ones auto-generate getters) and distinguished
    # via extra["solidity_kind"].
    "solidity": [
        "function_definition",
        "constructor_definition",
        "modifier_definition",
        "event_definition",
        "fallback_receive_definition",
    ],
}

_IMPORT_TYPES: dict[str, list[str]] = {
    "python": ["import_statement", "import_from_statement"],
    "javascript": ["import_statement"],
    "typescript": ["import_statement"],
    "tsx": ["import_statement"],
    "go": ["import_declaration"],
    "rust": ["use_declaration"],
    "java": ["import_declaration"],
    "c": ["preproc_include"],
    "cpp": ["preproc_include"],
    "csharp": ["using_directive"],
    "ruby": ["call"],  # require/require_relative
    "kotlin": ["import_header"],
    "swift": ["import_declaration"],
    "php": ["namespace_use_declaration"],
    "solidity": ["import_directive"],
}

_CALL_TYPES: dict[str, list[str]] = {
    "python": ["call"],
    "javascript": ["call_expression", "new_expression"],
    "typescript": ["call_expression", "new_expression"],
    "tsx": ["call_expression", "new_expression"],
    "go": ["call_expression"],
    "rust": ["call_expression", "macro_invocation"],
    "java": ["method_invocation", "object_creation_expression"],
    "c": ["call_expression"],
    "cpp": ["call_expression"],
    "csharp": ["invocation_expression", "object_creation_expression"],
    "ruby": ["call", "method_call"],
    "kotlin": ["call_expression"],
    "swift": ["call_expression"],
    "php": ["function_call_expression", "member_call_expression"],
    "solidity": ["call_expression"],
}

# Patterns that indicate a test function
_TEST_PATTERNS = [
    re.compile(r"^test_"),
    re.compile(r"^Test"),
    re.compile(r"_test$"),
    re.compile(r"\.test\."),
    re.compile(r"\.spec\."),
    re.compile(r"_spec$"),
]


def _is_test_function(name: str, file_path: str) -> bool:
    """A function is a test only if its name matches test patterns.
    Being in a test file alone is not sufficient (test files contain helpers too).
    """
    return any(p.search(name) for p in _TEST_PATTERNS)


def file_hash(path: Path) -> str:
    """SHA-256 hash of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_source_span(source_lines: list[str], start: int, end: int) -> str:
    """Return the joined slice of ``source_lines`` between 1-indexed
    ``start`` and ``end`` (both inclusive).

    ``source_lines`` is the file split on ``"\n"``. ``start`` / ``end``
    follow the same 1-indexed convention used by NodeInfo (Tree-sitter
    ``start_point[0] + 1``). Out-of-range bounds clamp to the available
    range so a malformed ``end`` (e.g. past EOF) returns whatever lines
    do exist instead of crashing. An empty ``source_lines`` returns an
    empty string.
    """
    if not source_lines:
        return ""
    # Clamp to valid 1-indexed range; tolerate inverted/None-like bounds.
    lo = max(1, start) if start else 1
    hi = min(len(source_lines), end) if end else len(source_lines)
    if hi < lo:
        return ""
    return "\n".join(source_lines[lo - 1 : hi])


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class CodeParser:
    """Parses source files using Tree-sitter and extracts structural information."""

    def __init__(self) -> None:
        self._parsers: dict[str, object] = {}
        self._module_file_cache: dict[str, str | None] = {}
        # Per-parse scratchpad: the file currently being parsed split on "\n".
        # Set in parse_bytes(), read by _handle_function_node() to populate
        # NodeInfo.source_text. Reset to None between parses so a stale
        # buffer can never leak across files.
        self._current_source_lines: list[str] | None = None

    def _get_parser(self, language: str):
        if language not in self._parsers:
            try:
                # tslp.get_parser expects SupportedLanguage (a large Literal
                # union). We validate against EXTENSION_TO_LANGUAGE upstream
                # and fall back on ValueError/KeyError via the generic except
                # below, so narrowing through cast is safe here.
                self._parsers[language] = tslp.get_parser(
                    cast("tslp.SupportedLanguage", language)
                )
            except Exception:
                return None
        return self._parsers[language]

    def detect_language(self, path: Path) -> str | None:
        return EXTENSION_TO_LANGUAGE.get(path.suffix.lower())

    def parse_file(
        self,
        path: Path,
        *,
        repo_registry: RepoRegistry | None = None,
        target_repos: list[TargetRepo] | None = None,
    ) -> tuple[list[NodeInfo], list[EdgeInfo]]:
        """Parse a single file and return extracted nodes and edges.

        Parameters
        ----------
        path:
            Filesystem path to the file to parse.
        repo_registry:
            Phase 2 Task 9 — when provided, every emitted ``NodeInfo``
            and ``EdgeInfo`` has its ``repo_id`` populated from
            ``repo_registry.assign(path)``. Single-repo callers (the
            default) get the legacy behaviour with empty ``repo_id``.
        target_repos:
            Phase 2 Task 9 — when both this and ``repo_registry`` are
            provided, ``IMPORTS_FROM`` edges whose target can be
            resolved across the federated targets are rewritten to
            ``<other_repo_id>:<file>::<symbol>`` via
            :func:`better_code_review_graph.resolver.resolve_cross_repo_imports`.
            Unresolved imports keep their original within-repo target.
        """
        try:
            source = path.read_bytes()
        except (OSError, PermissionError):
            return [], []
        return self.parse_bytes(
            path,
            source,
            repo_registry=repo_registry,
            target_repos=target_repos,
        )

    def parse_bytes(
        self,
        path: Path,
        source: bytes,
        *,
        repo_registry: RepoRegistry | None = None,
        target_repos: list[TargetRepo] | None = None,
    ) -> tuple[list[NodeInfo], list[EdgeInfo]]:
        """Parse pre-read bytes and return extracted nodes and edges.

        This avoids re-reading the file from disk, eliminating TOCTOU gaps
        when the caller has already read the bytes (e.g. for hashing).

        See :meth:`parse_file` for the ``repo_registry`` / ``target_repos``
        federation kwargs.
        """
        language = self.detect_language(path)
        if not language:
            return [], []

        parser = self._get_parser(language)
        if not parser:
            return [], []

        tree = parser.parse(source)
        nodes: list[NodeInfo] = []
        edges: list[EdgeInfo] = []
        file_path_str = str(path)

        # Decode + split the file once so _handle_function_node can populate
        # NodeInfo.source_text without re-reading bytes per Function. The
        # scratchpad is cleared at the end so stale lines never leak into the
        # next parse_bytes call.
        source_text_full = source.decode("utf-8", errors="replace")
        self._current_source_lines = source_text_full.split("\n")

        try:
            # File node
            nodes.append(
                NodeInfo(
                    kind="File",
                    name=file_path_str,
                    file_path=file_path_str,
                    line_start=1,
                    line_end=source.count(b"\n") + 1,
                    language=language,
                )
            )

            # Pre-scan for import mappings and defined names
            import_map, defined_names = self._collect_file_scope(
                tree.root_node,
                language,
                source,
            )

            # Walk the tree
            self._extract_from_tree(
                tree.root_node,
                source,
                language,
                file_path_str,
                nodes,
                edges,
                import_map=import_map,
                defined_names=defined_names,
            )
        finally:
            self._current_source_lines = None

        # Phase 2 Task 9: federation post-processing. Single-repo callers
        # (no registry) skip this entirely so behaviour is unchanged.
        if repo_registry is not None:
            self._apply_federation(
                path=path,
                language=language,
                nodes=nodes,
                edges=edges,
                repo_registry=repo_registry,
                target_repos=target_repos,
            )

        return nodes, edges

    def _apply_federation(
        self,
        *,
        path: Path,
        language: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        repo_registry: RepoRegistry,
        target_repos: list[TargetRepo] | None,
    ) -> None:
        """Stamp ``repo_id`` on nodes/edges and resolve cross-repo imports.

        Tagging is unconditional once a registry is wired in (every node
        belongs to *some* repo, even in single-repo federation mode);
        cross-repo IMPORTS_FROM rewrites are best-effort and only run
        when ``target_repos`` is non-empty.
        """
        # Resolve once, reuse for every node/edge in this file.
        try:
            source_repo_id = repo_registry.assign(path)
        except ValueError:
            # File lives outside every registered root — leave repo_id
            # empty so the row is still writeable; the caller decides
            # whether to register the path before retrying.
            return

        for node in nodes:
            node.repo_id = source_repo_id
        for edge in edges:
            edge.repo_id = source_repo_id

        if not target_repos:
            return

        # Cross-repo IMPORTS_FROM rewrite. Lazy import keeps the
        # resolver's tomllib/regex cost off the hot path for callers
        # that don't pass target_repos.
        from .resolver import resolve_cross_repo_imports  # noqa: PLC0415

        # Look up the source repo's filesystem root (registry knows it)
        # so the resolver can read its ``pyproject.toml`` /
        # ``Cargo.toml`` / ``go.mod`` etc. ``RepoRegistry.entries()``
        # gives us the canonical mapping.
        source_root: Path | None = None
        for entry in repo_registry.entries():
            if entry.repo_id == source_repo_id:
                source_root = entry.path
                break
        if source_root is None:
            return

        for edge in edges:
            if edge.kind != "IMPORTS_FROM":
                continue
            # Prefer the original import line (captured into
            # ``extra["import_stmt"]`` by ``_handle_import_node``) so
            # the resolvers see the imported symbol name. Fall back to
            # a synthesised statement built from the bare target —
            # this keeps the path working for legacy callers that
            # construct EdgeInfo by hand without ``extra``.
            stmt = (edge.extra or {}).get("import_stmt") or self._build_resolver_stmt(
                language, edge.target
            )
            try:
                resolved = resolve_cross_repo_imports(
                    stmt,
                    language,
                    source_root,
                    source_repo_id,
                    target_repos,
                )
            except Exception:
                # The resolver may touch the filesystem; treat any
                # error as "no cross-repo match" rather than aborting
                # the whole parse. Single-repo mode is preserved.
                resolved = None
            if resolved is not None:
                edge.target = resolved

    @staticmethod
    def _build_resolver_stmt(language: str, target: str) -> str:
        """Synthesise an import statement from the parser's bare target.

        The parser stores per-language extracted forms (Python: dotted
        module, JS/TS: module path string, Go: quoted path, Rust: full
        ``use`` line, Java/Kotlin/C#: dotted name, Solidity/Ruby:
        quoted path). The cross-repo resolvers re-parse these strings
        with their own regexes so the round-trip is lossy in edge
        cases (e.g. Python's imported symbol name is dropped because
        we only keep the module). For Phase 2 Task 9 this is the
        documented trade-off: cross-repo qualified names use the
        module's basename when the imported symbol name is not
        threaded through the parser-extracted target.
        """
        lang = language.lower()
        if lang == "python":
            return f"import {target}"
        if lang in ("javascript", "typescript", "tsx"):
            # TypeScript resolver matches the module string anywhere on the line.
            return f'import "{target}"'
        if lang == "go":
            return f'import "{target}"'
        if lang == "rust":
            # Rust resolver expects ``use ...;`` shape; the target is
            # already the full path-with-`::`.
            stripped = target.strip().rstrip(";")
            if stripped.startswith("use "):
                return target
            return f"use {stripped};"
        if lang in ("java", "kotlin"):
            return f"import {target};"
        # Fallback / tier-2 languages: pass through verbatim.
        return target

    def _extract_from_tree(
        self,
        root,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None = None,
        enclosing_func: str | None = None,
        import_map: dict[str, str] | None = None,
        defined_names: set[str] | None = None,
    ) -> None:
        """Recursively walk the AST and extract nodes/edges."""
        class_types = set(_CLASS_TYPES.get(language, []))
        func_types = set(_FUNCTION_TYPES.get(language, []))
        import_types = set(_IMPORT_TYPES.get(language, []))
        call_types = set(_CALL_TYPES.get(language, []))

        for child in root.children:
            node_type = child.type
            processed = False

            if node_type in class_types:
                processed = self._handle_class_node(
                    child,
                    source,
                    language,
                    file_path,
                    nodes,
                    edges,
                    enclosing_class,
                    import_map,
                    defined_names,
                )
            elif node_type in func_types:
                processed = self._handle_function_node(
                    child,
                    source,
                    language,
                    file_path,
                    nodes,
                    edges,
                    enclosing_class,
                    import_map,
                    defined_names,
                )
            elif node_type in import_types:
                processed = self._handle_import_node(
                    child, source, language, file_path, edges
                )
            elif node_type in call_types:
                processed = self._handle_call_node(
                    child,
                    source,
                    language,
                    file_path,
                    edges,
                    enclosing_class,
                    enclosing_func,
                    import_map,
                    defined_names,
                )

            if not processed and language == "solidity":
                processed = self._handle_solidity_node(
                    child,
                    source,
                    language,
                    file_path,
                    nodes,
                    edges,
                    enclosing_class,
                    enclosing_func,
                )

            if processed:
                continue

            # Recurse for other node types
            self._extract_from_tree(
                child,
                source,
                language,
                file_path,
                nodes,
                edges,
                enclosing_class=enclosing_class,
                enclosing_func=enclosing_func,
                import_map=import_map,
                defined_names=defined_names,
            )

    def _handle_class_node(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None,
        import_map: dict[str, str] | None,
        defined_names: set[str] | None,
    ) -> bool:
        name = self._get_name(node, language, "class")
        if not name:
            return False

        node_info = NodeInfo(
            kind="Class",
            name=name,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            language=language,
            parent_name=enclosing_class,
        )
        nodes.append(node_info)

        # CONTAINS edge
        edges.append(
            EdgeInfo(
                kind="CONTAINS",
                source=file_path,
                target=self._qualify(name, file_path, enclosing_class),
                file_path=file_path,
                line=node.start_point[0] + 1,
            )
        )

        # Inheritance edges
        bases = self._get_bases(node, language, source)
        for base in bases:
            edges.append(
                EdgeInfo(
                    kind="INHERITS",
                    source=self._qualify(name, file_path, enclosing_class),
                    target=base,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                )
            )

        # Recurse into class body
        self._extract_from_tree(
            node,
            source,
            language,
            file_path,
            nodes,
            edges,
            enclosing_class=name,
            enclosing_func=None,
            import_map=import_map,
            defined_names=defined_names,
        )
        return True

    def _handle_function_node(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None,
        import_map: dict[str, str] | None,
        defined_names: set[str] | None,
    ) -> bool:
        name = self._get_name(node, language, "function")
        if not name:
            return False

        is_test = _is_test_function(name, file_path)
        kind = "Test" if is_test else "Function"
        qualified = self._qualify(name, file_path, enclosing_class)
        params = self._get_params(node, language, source)
        ret_type = self._get_return_type(node, language, source)

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1
        # Only Function-kind nodes carry source_text — Test/Class skip to keep
        # batch_summarize's candidate set focused and the DB compact.
        source_text: str | None = None
        if kind == "Function" and self._current_source_lines is not None:
            source_text = _extract_source_span(
                self._current_source_lines, line_start, line_end
            )

        node_info = NodeInfo(
            kind=kind,
            name=name,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            language=language,
            parent_name=enclosing_class,
            params=params,
            return_type=ret_type,
            is_test=is_test,
            source_text=source_text,
        )
        nodes.append(node_info)

        # CONTAINS edge
        container = (
            self._qualify(enclosing_class, file_path, None)
            if enclosing_class
            else file_path
        )
        edges.append(
            EdgeInfo(
                kind="CONTAINS",
                source=container,
                target=qualified,
                file_path=file_path,
                line=node.start_point[0] + 1,
            )
        )

        # Solidity: modifier invocations on functions → CALLS edges
        if language == "solidity":
            for sub in node.children:
                if sub.type == "modifier_invocation":
                    for ident in sub.children:
                        if ident.type == "identifier":
                            edges.append(
                                EdgeInfo(
                                    kind="CALLS",
                                    source=qualified,
                                    target=ident.text.decode(
                                        "utf-8",
                                        errors="replace",
                                    ),
                                    file_path=file_path,
                                    line=sub.start_point[0] + 1,
                                )
                            )
                            break

        # Recurse to find calls inside the function
        self._extract_from_tree(
            node,
            source,
            language,
            file_path,
            nodes,
            edges,
            enclosing_class=enclosing_class,
            enclosing_func=name,
            import_map=import_map,
            defined_names=defined_names,
        )
        return True

    def _handle_import_node(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        edges: list[EdgeInfo],
    ) -> bool:
        imports = self._extract_import(node, language, source)
        # Phase 2 Task 9: stash the raw import line on the edge so the
        # federation post-processing can hand the full statement (with
        # the imported symbol name intact) to the cross-repo resolvers.
        # Single-repo callers ignore this field entirely.
        raw_stmt = node.text.decode("utf-8", errors="replace").strip()
        for imp_target in imports:
            edges.append(
                EdgeInfo(
                    kind="IMPORTS_FROM",
                    source=file_path,
                    target=imp_target,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                    extra={"import_stmt": raw_stmt},
                )
            )
        return True

    def _handle_call_node(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        edges: list[EdgeInfo],
        enclosing_class: str | None,
        enclosing_func: str | None,
        import_map: dict[str, str] | None,
        defined_names: set[str] | None,
    ) -> bool:
        call_name = self._get_call_name(node, language, source)
        if call_name and enclosing_func:
            caller = self._qualify(enclosing_func, file_path, enclosing_class)
            target = self._resolve_call_target(
                call_name,
                file_path,
                language,
                import_map or {},
                defined_names or set(),
            )
            edges.append(
                EdgeInfo(
                    kind="CALLS",
                    source=caller,
                    target=target,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                )
            )
        return False

    def _handle_solidity_emit_statement(
        self,
        node,
        file_path: str,
        edges: list[EdgeInfo],
        enclosing_class: str | None,
        enclosing_func: str | None,
    ) -> bool:
        if not enclosing_func:
            return False
        for sub in node.children:
            if sub.type == "expression":
                for ident in sub.children:
                    if ident.type == "identifier":
                        caller = self._qualify(
                            enclosing_func,
                            file_path,
                            enclosing_class,
                        )
                        edges.append(
                            EdgeInfo(
                                kind="CALLS",
                                source=caller,
                                target=ident.text.decode("utf-8", errors="replace"),
                                file_path=file_path,
                                line=node.start_point[0] + 1,
                            )
                        )
        return False

    def _handle_solidity_state_variable(
        self,
        node,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None,
    ) -> bool:
        if not enclosing_class:
            return False
        var_name = None
        var_visibility = None
        var_mutability = None
        var_type = None
        for sub in node.children:
            if sub.type == "identifier":
                var_name = sub.text.decode("utf-8", errors="replace")
            elif sub.type == "visibility":
                var_visibility = sub.text.decode("utf-8", errors="replace")
            elif sub.type == "type_name":
                var_type = sub.text.decode("utf-8", errors="replace")
            elif sub.type in ("constant", "immutable"):
                var_mutability = sub.type
        if var_name:
            qualified = self._qualify(var_name, file_path, enclosing_class)
            nodes.append(
                NodeInfo(
                    kind="Function",
                    name=var_name,
                    file_path=file_path,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    language=language,
                    parent_name=enclosing_class,
                    return_type=var_type,
                    modifiers=var_visibility,
                    extra={
                        "solidity_kind": "state_variable",
                        "mutability": var_mutability,
                    },
                )
            )
            edges.append(
                EdgeInfo(
                    kind="CONTAINS",
                    source=self._qualify(
                        enclosing_class,
                        file_path,
                        None,
                    ),
                    target=qualified,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                )
            )
            return True
        return False

    def _handle_solidity_constant_variable(
        self,
        node,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None,
    ) -> bool:
        var_name = None
        var_type = None
        for sub in node.children:
            if sub.type == "identifier":
                var_name = sub.text.decode("utf-8", errors="replace")
            elif sub.type == "type_name":
                var_type = sub.text.decode("utf-8", errors="replace")
        if var_name:
            qualified = self._qualify(
                var_name,
                file_path,
                enclosing_class,
            )
            nodes.append(
                NodeInfo(
                    kind="Function",
                    name=var_name,
                    file_path=file_path,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    language=language,
                    parent_name=enclosing_class,
                    return_type=var_type,
                    extra={"solidity_kind": "constant"},
                )
            )
            container = (
                self._qualify(enclosing_class, file_path, None)
                if enclosing_class
                else file_path
            )
            edges.append(
                EdgeInfo(
                    kind="CONTAINS",
                    source=container,
                    target=qualified,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                )
            )
            return True
        return False

    def _handle_solidity_using_directive(
        self,
        node,
        file_path: str,
        edges: list[EdgeInfo],
        enclosing_class: str | None,
    ) -> bool:
        lib_name = None
        for sub in node.children:
            if sub.type == "type_alias":
                for ident in sub.children:
                    if ident.type == "identifier":
                        lib_name = ident.text.decode(
                            "utf-8",
                            errors="replace",
                        )
        if lib_name:
            source_name = (
                self._qualify(enclosing_class, file_path, None)
                if enclosing_class
                else file_path
            )
            edges.append(
                EdgeInfo(
                    kind="DEPENDS_ON",
                    source=source_name,
                    target=lib_name,
                    file_path=file_path,
                    line=node.start_point[0] + 1,
                )
            )
            return True
        return False

    def _handle_solidity_node(
        self,
        node,
        source: bytes,
        language: str,
        file_path: str,
        nodes: list[NodeInfo],
        edges: list[EdgeInfo],
        enclosing_class: str | None,
        enclosing_func: str | None,
    ) -> bool:
        if language != "solidity":
            return False

        node_type = node.type
        if node_type == "emit_statement":
            return self._handle_solidity_emit_statement(
                node, file_path, edges, enclosing_class, enclosing_func
            )
        if node_type == "state_variable_declaration":
            return self._handle_solidity_state_variable(
                node, language, file_path, nodes, edges, enclosing_class
            )
        if node_type == "constant_variable_declaration":
            return self._handle_solidity_constant_variable(
                node, language, file_path, nodes, edges, enclosing_class
            )
        if node_type == "using_directive":
            return self._handle_solidity_using_directive(
                node, file_path, edges, enclosing_class
            )
        return False

    def _collect_file_scope(
        self,
        root,
        language: str,
        source: bytes,
    ) -> tuple[dict[str, str], set[str]]:
        """Pre-scan top-level AST to collect import mappings and defined names.

        Returns:
            (import_map, defined_names) where import_map maps imported names
            to their source module/path, and defined_names is the set of
            function/class names defined at file scope.
        """
        import_map: dict[str, str] = {}
        defined_names: set[str] = set()

        class_types = set(_CLASS_TYPES.get(language, []))
        func_types = set(_FUNCTION_TYPES.get(language, []))
        import_types = set(_IMPORT_TYPES.get(language, []))

        # Node types that wrap a class/function with decorators/annotations
        decorator_wrappers = {"decorated_definition", "decorator"}

        for child in root.children:
            node_type = child.type

            # Unwrap decorator wrappers to reach the inner definition
            target = child
            if node_type in decorator_wrappers:
                for inner in child.children:
                    if inner.type in func_types or inner.type in class_types:
                        target = inner
                        break

            target_type = target.type

            # Collect defined function/class names
            if target_type in func_types or target_type in class_types:
                name = self._get_name(
                    target,
                    language,
                    "class" if target_type in class_types else "function",
                )
                if name:
                    defined_names.add(name)

            # Collect import mappings: imported_name → module_path
            if node_type in import_types:
                self._collect_import_names(child, language, source, import_map)

        return import_map, defined_names

    def _collect_import_names(
        self,
        node,
        language: str,
        source: bytes,
        import_map: dict[str, str],
    ) -> None:
        """Extract imported names and their source modules into import_map."""
        if language == "python":
            if node.type == "import_from_statement":
                # from X.Y import A, B → {A: X.Y, B: X.Y}
                module = None
                seen_import_keyword = False
                for child in node.children:
                    if child.type == "dotted_name" and not seen_import_keyword:
                        module = child.text.decode("utf-8", errors="replace")
                    elif child.type == "import":
                        seen_import_keyword = True
                    elif seen_import_keyword and module:
                        if child.type in ("identifier", "dotted_name"):
                            name = child.text.decode("utf-8", errors="replace")
                            import_map[name] = module
                        elif child.type == "aliased_import":
                            # from X import A as B → {B: X}
                            names = [
                                sub.text.decode("utf-8", errors="replace")
                                for sub in child.children
                                if sub.type in ("identifier", "dotted_name")
                            ]
                            # Last name is the alias (local name)
                            if names:
                                import_map[names[-1]] = module

        elif language in ("javascript", "typescript", "tsx"):
            # import { A, B } from './path' → {A: ./path, B: ./path}
            module = None
            for child in node.children:
                if child.type == "string":
                    module = child.text.decode("utf-8", errors="replace").strip("'\"")
            if module:
                for child in node.children:
                    if child.type == "import_clause":
                        self._collect_js_import_names(child, module, import_map)

    def _collect_js_import_names(
        self,
        clause_node,
        module: str,
        import_map: dict[str, str],
    ) -> None:
        """Walk JS/TS import_clause to extract named and default imports."""
        for child in clause_node.children:
            if child.type == "identifier":
                # Default import
                import_map[child.text.decode("utf-8", errors="replace")] = module
            elif child.type == "named_imports":
                for spec in child.children:
                    if spec.type == "import_specifier":
                        # Could be: name or name as alias
                        names = [
                            s.text.decode("utf-8", errors="replace")
                            for s in spec.children
                            if s.type in ("identifier", "property_identifier")
                        ]
                        # Last identifier is the local name
                        if names:
                            import_map[names[-1]] = module

    def _resolve_module_to_file(
        self,
        module: str,
        file_path: str,
        language: str,
    ) -> str | None:
        """Resolve a module/import path to an absolute file path.

        Uses self._module_file_cache to avoid repeated filesystem lookups.
        """
        caller_dir = str(Path(file_path).parent)
        cache_key = f"{language}:{caller_dir}:{module}"
        if cache_key in self._module_file_cache:
            return self._module_file_cache[cache_key]

        resolved = self._do_resolve_module(module, file_path, language)
        self._module_file_cache[cache_key] = resolved
        return resolved

    def _do_resolve_module(
        self,
        module: str,
        file_path: str,
        language: str,
    ) -> str | None:
        """Language-aware module-to-file resolution."""
        caller_dir = Path(file_path).parent

        if language == "python":
            rel_path = module.replace(".", "/")
            candidates = [rel_path + ".py", rel_path + "/__init__.py"]
            # Walk up from caller's directory to find the module file
            current = caller_dir
            while True:
                for candidate in candidates:
                    target = current / candidate
                    if target.is_file():
                        return str(target.resolve())
                if current == current.parent:
                    break
                current = current.parent

        elif language in ("javascript", "typescript", "tsx"):
            if module.startswith("."):
                # Relative import — resolve from caller's directory
                base = caller_dir / module
                extensions = [".ts", ".tsx", ".js", ".jsx"]
                # Try exact path first (might already have extension)
                if base.is_file():
                    return str(base.resolve())
                # Try with extensions
                for ext in extensions:
                    target = base.with_suffix(ext)
                    if target.is_file():
                        return str(target.resolve())
                # Try index file in directory
                if base.is_dir():
                    for ext in extensions:
                        target = base / f"index{ext}"
                        if target.is_file():
                            return str(target.resolve())

        return None

    def _resolve_call_target(
        self,
        call_name: str,
        file_path: str,
        language: str,
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> str:
        """Resolve a bare call name to a qualified target, with fallback."""
        if call_name in defined_names:
            return self._qualify(call_name, file_path, None)
        if call_name in import_map:
            resolved = self._resolve_module_to_file(
                import_map[call_name],
                file_path,
                language,
            )
            if resolved:
                return self._qualify(call_name, resolved, None)
        return call_name

    def _qualify(self, name: str, file_path: str, enclosing_class: str | None) -> str:
        """Create a qualified name: file_path::ClassName.name or file_path::name."""
        if enclosing_class:
            return f"{file_path}::{enclosing_class}.{name}"
        return f"{file_path}::{name}"

    def _get_name(self, node, language: str, kind: str) -> str | None:
        """Extract the name from a class/function definition node."""
        # Solidity: constructor and receive/fallback have no identifier child
        if language == "solidity":
            if node.type == "constructor_definition":
                return "constructor"
            if node.type == "fallback_receive_definition":
                for child in node.children:
                    if child.type in ("receive", "fallback"):
                        return child.text.decode("utf-8", errors="replace")
        # For C/C++: function names are inside function_declarator/pointer_declarator
        # Check these first to avoid matching the return type_identifier
        if language in ("c", "cpp") and kind == "function":
            for child in node.children:
                if child.type in ("function_declarator", "pointer_declarator"):
                    result = self._get_name(child, language, kind)
                    if result:
                        return result
        # Most languages use a 'name' child
        for child in node.children:
            if child.type in (
                "identifier",
                "name",
                "type_identifier",
                "property_identifier",
                "simple_identifier",
                "constant",
            ):
                return child.text.decode("utf-8", errors="replace")
        # For Go type declarations, look for type_spec
        if language == "go" and node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    return self._get_name(child, language, kind)
        return None

    def _get_params(self, node, language: str, source: bytes) -> str | None:
        """Extract parameter list as a string."""
        for child in node.children:
            if child.type in ("parameters", "formal_parameters", "parameter_list"):
                return child.text.decode("utf-8", errors="replace")
        # Solidity: parameters are direct children between ( and )
        if language == "solidity":
            params = [
                c.text.decode("utf-8", errors="replace")
                for c in node.children
                if c.type == "parameter"
            ]
            if params:
                return f"({', '.join(params)})"
        return None

    def _get_return_type(self, node, language: str, source: bytes) -> str | None:
        """Extract return type annotation if present."""
        for child in node.children:
            if child.type in (
                "type",
                "return_type",
                "type_annotation",
                "return_type_definition",
            ):
                return child.text.decode("utf-8", errors="replace")
        # Python: look for -> annotation
        if language == "python":
            for i, child in enumerate(node.children):
                if child.type == "->" and i + 1 < len(node.children):
                    return node.children[i + 1].text.decode("utf-8", errors="replace")
        return None

    def _get_bases(self, node, language: str, source: bytes) -> list[str]:
        """Extract base classes / implemented interfaces."""
        bases = []
        if language == "python":
            for child in node.children:
                if child.type == "argument_list":
                    for arg in child.children:
                        if arg.type in ("identifier", "attribute"):
                            bases.append(arg.text.decode("utf-8", errors="replace"))
        elif language in ("java", "csharp", "kotlin"):
            # Look for superclass/interfaces in extends/implements clauses
            for child in node.children:
                if child.type in (
                    "superclass",
                    "super_interfaces",
                    "extends_type",
                    "implements_type",
                    "type_identifier",
                    "supertype",
                    "delegation_specifier",
                ):
                    text = child.text.decode("utf-8", errors="replace")
                    bases.append(text)
        elif language == "cpp":
            # C++: base_class_clause contains type_identifiers
            for child in node.children:
                if child.type == "base_class_clause":
                    for sub in child.children:
                        if sub.type == "type_identifier":
                            bases.append(sub.text.decode("utf-8", errors="replace"))
        elif language in ("typescript", "javascript", "tsx"):
            # extends clause
            for child in node.children:
                if child.type in ("extends_clause", "implements_clause"):
                    for sub in child.children:
                        if sub.type in (
                            "identifier",
                            "type_identifier",
                            "nested_identifier",
                        ):
                            bases.append(sub.text.decode("utf-8", errors="replace"))
        elif language == "solidity":
            # contract Foo is Bar, Baz { ... }
            for child in node.children:
                if child.type == "inheritance_specifier":
                    for sub in child.children:
                        if sub.type == "user_defined_type":
                            for ident in sub.children:
                                if ident.type == "identifier":
                                    bases.append(
                                        ident.text.decode("utf-8", errors="replace")
                                    )
        elif language == "go":
            # Embedded structs / interface composition
            for child in node.children:
                if child.type == "type_spec":
                    for sub in child.children:
                        if sub.type in ("struct_type", "interface_type"):
                            for field_node in sub.children:
                                if field_node.type == "field_declaration_list":
                                    for f in field_node.children:
                                        if f.type == "type_identifier":
                                            bases.append(
                                                f.text.decode("utf-8", errors="replace")
                                            )
        return bases

    def _extract_import(self, node, language: str, source: bytes) -> list[str]:
        """Extract import targets as module/path strings."""
        text = node.text.decode("utf-8", errors="replace").strip()

        if language == "python":
            return self._extract_import_python(node)
        elif language in ("javascript", "typescript", "tsx"):
            return self._extract_import_javascript(node)
        elif language == "go":
            return self._extract_import_go(node)
        elif language == "rust":
            return self._extract_import_rust(text)
        elif language in ("c", "cpp"):
            return self._extract_import_c(node)
        elif language in ("java", "csharp"):
            return self._extract_import_java(text)
        elif language == "solidity":
            return self._extract_import_solidity(node)
        elif language == "ruby":
            return self._extract_import_ruby(text)
        else:
            return [text]

    def _extract_import_python(self, node) -> list[str]:
        imports = []
        if node.type == "import_from_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    imports.append(child.text.decode("utf-8", errors="replace"))
                    break
        else:
            for child in node.children:
                if child.type == "dotted_name":
                    imports.append(child.text.decode("utf-8", errors="replace"))
        return imports

    def _extract_import_javascript(self, node) -> list[str]:
        imports = []
        for child in node.children:
            if child.type == "string":
                val = child.text.decode("utf-8", errors="replace").strip("'\"")
                imports.append(val)
        return imports

    def _extract_import_go(self, node) -> list[str]:
        imports = []
        for child in node.children:
            if child.type == "import_spec_list":
                for spec in child.children:
                    if spec.type == "import_spec":
                        for s in spec.children:
                            if s.type == "interpreted_string_literal":
                                val = s.text.decode("utf-8", errors="replace")
                                imports.append(val.strip('"'))
            elif child.type == "import_spec":
                for s in child.children:
                    if s.type == "interpreted_string_literal":
                        val = s.text.decode("utf-8", errors="replace")
                        imports.append(val.strip('"'))
        return imports

    def _extract_import_rust(self, text: str) -> list[str]:
        # use crate::module::item
        return [text.replace("use ", "").rstrip(";").strip()]

    def _extract_import_c(self, node) -> list[str]:
        imports = []
        for child in node.children:
            if child.type in ("system_lib_string", "string_literal"):
                val = child.text.decode("utf-8", errors="replace").strip('<>"')
                imports.append(val)
        return imports

    def _extract_import_java(self, text: str) -> list[str]:
        imports = []
        parts = text.split()
        if len(parts) >= 2:
            imports.append(parts[-1].rstrip(";"))
        return imports

    def _extract_import_solidity(self, node) -> list[str]:
        imports = []
        for child in node.children:
            if child.type == "string":
                val = child.text.decode("utf-8", errors="replace").strip('"')
                if val:
                    imports.append(val)
        return imports

    def _extract_import_ruby(self, text: str) -> list[str]:
        imports = []
        if "require" in text:
            match = re.search(r"""['"](.*?)['"]""", text)
            if match:
                imports.append(match.group(1))
        return imports

    def _get_call_name(self, node, language: str, source: bytes) -> str | None:
        """Extract the function/method name being called."""
        if not node.children:
            return None

        first = node.children[0]

        # Solidity wraps call targets in an 'expression' node – unwrap it
        if language == "solidity" and first.type == "expression" and first.children:
            first = first.children[0]

        # Simple call: func_name(args)
        if first.type == "identifier":
            return first.text.decode("utf-8", errors="replace")

        # Method call: obj.method(args)
        member_types = (
            "attribute",
            "member_expression",
            "field_expression",
            "selector_expression",
        )
        if first.type in member_types:
            # Get the rightmost identifier (the method name)
            for child in reversed(first.children):
                if child.type in (
                    "identifier",
                    "property_identifier",
                    "field_identifier",
                    "field_name",
                ):
                    return child.text.decode("utf-8", errors="replace")
            return first.text.decode("utf-8", errors="replace")

        # Scoped call (e.g., Rust path::func())
        if first.type in ("scoped_identifier", "qualified_name"):
            return first.text.decode("utf-8", errors="replace")

        return None
