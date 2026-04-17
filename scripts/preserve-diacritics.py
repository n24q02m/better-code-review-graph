#!/usr/bin/env python3
"""Pre-commit hook: prevent ASCII rewriting of Vietnamese diacritics + Unicode punctuation.

Blocks commits that replace:
  1. Unicode punctuation (em-dash, ellipsis, arrows, smart quotes) with ASCII equivalents.
  2. Vietnamese diacritics with bare vowels (NFD-strip or transliteration).
  3. Emoji characters removed or replaced with ASCII labels.

Rationale: Jules/Sentinel style AI PRs frequently "normalize" non-ASCII text, which
silently damages Vietnamese content + typography. Rule: feedback_vietnamese_diacritics.

Pure additions of diacritics / Unicode punctuation (progress) always PASS.
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

# Force UTF-8 on stderr so Vietnamese / Unicode chars display correctly on
# Windows (default cp1252 otherwise replaces non-ASCII chars with '?').
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )

# Unicode char -> candidate ASCII replacements frequently produced by AI rewrites.
UNICODE_REPLACEMENTS: dict[str, list[str]] = {
    "\u2014": ["---", "--", "-"],  # em-dash
    "\u2013": ["--", "-"],  # en-dash
    "\u2026": ["..."],  # horizontal ellipsis
    "\u2192": ["->"],  # rightwards arrow
    "\u2190": ["<-"],  # leftwards arrow
    "\u21d2": ["=>"],  # rightwards double arrow
    "\u21d0": ["<="],  # leftwards double arrow
    "\u2194": ["<->"],  # left-right arrow
    "\u201c": ['"'],  # left double quote
    "\u201d": ['"'],  # right double quote
    "\u2018": ["'"],  # left single quote
    "\u2019": ["'"],  # right single quote / apostrophe
    "\u00d7": ["x", "*"],  # multiplication sign
    "\u2713": ["v", "[x]", "[v]"],  # check mark
    "\u2717": ["x", "[ ]"],  # ballot x
    "\u00b7": ["*", "."],  # middle dot
    "\u2022": ["*", "-"],  # bullet
}

# Vietnamese precomposed letters (NFC). Lowercase + uppercase.
_VN_BASE = "àảãáạâấầẩẫậăắằẳẵặèẻẽéẹêếềểễệìỉĩíịòỏõóọôốồổỗộơớờởỡợùủũúụưứừửữựỳỷỹýỵđ"
VIETNAMESE_DIACRITIC_CHARS: set[str] = set(_VN_BASE + _VN_BASE.upper())

# Emoji detection: any codepoint in common emoji blocks.
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f5ff"  # Misc symbols & pictographs
    "\U0001f600-\U0001f64f"  # Emoticons
    "\U0001f680-\U0001f6ff"  # Transport & map
    "\U0001f700-\U0001f77f"  # Alchemical
    "\U0001f780-\U0001f7ff"  # Geometric shapes extended
    "\U0001f800-\U0001f8ff"  # Supplemental arrows-C
    "\U0001f900-\U0001f9ff"  # Supplemental symbols & pictographs
    "\U0001fa00-\U0001fa6f"  # Chess / symbols
    "\U0001fa70-\U0001faff"  # Symbols & pictographs extended-A
    "\U00002600-\U000026ff"  # Misc symbols
    "\U00002700-\U000027bf"  # Dingbats
    "]",
    flags=re.UNICODE,
)

# Files we deliberately skip (binary-ish or generated).
_SKIP_SUFFIXES = {
    ".lock",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp3",
    ".mp4",
    ".webm",
    ".wasm",
    ".min.js",
    ".min.css",
}
_SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"}


def _is_skippable(path: str) -> bool:
    p = Path(path)
    if any(part in _SKIP_DIRS for part in p.parts):
        return True
    if p.suffix.lower() in _SKIP_SUFFIXES:
        return True
    # Lockfiles
    return p.name in {
        "bun.lockb",
        "bun.lock",
        "package-lock.json",
        "yarn.lock",
        "uv.lock",
        "poetry.lock",
        "Cargo.lock",
        "go.sum",
    }


def _run_git(args: list[str]) -> str:
    """Run git returning UTF-8 decoded stdout. Windows cp1252 default would
    mangle Vietnamese/Unicode — force UTF-8 explicitly."""
    raw = subprocess.check_output(["git", *args])
    return raw.decode("utf-8", errors="replace")


def _staged_files() -> list[str]:
    """Files added or modified in the staged index (no deletions, no renames-only)."""
    out = _run_git(["diff", "--cached", "--name-only", "--diff-filter=AM"])
    return [line for line in out.splitlines() if line]


def _diff_pairs(file_path: str) -> list[tuple[int, str, str]]:
    """Return list of (line_number, removed_line, added_line) pairs.

    Pairs are aligned within the same hunk using position matching: the k-th
    '-' removal is paired with the k-th '+' addition of that hunk. Unpaired
    lines (pure add / pure delete) are skipped — they are definitionally
    not rewrites of existing content.
    """
    try:
        diff = _run_git(["diff", "--cached", "-U0", "--no-color", "--", file_path])
    except subprocess.CalledProcessError:
        return []

    pairs: list[tuple[int, str, str]] = []
    removed: list[str] = []
    added: list[str] = []
    plus_line_no = 0
    hunk_plus_start = 0

    def _flush(start_line: int) -> None:
        # Pair k-th removed with k-th added; any overflow is pure add/delete.
        for idx in range(min(len(removed), len(added))):
            pairs.append((start_line + idx, removed[idx], added[idx]))
        removed.clear()
        added.clear()

    for line in diff.splitlines():
        if line.startswith("@@"):
            _flush(hunk_plus_start)
            m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                hunk_plus_start = int(m.group(1))
                plus_line_no = hunk_plus_start
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
        else:
            # context line (unlikely with -U0) — flush
            _flush(hunk_plus_start)
            plus_line_no += 1
            hunk_plus_start = plus_line_no
    _flush(hunk_plus_start)
    return pairs


def _strip_diacritics(s: str) -> str:
    """Return NFD-stripped lowercase form with đ->d, Đ->D."""
    s = s.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if not unicodedata.combining(c))


def _check_pair(old: str, new: str) -> list[tuple[str, str, str]]:
    """Return list of (rule, old_excerpt, new_excerpt) violations for one pair."""
    violations: list[tuple[str, str, str]] = []

    # Rule 1: Unicode punctuation replaced with ASCII.
    # Strategy: strip ALL tracked unicode punct from `old` and ALL their ASCII
    # forms from `new`; if the resulting skeletons match (similarity), this is
    # a mechanical normalization, not a content rewrite.
    old_skel = old
    new_skel = new
    hit_uni: list[str] = []
    for uni, ascii_forms in UNICODE_REPLACEMENTS.items():
        if uni in old and uni not in new and any(form in new for form in ascii_forms):
            hit_uni.append(uni)
            old_skel = old_skel.replace(uni, "")
            for form in ascii_forms:
                new_skel = new_skel.replace(form, "")
    if hit_uni and _similar(old_skel.strip(), new_skel.strip()):
        for uni in hit_uni:
            violations.append((f"unicode-punct {uni!r}->ascii", old, new))

    # Rule 2: Vietnamese diacritics stripped.
    old_diacritics = [c for c in old if c in VIETNAMESE_DIACRITIC_CHARS]
    new_diacritics = [c for c in new if c in VIETNAMESE_DIACRITIC_CHARS]
    if len(old_diacritics) > len(new_diacritics):
        # Confirm via NFD-strip round-trip: does stripping old give us new?
        old_stripped = _strip_diacritics(old)
        new_lower = new.replace("đ", "d").replace("Đ", "D")
        if old_stripped.strip().lower() == new_lower.strip().lower():
            violations.append(("vietnamese-diacritic-strip", old, new))
        elif (
            _similar(old_stripped, new_lower)
            and len(old_diacritics) - len(new_diacritics) >= 2
        ):
            # Many diacritics vanished but content otherwise similar.
            violations.append(("vietnamese-diacritic-strip", old, new))

    # Rule 3: Emoji removed / replaced.
    old_emoji = _EMOJI_RE.findall(old)
    new_emoji = _EMOJI_RE.findall(new)
    if len(old_emoji) > len(new_emoji):
        # Confirm similarity so that full-paragraph rewrites don't trip it.
        old_no_emoji = _EMOJI_RE.sub("", old).strip()
        new_no_emoji = _EMOJI_RE.sub("", new).strip()
        if _similar(old_no_emoji, new_no_emoji):
            violations.append(("emoji-removed", old, new))

    return violations


def _similar(a: str, b: str) -> bool:
    """Cheap similarity: shared >=70% of the shorter string's characters in order."""
    if not a and not b:
        return True
    if not a or not b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) == 0:
        return False
    # Abs length gap guard: if one side is >2x the other, treat as different.
    if len(longer) > 2 * max(len(shorter), 1):
        return False
    # Character-in-order match ratio.
    i = 0
    for ch in longer:
        if i < len(shorter) and ch == shorter[i]:
            i += 1
    return (i / len(shorter)) >= 0.7


def main() -> int:
    files = sys.argv[1:] if len(sys.argv) > 1 else _staged_files()
    files = [f for f in files if not _is_skippable(f) and Path(f).is_file()]

    violations: list[tuple[str, int, str, str, str]] = []
    for f in files:
        for line_no, old, new in _diff_pairs(f):
            for rule, old_ex, new_ex in _check_pair(old, new):
                violations.append((f, line_no, rule, old_ex, new_ex))

    if not violations:
        return 0

    print(
        "ASCII-rewriting detected (violates feedback_vietnamese_diacritics rule):",
        file=sys.stderr,
    )
    for f, line_no, rule, old, new in violations[:20]:
        print(f"  {f}:{line_no}  [{rule}]", file=sys.stderr)
        print(f"     OLD: {old[:120]}", file=sys.stderr)
        print(f"     NEW: {new[:120]}", file=sys.stderr)
    if len(violations) > 20:
        print(f"  ... and {len(violations) - 20} more", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"Total violations: {len(violations)}", file=sys.stderr)
    print(
        "If intentional (e.g. fixing mojibake), bypass requires explicit user approval.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
