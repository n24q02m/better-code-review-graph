"""Shared types for cross-repo resolvers (Phase 2 Task 8).

The :class:`TargetRepo` dataclass was originally duplicated across each
language resolver module. Task 8 consolidates it here so the dispatcher
in :mod:`better_code_review_graph.resolver` and every language module
share the exact same type. Each language module re-exports the symbol
to preserve backwards compatibility for callers importing
``TargetRepo`` directly from a specific resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TargetRepo:
    """Per-target descriptor: ``repo_id`` plus its filesystem root."""

    repo_id: str
    root: Path
