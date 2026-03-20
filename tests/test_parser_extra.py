"""Additional parser tests covering language-specific branches."""

from __future__ import annotations

from pathlib import Path

from better_code_review_graph.parser import (
    CodeParser,
    _is_test_file,
    _is_test_function,
    file_hash,
)


class TestParserUtils:
    def test_is_test_file(self):
        assert _is_test_file("tests/test_foo.py") is True
        assert _is_test_file("test/test_bar.py") is True
        assert _is_test_file("src/main.py") is False

    def test_is_test_function(self):
        assert _is_test_function("test_login", "test_auth.py") is True
        assert _is_test_function("login", "auth.py") is False

    def test_file_hash(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        h = file_hash(f)
        assert len(h) == 64  # SHA-256 hex digest

    def test_detect_language(self):
        parser = CodeParser()
        assert parser.detect_language(Path("test.py")) == "python"
        assert parser.detect_language(Path("test.ts")) == "typescript"
        assert parser.detect_language(Path("test.tsx")) == "tsx"
        assert parser.detect_language(Path("test.go")) == "go"
        assert parser.detect_language(Path("test.rs")) == "rust"
        assert parser.detect_language(Path("test.java")) == "java"
        assert parser.detect_language(Path("test.cs")) == "csharp"
        assert parser.detect_language(Path("test.rb")) == "ruby"
        assert parser.detect_language(Path("test.kt")) == "kotlin"
        assert parser.detect_language(Path("test.swift")) == "swift"
        assert parser.detect_language(Path("test.php")) == "php"
        assert parser.detect_language(Path("test.c")) == "c"
        assert parser.detect_language(Path("test.cpp")) == "cpp"
        assert parser.detect_language(Path("test.h")) == "c"
        assert parser.detect_language(Path("test.hpp")) == "cpp"
        assert parser.detect_language(Path("test.txt")) is None

    def test_parse_unreadable_file(self, tmp_path):
        parser = CodeParser()
        missing = tmp_path / "missing.py"
        nodes, edges = parser.parse_file(missing)
        assert nodes == []
        assert edges == []

    def test_parse_unsupported_extension(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "data.csv"
        f.write_text("a,b,c\n")
        nodes, edges = parser.parse_file(f)
        assert nodes == []

    def test_get_parser_unknown_language(self):
        parser = CodeParser()
        result = parser._get_parser("brainfuck")
        assert result is None


class TestPythonAliasedImport:
    def test_from_import_as(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "aliased.py"
        f.write_text(
            "from os.path import join as path_join\n"
            "\n"
            "def use_it():\n"
            "    path_join('a', 'b')\n"
        )
        nodes, edges = parser.parse_file(f)
        # Should have nodes for the file and function
        names = {n.name for n in nodes}
        assert "use_it" in names


class TestJSImportParsing:
    def test_js_import_named(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "app.js"
        f.write_text(
            "import { useState, useEffect } from 'react';\n"
            "\n"
            "function App() {\n"
            "    useState();\n"
            "}\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "App" in names

    def test_js_import_default(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "component.js"
        f.write_text(
            "import React from 'react';\n"
            "import * as utils from './utils';\n"
            "\n"
            "function Component() {\n"
            "    return null;\n"
            "}\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "Component" in names


class TestTSInheritance:
    def test_ts_extends(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "derived.ts"
        f.write_text(
            "class Base {\n"
            "    run() {}\n"
            "}\n"
            "\n"
            "class Derived extends Base {\n"
            "    run() { super.run(); }\n"
            "}\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "Derived" in names
        assert "Base" in names
        # Check edges exist
        assert len(edges) >= 1

    def test_ts_implements(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "impl.ts"
        f.write_text(
            "interface IService {\n"
            "    process(): void;\n"
            "}\n"
            "\n"
            "class ServiceImpl implements IService {\n"
            "    process() {}\n"
            "}\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "ServiceImpl" in names


class TestGoImports:
    def test_go_multi_import(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "main.go"
        f.write_text(
            "package main\n"
            "\n"
            "import (\n"
            '    "fmt"\n'
            '    "os"\n'
            ")\n"
            "\n"
            "func main() {\n"
            '    fmt.Println("hello")\n'
            "}\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "main" in names
        # Should have IMPORTS_FROM edges
        import_edges = [e for e in edges if e.kind == "IMPORTS_FROM"]
        assert len(import_edges) >= 1

    def test_go_single_import(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "single.go"
        f.write_text(
            'package main\n\nimport "fmt"\n\nfunc hello() {\n    fmt.Println("hi")\n}\n'
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "hello" in names


class TestGoTypeDeclaration:
    def test_go_struct_type(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "types.go"
        f.write_text(
            "package types\n"
            "\n"
            "type User struct {\n"
            "    Name string\n"
            "    Age  int\n"
            "}\n"
            "\n"
            "func (u *User) String() string {\n"
            "    return u.Name\n"
            "}\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "User" in names


class TestRubyImport:
    def test_ruby_require(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "app.rb"
        f.write_text(
            "require 'json'\n"
            "require_relative 'helper'\n"
            "\n"
            "def process\n"
            "  puts 'hello'\n"
            "end\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "process" in names
        import_edges = [e for e in edges if e.kind == "IMPORTS_FROM"]
        assert len(import_edges) >= 1


class TestCppBasicParsing:
    def test_cpp_class_with_inheritance(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "derived.cpp"
        f.write_text(
            "class Base {\n"
            "public:\n"
            "    virtual void run() {}\n"
            "};\n"
            "\n"
            "class Derived : public Base {\n"
            "public:\n"
            "    void run() override {}\n"
            "};\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "Derived" in names

    def test_c_include(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "main.c"
        f.write_text(
            "#include <stdio.h>\n"
            '#include "myheader.h"\n'
            "\n"
            "int main() {\n"
            '    printf("hello");\n'
            "    return 0;\n"
            "}\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "main" in names
        import_edges = [e for e in edges if e.kind == "IMPORTS_FROM"]
        assert len(import_edges) >= 1


class TestJavaCSImport:
    def test_java_import(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "App.java"
        f.write_text(
            "import java.util.List;\n"
            "\n"
            "public class App {\n"
            "    public void run() {}\n"
            "}\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "App" in names

    def test_csharp_using(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "Program.cs"
        f.write_text(
            "using System;\n"
            "\n"
            "class Program {\n"
            "    static void Main() {\n"
            '        Console.WriteLine("hi");\n'
            "    }\n"
            "}\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "Program" in names


class TestPythonReturnType:
    def test_python_return_annotation(self, tmp_path):
        parser = CodeParser()
        f = tmp_path / "typed.py"
        f.write_text("def greet(name: str) -> str:\n    return f'Hello {name}'\n")
        nodes, edges = parser.parse_file(f)
        func = [n for n in nodes if n.name == "greet"][0]
        assert func.return_type is not None


class TestJSModuleResolution:
    def test_resolve_relative_import(self, tmp_path):
        """JS/TS relative import resolution."""
        parser = CodeParser()

        # Create the target file
        utils_dir = tmp_path / "src"
        utils_dir.mkdir()
        (utils_dir / "utils.ts").write_text("export function helper() { return 1; }\n")

        # Create the importing file
        f = utils_dir / "app.ts"
        f.write_text(
            "import { helper } from './utils';\n\nfunction main() {\n    helper();\n}\n"
        )
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "main" in names

    def test_resolve_relative_import_index(self, tmp_path):
        """JS/TS import resolving to index file in directory."""
        parser = CodeParser()
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "index.ts").write_text("export function init() {}\n")

        f = tmp_path / "app.ts"
        f.write_text("import { init } from './lib';\nfunction start() { init(); }\n")
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "start" in names


class TestPythonModuleResolution:
    def test_resolve_python_module(self, tmp_path):
        """Python module resolution via dotted path."""
        parser = CodeParser()
        pkg = tmp_path / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "utils.py").write_text("def helper():\n    pass\n")

        f = tmp_path / "main.py"
        f.write_text("from mypackage.utils import helper\n\ndef run():\n    helper()\n")
        nodes, edges = parser.parse_file(f)
        names = {n.name for n in nodes}
        assert "run" in names
