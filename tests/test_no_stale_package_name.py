"""Không còn tham chiếu tới tên package cũ ngoài lịch sử CHANGELOG."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"CHANGELOG.md"}
IGNORED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "build",
    "dist",
    "__pycache__",
}


def _worktree_hits(pattern: str) -> list[str]:
    """Scan tracked and untracked text files in the current worktree."""
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if path.name in ALLOWED or any(
            part in IGNORED_DIRECTORIES for part in relative.parts
        ):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        hits.extend(
            f"{relative}:{line_number}:{line}"
            for line_number, line in enumerate(lines, start=1)
            if pattern in line
        )
    return hits


def _legacy_module_name() -> str:
    return "qwen3_" + "embed"


def _legacy_distribution_name() -> str:
    return "qwen3-" + "embed"


def test_no_module_reference_remains():
    hits = _worktree_hits(_legacy_module_name())
    assert not hits, "stale module name:\n" + "\n".join(hits)


def test_no_distribution_reference_remains():
    hits = _worktree_hits(_legacy_distribution_name())
    assert not hits, "stale distribution name:\n" + "\n".join(hits)
