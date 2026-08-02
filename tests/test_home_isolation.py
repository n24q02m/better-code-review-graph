"""Guard: the test session must never touch the real home directory.

``conftest._isolate_per_plugin_home`` redirects ``HOME`` / ``USERPROFILE`` so
``PerPluginStore`` (and anything else resolving ``Path.home()``) writes into a
tmp dir. These tests fail loudly if that fixture is ever removed, renamed, or
stops being ``autouse``, instead of the failure showing up as mysterious
credential files appearing in a developer's home directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import tree_sitter_language_pack as tslp
from mcp_core.storage.per_plugin_store import PerPluginStore

from better_code_review_graph.credential_state import PLUGIN_NAME
from better_code_review_graph.parser import CodeParser

from .conftest import REAL_HOME

_FIXTURE_HINT = (
    "conftest._isolate_per_plugin_home is not in force -- tests are running "
    "against the real home directory and will read/write the developer's "
    "live credential store."
)


def test_path_home_is_redirected_away_from_the_real_home() -> None:
    """``Path.home()`` inside a test must not be the real home."""
    assert Path.home() != REAL_HOME, _FIXTURE_HINT


def test_home_env_vars_point_at_the_isolated_home() -> None:
    """Both POSIX ``HOME`` and Windows ``USERPROFILE`` must be redirected.

    Setting only one of them silently leaves the other platform unprotected,
    so assert on both regardless of which one this platform's
    ``Path.home()`` actually consults.
    """
    assert Path(os.environ["HOME"]) != REAL_HOME, _FIXTURE_HINT
    assert Path(os.environ["USERPROFILE"]) != REAL_HOME, _FIXTURE_HINT
    assert os.environ["HOME"] == str(Path.home()), _FIXTURE_HINT
    assert os.environ["USERPROFILE"] == str(Path.home()), _FIXTURE_HINT


def test_per_plugin_store_writes_land_outside_the_real_home() -> None:
    """A real ``PerPluginStore.save()`` must not write into the real home.

    The guard assertions run *before* ``save()`` so that a broken fixture can
    never cause this test itself to pollute the real home.
    """
    real_leak_target = REAL_HOME / f".{PLUGIN_NAME}-mcp"
    assert Path.home() != REAL_HOME, _FIXTURE_HINT

    store = PerPluginStore(PLUGIN_NAME)
    assert store.cred_path.parent != real_leak_target, _FIXTURE_HINT

    store.save({"GEMINI_API_KEY": "home-isolation-guard-value"})

    assert store.cred_path.exists()
    assert store.cred_path.parent.parent == Path.home()
    assert store.load() == {"GEMINI_API_KEY": "home-isolation-guard-value"}


def test_isolated_home_is_empty_per_test() -> None:
    """Each test gets a fresh home, so no state leaks between tests.

    ``test_per_plugin_store_writes_land_outside_the_real_home`` saves a
    credential store; if the fixture were session-scoped that store would
    still be visible here.
    """
    assert Path.home() != REAL_HOME, _FIXTURE_HINT
    assert not (Path.home() / f".{PLUGIN_NAME}-mcp").exists()
    assert PerPluginStore(PLUGIN_NAME).load() is None


def test_tree_sitter_grammar_cache_survives_the_isolated_home() -> None:
    """Redirecting HOME must not drag the tree-sitter grammar cache with it.

    ``tree_sitter_language_pack`` resolves its grammar cache from the
    environment (``$HOME`` / ``$XDG_CACHE_HOME`` on Linux, ``LOCALAPPDATA``
    on Windows) and memoises the result on first use. If the first resolution
    happens inside a test, it lands in that test's empty tmp home and grammar
    loading fails. That used to be invisible: ``CodeParser._get_parser``
    swallowed the error and returned ``None``, ``parse_bytes`` yielded an
    empty result, and the suite parsed zero nodes everywhere instead of
    erroring. A supported language whose grammar will not load now raises
    ``GrammarUnavailableError``, so the same breakage reports itself.

    ``conftest._pin_tree_sitter_grammar_cache`` is still what keeps the
    grammars reachable: it forces that first resolution to happen at session
    start, with the real environment still in place. ``cache_dir()`` raises
    outright when unresolvable, so this asserts both that it resolves and
    that it did not follow the redirect. The parse below then confirms the
    grammars genuinely load, rather than trusting the path check alone.
    """
    assert Path.home() != REAL_HOME, _FIXTURE_HINT

    cache = Path(tslp.cache_dir())
    assert not cache.is_relative_to(Path.home()), (
        f"tree-sitter grammar cache followed the isolated home ({cache}) -- "
        "see conftest._pin_tree_sitter_grammar_cache"
    )

    nodes, _edges = CodeParser().parse_bytes(
        Path("sample.py"), b"def outer():\n    return 1\n"
    )
    assert [n for n in nodes if n.kind == "Function"], (
        "tree-sitter returned no Function nodes -- grammar loading is broken "
        "under the isolated HOME (see conftest._pin_tree_sitter_grammar_cache)"
    )
