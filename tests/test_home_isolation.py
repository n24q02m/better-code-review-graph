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

from mcp_core.storage.per_plugin_store import PerPluginStore

from better_code_review_graph.credential_state import PLUGIN_NAME

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
