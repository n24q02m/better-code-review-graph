import sys

with open('src/better_code_review_graph/parser.py', 'r') as f:
    content = f.read()

# Define the new methods to be inserted
new_methods = """
    def _find_decorated_definition(
        self,
        node,
        func_types: set[str],
        class_types: set[str],
    ):
        \"\"\"Unwrap decorator wrappers to reach the inner definition.\"\"\"
        for inner in node.children:
            if inner.type in func_types or inner.type in class_types:
                return inner
        return node

    def _handle_file_scope_node(
        self,
        node,
        language: str,
        source: bytes,
        func_types: set[str],
        class_types: set[str],
        import_types: set[str],
        import_map: dict[str, str],
        defined_names: set[str],
    ) -> None:
        \"\"\"Process a single node at file scope for imports and definitions.\"\"\"
        node_type = node.type
        decorator_wrappers = {"decorated_definition", "decorator"}

        # Unwrap decorator wrappers to reach the inner definition
        target = node
        if node_type in decorator_wrappers:
            target = self._find_decorated_definition(node, func_types, class_types)

        target_type = target.type

        # Collect defined function/class names
        if target_type in func_types or target_type in class_types:
            kind = "class" if target_type in class_types else "function"
            name = self._get_name(target, language, kind)
            if name:
                defined_names.add(name)

        # Collect import mappings: imported_name → module_path
        if node_type in import_types:
            self._collect_import_names(node, language, source, import_map)

    def _collect_file_scope(
        self,
        root,
        language: str,
        source: bytes,
    ) -> tuple[dict[str, str], set[str]]:
        \"\"\"Pre-scan top-level AST to collect import mappings and defined names.

        Returns:
            (import_map, defined_names) where import_map maps imported names
            to their source module/path, and defined_names is the set of
            function/class names defined at file scope.
        \"\"\"
        import_map: dict[str, str] = {}
        defined_names: set[str] = set()

        class_types = set(_CLASS_TYPES.get(language, []))
        func_types = set(_FUNCTION_TYPES.get(language, []))
        import_types = set(_IMPORT_TYPES.get(language, []))

        for child in root.children:
            self._handle_file_scope_node(
                child,
                language,
                source,
                func_types,
                class_types,
                import_types,
                import_map,
                defined_names,
            )

        return import_map, defined_names
"""

# Replace the existing _collect_file_scope
start_marker = "    def _collect_file_scope("
end_marker = "    def _collect_import_names("

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_methods + content[end_idx:]
    with open('src/better_code_review_graph/parser.py', 'w') as f:
        f.write(new_content)
    print("Successfully refactored _collect_file_scope")
else:
    print(f"Failed to find markers: start_idx={start_idx}, end_idx={end_idx}")
    sys.exit(1)
