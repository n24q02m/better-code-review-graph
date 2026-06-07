"""Tier-2 Semgrep security scanner (opt-in).

Wraps the Semgrep CLI (``semgrep --config p/auto --json``) to surface
the curated OWASP-style ruleset. Available only when the package is
installed with the ``[security]`` extra::

    uv add 'better-code-review-graph[security]'

Without the extra, importing this module is safe; the engine raises
:class:`SemgrepNotAvailable` when instantiated. Heuristic Tier-1
scanning (``HeuristicScanner``) remains fully functional regardless.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .heuristic import Tag

_SEMGREP_DEFAULT_CONFIG = "p/auto"


class SemgrepNotAvailable(RuntimeError):
    """Raised when semgrep is not installed, not on PATH, or fails to run."""


@dataclass(frozen=True)
class SemgrepResult:
    """Aggregated Semgrep scan result.

    ``tags`` is a flat list of :class:`Tag` objects (one per finding);
    ``raw_output`` preserves the full ``--json`` stdout so callers that
    need the structured Semgrep schema (file path, position spans, fix
    suggestions, ...) can parse it themselves.
    """

    tags: list[Tag]
    raw_output: str


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def _semgrep_executable() -> str:
    """Find the semgrep executable."""
    import shutil

    path = shutil.which("semgrep")
    if path:
        return path
    return "semgrep"


def _semgrep_python_module_available() -> bool:
    """Return ``True`` if the ``semgrep`` Python module is importable."""

    try:
        import semgrep  # noqa: F401
    except ImportError:
        return False
    return True


def _resolve_overlay_rules_dir() -> Path | None:
    """Return path to the bundled ``rules/semgrep/`` overlay, if present.

    First tries the wheel-installed location (top-level package
    ``better_code_review_graph_security_rules`` populated by the
    ``[tool.hatch.build.targets.wheel.force-include]`` mapping), then
    falls back to the repository checkout layout used during ``uv sync``.
    """

    try:
        ref = files("better_code_review_graph_security_rules") / "semgrep"
        path = Path(str(ref))
        if path.is_dir():
            return path
    except (ModuleNotFoundError, OSError):
        pass
    fallback = (
        Path(__file__).resolve().parent.parent.parent.parent / "rules" / "semgrep"
    )
    if fallback.is_dir():
        return fallback
    return None


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class SemgrepScanner:
    """Tier-2 Semgrep wrapper.

    Args:
        config: Semgrep ruleset to use. Defaults to ``p/auto`` (Semgrep's
            curated meta-pack). Can be a local rules dir, a registry URL,
            or a path to a single YAML file.
        executable: Override path to the ``semgrep`` binary. Defaults to
            ``shutil.which("semgrep")``.
        require_python_module: When ``True``, also requires that the
            ``semgrep`` Python module be importable. Defaults to ``False``
            (CLI-only check).

    Raises:
        SemgrepNotAvailable: If neither the CLI (always) nor the Python
            module (when ``require_python_module=True``) is available.
    """

    def __init__(
        self,
        config: str | Path = _SEMGREP_DEFAULT_CONFIG,
        executable: str | None = None,
        require_python_module: bool = False,
    ) -> None:
        self._config = str(config)
        if executable:
            self._executable = executable
        else:
            resolved = _semgrep_executable()
            if shutil.which(resolved) is None:
                raise SemgrepNotAvailable(
                    "semgrep CLI not found on PATH. Install with: "
                    "uv add 'better-code-review-graph[security]'"
                )
            self._executable = resolved

        if require_python_module:
            if not _semgrep_python_module_available():
                raise SemgrepNotAvailable(
                    "semgrep Python module not importable. Install with: "
                    "uv add 'better-code-review-graph[security]'"
                )

    def scan_path(
        self,
        target: Path,
        *,
        timeout: float = 300.0,
    ) -> SemgrepResult:
        """Run ``semgrep --config <config> --json <target>`` and parse output.

        Args:
            target: File or directory to scan.
            timeout: Maximum seconds to wait for ``semgrep`` to complete.

        Returns:
            A :class:`SemgrepResult` with one :class:`Tag` per finding plus
            the raw ``--json`` stdout for callers needing the full Semgrep
            schema.

        Raises:
            SemgrepNotAvailable: If ``semgrep`` exits with a code greater
                than ``1`` (``0`` = no findings, ``1`` = findings present
                are both treated as success), or if the JSON output cannot
                be parsed.
            subprocess.TimeoutExpired: If the scan exceeds ``timeout``.
        """

        cmd = [
            self._executable,
            "--config",
            self._config,
            "--json",
            "--quiet",
            str(target),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        # Semgrep exit codes: 0 = no findings, 1 = findings, >1 = error.
        if proc.returncode > 1:
            raise SemgrepNotAvailable(
                f"semgrep exited with code {proc.returncode}: {proc.stderr.strip()}"
            )
        try:
            data = json.loads(proc.stdout) if proc.stdout else {"results": []}
        except json.JSONDecodeError as exc:
            raise SemgrepNotAvailable(
                f"semgrep JSON output parse failed: {exc}"
            ) from exc
        tags = _parse_semgrep_findings(data.get("results", []))
        return SemgrepResult(tags=tags, raw_output=proc.stdout)


# ---------------------------------------------------------------------------
# Finding -> Tag translation
# ---------------------------------------------------------------------------


_SEMGREP_TO_CRG_SEVERITY = {"INFO": "LOW", "WARNING": "MEDIUM", "ERROR": "HIGH"}


def _parse_semgrep_findings(findings: list[dict]) -> list[Tag]:
    """Translate semgrep ``--json`` result entries into :class:`Tag` objects."""

    out: list[Tag] = []
    for finding in findings:
        rule_id = str(finding.get("check_id") or "semgrep-rule")
        extra = finding.get("extra") or {}
        if not isinstance(extra, dict):
            extra = {}
        severity_raw = str(extra.get("severity") or "MEDIUM").upper()
        severity = _SEMGREP_TO_CRG_SEVERITY.get(severity_raw, severity_raw)
        message = str(extra.get("message") or "")
        start = finding.get("start")
        line = start.get("line") if isinstance(start, dict) else None
        out.append(
            Tag(
                rule_id=rule_id,
                severity=severity,
                message=message,
                line=line if isinstance(line, int) else None,
            )
        )
    return out
