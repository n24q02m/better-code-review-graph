from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from better_code_review_graph.resolver.typescript import (
    _expand_alias,
    _read_tsconfig_paths,
    _read_workspaces,
)


def test_read_tsconfig_paths_oserror(tmp_path: Path) -> None:
    """OSError during read_text should be caught and return empty dict."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text("{}", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=OSError("Disk failure")):
        paths = _read_tsconfig_paths(tsconfig)
    assert paths == {}


def test_read_workspaces_oserror(tmp_path: Path) -> None:
    """OSError during read_text should be caught and return empty list."""
    pkg = tmp_path / "package.json"
    pkg.write_text("{}", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=OSError("Disk failure")):
        assert _read_workspaces(pkg) == []


def test_read_tsconfig_paths_unsupported_target_type(tmp_path: Path) -> None:
    """If target is neither string nor list, it should be ignored (covers branch 124->120)."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(
        '{"compilerOptions": {"paths": {"@/*": 123}}}', encoding="utf-8"
    )
    paths = _read_tsconfig_paths(tsconfig)
    assert paths == {}


def test_expand_alias_no_match_not_glob(tmp_path: Path) -> None:
    """Alias that is not a glob and does not match exactly (covers branch 174->164)."""
    paths = {"@/other": ["packages/other"]}
    candidates = _expand_alias("@/foo", paths)
    # Since no alias matches, it returns the module itself.
    assert candidates == ["@/foo"]


def test_read_tsconfig_paths_list_target(tmp_path: Path) -> None:
    """Ensure list target hits the branch at 124."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(
        '{"compilerOptions": {"paths": {"@/*": ["src/*"]}}}', encoding="utf-8"
    )
    paths = _read_tsconfig_paths(tsconfig)
    assert paths == {"@/*": ["src/*"]}
