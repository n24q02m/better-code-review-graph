"""Security scanning (Phase 3 v2.0).

Two-tier security engine:
- Tier 1 (heuristic): regex/AST patterns -- always available, ~50 rules.
- Tier 2 (semgrep): wrapper around semgrep CLI -- opt-in via [security] extra.
"""

from .heuristic import HeuristicScanner, ScanResult, Tag

__all__ = ["HeuristicScanner", "ScanResult", "Tag"]
