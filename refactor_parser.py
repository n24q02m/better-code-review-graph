def refactor():
    with open("src/better_code_review_graph/parser.py") as f:
        lines = f.readlines()

    new_lines = []
    skip = False

    python_logic = """    def _collect_python_import_names(
        self,
        node,
        import_map: dict[str, str],
    ) -> None:
        if node.type != "import_from_statement":
            return

        # from X.Y import A, B → {A: X.Y, B: X.Y}
        module = None
        seen_import_keyword = False
        for child in node.children:
            if child.type == "dotted_name" and not seen_import_keyword:
                module = child.text.decode("utf-8", errors="replace")
            elif child.type == "import":
                seen_import_keyword = True
            elif seen_import_keyword and module:
                self._process_python_import_child(child, module, import_map)

    def _process_python_import_child(
        self,
        child,
        module: str,
        import_map: dict[str, str],
    ) -> None:
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

"""

    i = 0
    while i < len(lines):
        line = lines[i]

        # Update call site
        if "self._collect_import_names(child, language, source, import_map)" in line:
            new_lines.append(line.replace("source, ", ""))
            i += 1
            continue

        # Replace _collect_import_names definition
        if "def _collect_import_names(" in line and "node," in lines[i + 2]:
            new_lines.append("    def _collect_import_names(\n")
            new_lines.append("        self,\n")
            new_lines.append("        node,\n")
            new_lines.append("        language: str,\n")
            new_lines.append("        import_map: dict[str, str],\n")
            new_lines.append("    ) -> None:\n")
            new_lines.append(
                '        """Extract imported names and their source modules into import_map."""\n'
            )

            # Skip old implementation until _collect_js_import_names
            i += 7  # skip def + docstring
            while i < len(lines) and "def _collect_js_import_names" not in lines[i]:
                i += 1

            # New implementation of _collect_import_names
            new_lines.append('        if language == "python":\n')
            new_lines.append(
                "            self._collect_python_import_names(node, import_map)\n"
            )
            new_lines.append("            return\n")
            new_lines.append("\n")
            new_lines.append(
                '        if language not in ("javascript", "typescript", "tsx"):\n'
            )
            new_lines.append("            return\n")
            new_lines.append("\n")
            new_lines.append("        # JS/TS logic\n")
            new_lines.append("        module = None\n")
            new_lines.append("        for child in node.children:\n")
            new_lines.append('            if child.type == "string":\n')
            new_lines.append(
                '                module = child.text.decode("utf-8", errors="replace").strip(chr(39) + chr(34))\n'
            )
            new_lines.append("\n")
            new_lines.append("        if not module:\n")
            new_lines.append("            return\n")
            new_lines.append("\n")
            new_lines.append("        for child in node.children:\n")
            new_lines.append('            if child.type == "import_clause":\n')
            new_lines.append(
                "                self._collect_js_import_names(child, module, import_map)\n"
            )
            new_lines.append("\n")

            # Insert helper functions before _collect_js_import_names
            new_lines.append(python_logic)

            # Continue with _collect_js_import_names and the rest of the file
            continue

        new_lines.append(line)
        i += 1

    with open("src/better_code_review_graph/parser.py", "w") as f:
        f.writelines(new_lines)


if __name__ == "__main__":
    refactor()
