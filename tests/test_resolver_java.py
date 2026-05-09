"""Tests for the Java cross-repo resolver (Phase 2 Task 7).

Covers :mod:`better_code_review_graph.resolver.java`:

* ``parse_import_statement`` — turns Java ``import com.example.a.Util;``
  declarations (including ``import static`` form) into a
  :class:`JavaImport`.
* ``_read_pom_modules`` — extracts ``<modules><module>...</module></modules>``
  entries from a Maven ``pom.xml`` (with or without the default XML
  namespace).
* ``_read_gradle_includes`` — extracts ``include`` declarations from
  ``settings.gradle`` (Groovy DSL) and ``settings.gradle.kts`` (Kotlin
  DSL).
* ``JavaResolver.resolve`` — combines Maven module + Gradle include
  parsing with a standard ``src/main/java/<package>/<Class>.java`` walk
  to yield ``<repo_id>:<file_path>::<symbol>`` qualified names on hit.
"""

from __future__ import annotations

from pathlib import Path

from better_code_review_graph.resolver.java import (
    JavaImport,
    JavaResolver,
    TargetRepo,
    _read_gradle_includes,
    _read_pom_modules,
    parse_import_statement,
)

# ---------------------------------------------------------------------------
# parse_import_statement
# ---------------------------------------------------------------------------


def test_parse_import_simple() -> None:
    """``import com.example.a.Util;`` -> qualified='com.example.a.Util'."""
    parsed = parse_import_statement("import com.example.a.Util;")
    assert parsed == JavaImport(
        qualified="com.example.a.Util",
        package="com.example.a",
        class_name="Util",
    )


def test_parse_import_static() -> None:
    """``import static com.example.a.Util.foo;`` keeps full qualified path.

    The ``static`` modifier targets a member symbol, but the resolver
    treats the trailing identifier as the symbol regardless — so
    ``foo`` becomes the class_name (which is fine; the caller uses it
    purely as the qualified-name suffix).
    """
    parsed = parse_import_statement("import static com.example.a.Util.foo;")
    assert parsed == JavaImport(
        qualified="com.example.a.Util.foo",
        package="com.example.a.Util",
        class_name="foo",
    )


def test_parse_import_no_dot() -> None:
    """``import Util;`` (no package) returns None.

    A bare ``import Util;`` is not legal Java in any case, but more
    importantly the resolver needs at least one ``.`` to split package
    from class — without it the lookup is undefined, so we bail early.
    """
    assert parse_import_statement("import Util;") is None


def test_parse_import_garbage() -> None:
    """Non-import lines (declarations, comments, blanks) return None."""
    assert parse_import_statement("public class Foo {}") is None
    assert parse_import_statement("") is None
    assert parse_import_statement("    ") is None
    assert parse_import_statement("// import com.example.a.Util;") is None
    assert parse_import_statement("package com.example.a;") is None


def test_parse_import_without_semicolon() -> None:
    """``import com.example.a.Util`` (semicolon stripped by caller) still parses."""
    parsed = parse_import_statement("import com.example.a.Util")
    assert parsed == JavaImport(
        qualified="com.example.a.Util",
        package="com.example.a",
        class_name="Util",
    )


# ---------------------------------------------------------------------------
# _read_pom_modules
# ---------------------------------------------------------------------------


def test_read_pom_modules_with_namespace(tmp_path: Path) -> None:
    """POM with ``xmlns="http://maven.apache.org/POM/4.0.0"`` parses correctly."""
    pom = tmp_path / "pom.xml"
    pom.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>module-a</module>
        <module>module-b</module>
    </modules>
</project>
""",
        encoding="utf-8",
    )
    assert _read_pom_modules(pom) == ["module-a", "module-b"]


def test_read_pom_modules_no_namespace(tmp_path: Path) -> None:
    """POM without an ``xmlns`` declaration also parses (some legacy POMs).

    ElementTree treats an undeclared default namespace as no namespace,
    so the resolver must fall back to the unqualified XPath when the
    namespaced query yields nothing.
    """
    pom = tmp_path / "pom.xml"
    pom.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>module-a</module>
        <module>module-b</module>
    </modules>
</project>
""",
        encoding="utf-8",
    )
    assert _read_pom_modules(pom) == ["module-a", "module-b"]


def test_read_pom_modules_missing_file(tmp_path: Path) -> None:
    """Missing pom.xml -> empty list, no exception."""
    assert _read_pom_modules(tmp_path / "nope.xml") == []


def test_read_pom_modules_malformed_xml(tmp_path: Path) -> None:
    """Unparseable XML -> empty list, no exception."""
    pom = tmp_path / "pom.xml"
    pom.write_text("<project><modules<<<", encoding="utf-8")
    assert _read_pom_modules(pom) == []


def test_read_pom_modules_no_modules_section(tmp_path: Path) -> None:
    """POM without ``<modules>`` yields empty list."""
    pom = tmp_path / "pom.xml"
    pom.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>singleton</artifactId>
    <version>1.0.0</version>
</project>
""",
        encoding="utf-8",
    )
    assert _read_pom_modules(pom) == []


def test_read_pom_modules_skips_empty_module_text(tmp_path: Path) -> None:
    """``<module></module>`` (no text) entries are skipped silently.

    Pins the ``if m.text`` guard inside the loop: an empty self-closing
    or text-less ``<module/>`` element should not produce a stray entry.
    """
    pom = tmp_path / "pom.xml"
    pom.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <modules>
        <module>module-a</module>
        <module/>
    </modules>
</project>
""",
        encoding="utf-8",
    )
    assert _read_pom_modules(pom) == ["module-a"]


# ---------------------------------------------------------------------------
# _read_gradle_includes
# ---------------------------------------------------------------------------


def test_read_gradle_includes_groovy_form(tmp_path: Path) -> None:
    """Groovy DSL: ``include 'a', 'b'`` and ``include(':c')`` both extracted."""
    settings = tmp_path / "settings.gradle"
    settings.write_text(
        """rootProject.name = 'demo'
include 'app'
include 'lib'
include(':sub')
""",
        encoding="utf-8",
    )
    # Order is regex match order through the file.
    assert _read_gradle_includes(settings) == ["app", "lib", "sub"]


def test_read_gradle_includes_kotlin_form(tmp_path: Path) -> None:
    """Kotlin DSL: ``include(":app", ":lib")`` and ``include(":sub")`` extracted.

    The regex iterates per-name so a single ``include(":app", ":lib")``
    yields two entries (one per quoted token).
    """
    settings = tmp_path / "settings.gradle.kts"
    settings.write_text(
        """rootProject.name = "demo"
include(":app")
include(":lib")
include(":sub")
""",
        encoding="utf-8",
    )
    assert _read_gradle_includes(settings) == ["app", "lib", "sub"]


def test_read_gradle_includes_nested_path(tmp_path: Path) -> None:
    """``include ':a:b'`` (nested project) -> 'a/b' (Gradle ``:`` -> FS ``/``)."""
    settings = tmp_path / "settings.gradle"
    settings.write_text(
        """include ':parent:child'
""",
        encoding="utf-8",
    )
    assert _read_gradle_includes(settings) == ["parent/child"]


def test_read_gradle_includes_missing_file(tmp_path: Path) -> None:
    """Missing settings file -> empty list, no exception."""
    assert _read_gradle_includes(tmp_path / "settings.gradle") == []


def test_read_gradle_includes_no_include_lines(tmp_path: Path) -> None:
    """settings.gradle without any ``include`` -> empty list."""
    settings = tmp_path / "settings.gradle"
    settings.write_text("rootProject.name = 'demo'\n", encoding="utf-8")
    assert _read_gradle_includes(settings) == []


# ---------------------------------------------------------------------------
# JavaResolver.resolve — fixtures + integration
# ---------------------------------------------------------------------------


def _build_maven_multimodule_repo(tmp_path: Path) -> Path:
    """Build ``repo_a`` parent POM with module ``module-a`` containing Util.java.

    Returns ``repo_a`` root.
    """
    repo_a = tmp_path / "repo_a"
    module_a_src = (
        repo_a / "module-a" / "src" / "main" / "java" / "com" / "example" / "a"
    )
    module_a_src.mkdir(parents=True)
    (repo_a / "pom.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>module-a</module>
    </modules>
</project>
""",
        encoding="utf-8",
    )
    (repo_a / "module-a" / "pom.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>parent</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>module-a</artifactId>
</project>
""",
        encoding="utf-8",
    )
    (module_a_src / "Util.java").write_text(
        """package com.example.a;

public class Util {
    public static void doThing() {}
}
""",
        encoding="utf-8",
    )
    return repo_a


def _build_minimal_source_repo(tmp_path: Path, name: str = "repo_b") -> Path:
    """Build a minimal source repo (no pom.xml, no settings.gradle).

    Used as the *importing* repo for tests focused on target-side
    resolution logic; the source's own module map is irrelevant.
    """
    repo = tmp_path / name
    repo.mkdir()
    return repo


def test_resolver_finds_via_maven_modules(tmp_path: Path) -> None:
    """The plan-required Maven multi-module fixture (test 12).

    repo_a is a Maven multi-module project: parent ``pom.xml`` with
    ``<modules><module>module-a</module></modules>``; the child module
    contains ``module-a/src/main/java/com/example/a/Util.java``.

    Resolving ``import com.example.a.Util;`` against repo_a should
    yield ``repo_a_id:module-a/src/main/java/com/example/a/Util.java::Util``.
    """
    repo_a = _build_maven_multimodule_repo(tmp_path)
    repo_b = _build_minimal_source_repo(tmp_path)

    resolver = JavaResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import com.example.a.Util;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:module-a/src/main/java/com/example/a/Util.java::Util"


def test_resolver_finds_via_gradle_settings(tmp_path: Path) -> None:
    """``settings.gradle`` with ``include ':app'`` + Foo.java resolves."""
    repo_a = tmp_path / "repo_a"
    app_src = repo_a / "app" / "src" / "main" / "java" / "com" / "example"
    app_src.mkdir(parents=True)
    (repo_a / "settings.gradle").write_text(
        """rootProject.name = 'demo'
include ':app'
""",
        encoding="utf-8",
    )
    (app_src / "Foo.java").write_text(
        """package com.example;

public class Foo {}
""",
        encoding="utf-8",
    )
    repo_b = _build_minimal_source_repo(tmp_path)

    resolver = JavaResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import com.example.Foo;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:app/src/main/java/com/example/Foo.java::Foo"


def test_resolver_finds_via_gradle_kts_settings(tmp_path: Path) -> None:
    """``settings.gradle.kts`` with ``include(":app")`` resolves identically.

    Pins the kts-before-groovy probe order: when only the ``.kts`` file
    exists the resolver still picks it up.
    """
    repo_a = tmp_path / "repo_a"
    app_src = repo_a / "app" / "src" / "main" / "java" / "com" / "example"
    app_src.mkdir(parents=True)
    (repo_a / "settings.gradle.kts").write_text(
        """rootProject.name = "demo"
include(":app")
""",
        encoding="utf-8",
    )
    (app_src / "Foo.java").write_text(
        """package com.example;

public class Foo {}
""",
        encoding="utf-8",
    )
    repo_b = _build_minimal_source_repo(tmp_path)

    resolver = JavaResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import com.example.Foo;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:app/src/main/java/com/example/Foo.java::Foo"


def test_resolver_finds_kotlin_file(tmp_path: Path) -> None:
    """Class lives in ``src/main/kotlin/...Bar.kt`` -> resolves with ``.kt``.

    Many Java multi-module projects mix Kotlin sources; the resolver
    walks ``src/main/kotlin`` alongside ``src/main/java`` and emits the
    matching ``.kt`` path verbatim.
    """
    repo_a = tmp_path / "repo_a"
    kotlin_src = repo_a / "module" / "src" / "main" / "kotlin" / "com" / "example"
    kotlin_src.mkdir(parents=True)
    (repo_a / "pom.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>module</module>
    </modules>
</project>
""",
        encoding="utf-8",
    )
    (kotlin_src / "Bar.kt").write_text(
        """package com.example

class Bar
""",
        encoding="utf-8",
    )
    repo_b = _build_minimal_source_repo(tmp_path)

    resolver = JavaResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import com.example.Bar;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:module/src/main/kotlin/com/example/Bar.kt::Bar"


def test_resolver_skips_self_repo(tmp_path: Path) -> None:
    """A target sharing source's repo_id is skipped."""
    repo_a = _build_maven_multimodule_repo(tmp_path)
    repo_b = _build_minimal_source_repo(tmp_path)

    resolver = JavaResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_a_id",  # same as target
    )
    qualified = resolver.resolve(
        "import com.example.a.Util;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_returns_none_when_no_match(tmp_path: Path) -> None:
    """No matching .java / .kt file under any target module -> None."""
    repo_a = tmp_path / "repo_a"
    # Module exists but the requested package/class isn't there.
    module_src = repo_a / "module-a" / "src" / "main" / "java" / "com" / "other"
    module_src.mkdir(parents=True)
    (repo_a / "pom.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>module-a</module>
    </modules>
</project>
""",
        encoding="utf-8",
    )
    (module_src / "Other.java").write_text(
        "package com.other; public class Other {}\n",
        encoding="utf-8",
    )
    repo_b = _build_minimal_source_repo(tmp_path)

    resolver = JavaResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import com.example.a.Util;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_single_module_project_uses_root(tmp_path: Path) -> None:
    """Repo with no ``<modules>`` and no ``settings.gradle`` walks target_root.

    Pins the single-module fallback: a flat repo with just
    ``src/main/java/<pkg>/<Class>.java`` (no parent-pom modules, no
    Gradle settings) should still resolve by treating the target root
    itself as the lone module directory.
    """
    repo_a = tmp_path / "repo_a"
    src = repo_a / "src" / "main" / "java" / "com" / "example"
    src.mkdir(parents=True)
    # No pom.xml with <modules> and no settings.gradle.
    (src / "Single.java").write_text(
        """package com.example;

public class Single {}
""",
        encoding="utf-8",
    )
    repo_b = _build_minimal_source_repo(tmp_path)

    resolver = JavaResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import com.example.Single;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:src/main/java/com/example/Single.java::Single"


def test_resolver_returns_none_for_garbage_import(tmp_path: Path) -> None:
    """Unparseable import line -> None even with valid targets."""
    repo_a = _build_maven_multimodule_repo(tmp_path)
    repo_b = _build_minimal_source_repo(tmp_path)

    resolver = JavaResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "public class Foo {}",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified is None


def test_resolver_source_repo_reads_its_own_pom_and_gradle(
    tmp_path: Path,
) -> None:
    """Constructor populates source's module map (used by parser layer).

    Pins the constructor-time read paths even though :meth:`resolve`
    itself doesn't consume them: the parser stage may inspect
    ``_maven_modules`` / ``_gradle_modules`` for source-side
    same-repo module disambiguation.
    """
    src_repo = tmp_path / "src_repo"
    src_repo.mkdir()
    (src_repo / "pom.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <modules>
        <module>core</module>
    </modules>
</project>
""",
        encoding="utf-8",
    )
    resolver = JavaResolver(
        source_repo_root=src_repo,
        source_repo_id="src_id",
    )
    # Internal state — pin the constructor pathway.
    assert resolver._maven_modules == ["core"]  # noqa: SLF001
    assert resolver._gradle_modules == []  # noqa: SLF001


def test_resolver_source_repo_reads_settings_gradle_when_no_pom(
    tmp_path: Path,
) -> None:
    """Constructor falls through to settings.gradle when pom.xml absent."""
    src_repo = tmp_path / "src_repo"
    src_repo.mkdir()
    (src_repo / "settings.gradle").write_text(
        "include ':app'\ninclude ':lib'\n",
        encoding="utf-8",
    )
    resolver = JavaResolver(
        source_repo_root=src_repo,
        source_repo_id="src_id",
    )
    assert resolver._maven_modules == []  # noqa: SLF001
    assert resolver._gradle_modules == ["app", "lib"]  # noqa: SLF001


def test_resolver_target_uses_gradle_kts_when_no_pom(tmp_path: Path) -> None:
    """Target repo with only ``settings.gradle.kts`` resolves correctly.

    Pins the target-side fallback chain: when ``pom.xml`` is missing
    and ``settings.gradle`` is also missing, the resolver should pick
    up ``settings.gradle.kts``.
    """
    repo_a = tmp_path / "repo_a"
    app_src = repo_a / "app" / "src" / "main" / "java" / "com" / "example"
    app_src.mkdir(parents=True)
    (repo_a / "settings.gradle.kts").write_text(
        """rootProject.name = "demo"
include(":app")
""",
        encoding="utf-8",
    )
    (app_src / "Baz.java").write_text(
        "package com.example; public class Baz {}\n",
        encoding="utf-8",
    )
    repo_b = _build_minimal_source_repo(tmp_path)

    resolver = JavaResolver(
        source_repo_root=repo_b,
        source_repo_id="repo_b_id",
    )
    qualified = resolver.resolve(
        "import com.example.Baz;",
        targets=[TargetRepo(repo_id="repo_a_id", root=repo_a)],
    )
    assert qualified == "repo_a_id:app/src/main/java/com/example/Baz.java::Baz"
