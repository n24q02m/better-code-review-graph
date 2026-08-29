"""Tier-1 heuristic security scanner.

Loads YAML rule definitions from ``rules/heuristic/*.yaml`` and matches each
rule's regex pattern against node source text. Returns :class:`Tag` objects
with rule id, severity, message, and an approximate source line.

The YAML loader implements a tiny purpose-built subset of YAML so that this
module has no runtime dependency on PyYAML; rule files only use simple
top-level scalar fields plus inline lists, which is sufficient for the
v2.0 ruleset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tag:
    """A security finding on a node."""

    rule_id: str  # e.g. ``cwe-89-sql-string-format``
    severity: str  # ``LOW`` | ``MEDIUM`` | ``HIGH`` | ``CRITICAL``
    message: str  # human-readable description
    line: int | None  # approximate source line of the match


@dataclass(frozen=True)
class HeuristicRule:
    """A loaded YAML rule definition."""

    id: str
    severity: str
    pattern: re.Pattern[str]
    languages: frozenset[str]  # empty set = applies to all languages
    message: str


@dataclass(frozen=True)
class ScanResult:
    """Aggregated result of scanning a set of nodes."""

    tags_by_node: dict[str, list[Tag]]  # node identifier -> list of tags
    total: int
    by_severity: dict[str, int]


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse a tiny subset of YAML used by heuristic rule files.

    Supported syntax:

    - ``id: value`` -- top-level scalar fields
    - ``severity: LOW`` -- bare scalars
    - ``pattern: 'regex'`` / ``pattern: "regex"`` -- quoted scalars
    - ``languages: [a, b, c]`` / ``languages: []`` -- inline lists
    - ``# comment`` -- inline and full-line comments are stripped

    Multi-line block scalars (``|`` / ``>``) are intentionally NOT supported.
    """

    result: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Handle comments, but only if they are not inside quotes
        if "#" in line:
            in_single_quote = False
            in_double_quote = False
            hash_idx = -1
            for i, char in enumerate(line):
                if char == "'" and not in_double_quote:
                    in_single_quote = not in_single_quote
                elif char == '"' and not in_single_quote:
                    in_double_quote = not in_double_quote
                elif char == "#" and not in_single_quote and not in_double_quote:
                    hash_idx = i
                    break

            if hash_idx != -1:
                line = line[:hash_idx].rstrip()

        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if inner:
                result[key] = [v.strip().strip("'\"") for v in inner.split(",")]
            else:
                result[key] = []
        elif len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
            result[key] = value[1:-1]
        else:
            result[key] = value
    return result


def _load_rules_from_dir(rules_dir: Path) -> list[HeuristicRule]:
    """Load every ``*.yaml`` file in ``rules_dir`` as a :class:`HeuristicRule`.

    Files that are unreadable, malformed, missing required fields, or contain
    an invalid regex are silently skipped so that one bad rule does not
    disable the whole scanner.
    """

    if not rules_dir.is_dir():
        return []
    rules: list[HeuristicRule] = []
    for path in sorted(rules_dir.glob("*.yaml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        data = _parse_simple_yaml(text)
        rule_id = data.get("id")
        severity = data.get("severity")
        pattern_str = data.get("pattern")
        languages = data.get("languages") or []
        message = data.get("message", "")
        if not (rule_id and severity and pattern_str):
            continue
        try:
            pattern = re.compile(str(pattern_str), re.DOTALL | re.MULTILINE)
        except re.error:
            continue
        if isinstance(languages, str):
            language_iter: Iterable[str] = [languages]
        else:
            language_iter = languages
        rules.append(
            HeuristicRule(
                id=str(rule_id),
                severity=str(severity).upper(),
                pattern=pattern,
                languages=frozenset(
                    str(language).lower() for language in language_iter
                ),
                message=str(message),
            )
        )
    return rules


def _default_rules_dir() -> Path:
    """Locate the bundled rules directory.

    First tries the wheel-installed location (top-level package
    ``better_code_review_graph_security_rules`` populated by the
    ``[tool.hatch.build.targets.wheel.force-include]`` mapping), then falls
    back to the repository checkout layout used during ``uv sync``.
    """

    try:
        ref = files("better_code_review_graph_security_rules").joinpath("heuristic")
        if isinstance(ref, Path) and ref.joinpath("hardcoded-secret.yaml").is_file():
            return ref
    except (ModuleNotFoundError, OSError):
        pass
    return Path(__file__).resolve().parent.parent.parent.parent / "rules" / "heuristic"


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class HeuristicScanner:
    """Tier-1 regex-based security scanner.

    Construct with no arguments to use the bundled rule set, with
    ``rules_dir=`` to load from a custom directory, or with ``rules=`` to
    inject an explicit rule list (primarily for tests).
    """

    def __init__(
        self,
        rules: list[HeuristicRule] | None = None,
        rules_dir: Path | None = None,
    ) -> None:
        if rules is not None:
            self._rules = rules
        elif rules_dir is not None:
            self._rules = _load_rules_from_dir(rules_dir)
        else:
            self._rules = _load_rules_from_dir(_default_rules_dir())

    def scan_node(self, node: object) -> list[Tag]:
        """Run all applicable rules against ``node.source_text``.

        ``node`` is duck-typed: it must expose ``source_text`` (``str | None``),
        ``language`` (``str``), and ``line_start`` (``int | None``) attributes.
        :class:`better_code_review_graph.parser.NodeInfo` satisfies this
        contract.
        """

        source = getattr(node, "source_text", "") or ""
        if not source:
            return []
        node_lang = (getattr(node, "language", "") or "").lower()
        line_start = getattr(node, "line_start", None) or 0
        out: list[Tag] = []
        for rule in self._rules:
            if rule.languages and node_lang not in rule.languages:
                continue
            for match in rule.pattern.finditer(source):
                line_offset = source.count("\n", 0, match.start())
                line = line_start + line_offset
                out.append(
                    Tag(
                        rule_id=rule.id,
                        severity=rule.severity,
                        message=rule.message,
                        line=line if line >= 0 else None,
                    )
                )
        return out

    def scan_nodes(self, nodes: Iterable[object]) -> ScanResult:
        """Scan an iterable of nodes and aggregate the findings."""

        tags_by_node: dict[str, list[Tag]] = {}
        total = 0
        by_severity: dict[str, int] = {}
        for node in nodes:
            tags = self.scan_node(node)
            if not tags:
                continue
            key = getattr(node, "qualified_name", "") or getattr(node, "name", "") or ""
            tags_by_node[key] = tags
            total += len(tags)
            for tag in tags:
                by_severity[tag.severity] = by_severity.get(tag.severity, 0) + 1
        return ScanResult(
            tags_by_node=tags_by_node, total=total, by_severity=by_severity
        )
