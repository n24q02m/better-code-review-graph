#!/usr/bin/env python3
"""Tests for preserve-diacritics.py.

Run with: python scripts/test_preserve_diacritics.py
Exit code 0 => all pass; non-zero => at least one failure.

These tests exercise the pure check function (_check_pair) with hand-crafted
before/after line pairs, avoiding the need for a real git repo.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "preserve_diacritics", _HERE / "preserve-diacritics.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)

check_pair = _MOD._check_pair
similar = _MOD._similar
strip_diacritics = _MOD._strip_diacritics


_failures: list[str] = []


def _assert(cond: bool, label: str) -> None:
    if cond:
        print(f"  PASS: {label}")
    else:
        print(f"  FAIL: {label}")
        _failures.append(label)


def test_case_1_em_dash_to_dashdash() -> None:
    print("Case 1: em-dash -> '--' should FAIL the hook")
    old = "Rust \u2014 the language"
    new = "Rust -- the language"
    v = check_pair(old, new)
    _assert(
        len(v) == 1 and v[0][0].startswith("unicode-punct"), "detects em-dash rewrite"
    )


def test_case_1b_arrow_rewrite() -> None:
    print("Case 1b: right-arrow -> '->' should FAIL")
    old = "input \u2192 output"
    new = "input -> output"
    v = check_pair(old, new)
    _assert(len(v) == 1 and "unicode-punct" in v[0][0], "detects arrow rewrite")


def test_case_1c_ellipsis() -> None:
    print("Case 1c: ellipsis -> '...' should FAIL")
    old = "loading\u2026 please wait"
    new = "loading... please wait"
    v = check_pair(old, new)
    _assert(len(v) == 1 and "unicode-punct" in v[0][0], "detects ellipsis rewrite")


def test_case_1d_smart_quotes() -> None:
    print("Case 1d: smart quotes -> ASCII should FAIL")
    old = "he said \u201chello\u201d loudly"
    new = 'he said "hello" loudly'
    v = check_pair(old, new)
    _assert(any("unicode-punct" in r for r, _, _ in v), "detects smart-quote rewrite")


def test_case_2_pure_add_diacritics_passes() -> None:
    print("Case 2: adding Vietnamese text (not modifying) should PASS")
    # In the pair model an empty `old` means no prior content on this line.
    # But for completeness, test: replacing English with Vietnamese (progress).
    old = "hello world"
    new = "xin ch\u00e0o th\u1ebf gi\u1edbi"
    v = check_pair(old, new)
    _assert(len(v) == 0, "pure-add diacritics not flagged as strip")


def test_case_3_ascii_refactor_passes() -> None:
    print("Case 3: ASCII-only refactor should PASS")
    old = "def foo(x): return x + 1"
    new = "def foo(x: int) -> int: return x + 1"
    v = check_pair(old, new)
    _assert(len(v) == 0, "ASCII refactor not flagged")


def test_case_4_diacritic_strip_flagged() -> None:
    print("Case 4: stripping Vietnamese diacritics should FAIL")
    old = "Ti\u1ebfng Vi\u1ec7t r\u1ea5t \u0111\u1eb9p"
    new = "Tieng Viet rat dep"
    v = check_pair(old, new)
    _assert(
        any("vietnamese-diacritic-strip" in r for r, _, _ in v),
        "detects diacritic strip",
    )


def test_case_5_emoji_removed_flagged() -> None:
    print("Case 5: removing emoji should FAIL")
    old = "Deploy complete \U0001f680 ready for production"
    new = "Deploy complete ready for production"
    v = check_pair(old, new)
    _assert(any("emoji-removed" in r for r, _, _ in v), "detects emoji removal")


def test_case_6_full_rewrite_not_flagged() -> None:
    print("Case 6: full-content rewrite (not a char swap) should PASS")
    old = "The dog \u2014 a brown labrador \u2014 ran away."
    new = "A completely different sentence."
    v = check_pair(old, new)
    _assert(len(v) == 0, "full rewrite not false-flagged")


def test_case_7_char_legit_in_prose() -> None:
    print("Case 7: removing em-dash without ASCII dash replacement should PASS")
    old = "Rust \u2014 awesome"
    new = "Rust is awesome"
    v = check_pair(old, new)
    # Heuristic: no `--` / `-` substitution in similar position => let it pass
    # (the text was rewritten, not mechanically normalized).
    _assert(len(v) == 0, "genuine rewrite removing em-dash not flagged")


def test_case_8_partial_diacritic_unchanged_passes() -> None:
    print("Case 8: preserving diacritics with small edit should PASS")
    old = "Ti\u1ebfng Vi\u1ec7t r\u1ea5t hay"
    new = "Ti\u1ebfng Vi\u1ec7t v\u00f4 c\u00f9ng hay"
    v = check_pair(old, new)
    _assert(len(v) == 0, "diacritic-preserving edit not false-flagged")


def test_case_9_strip_diacritics_helper() -> None:
    print("Case 9: _strip_diacritics helper sanity")
    _assert(strip_diacritics("\u0111") == "d", "dj -> d")
    _assert(
        strip_diacritics("Ti\u1ebfng Vi\u1ec7t") == "Tieng Viet", "Tieng Viet strips"
    )


def test_case_10_similar_helper() -> None:
    print("Case 10: _similar helper sanity")
    _assert(similar("hello world", "hello world!"), "near-equal similar")
    _assert(
        not similar("hello world", "completely different text here"),
        "different strings not similar",
    )


def main() -> int:
    tests = [
        test_case_1_em_dash_to_dashdash,
        test_case_1b_arrow_rewrite,
        test_case_1c_ellipsis,
        test_case_1d_smart_quotes,
        test_case_2_pure_add_diacritics_passes,
        test_case_3_ascii_refactor_passes,
        test_case_4_diacritic_strip_flagged,
        test_case_5_emoji_removed_flagged,
        test_case_6_full_rewrite_not_flagged,
        test_case_7_char_legit_in_prose,
        test_case_8_partial_diacritic_unchanged_passes,
        test_case_9_strip_diacritics_helper,
        test_case_10_similar_helper,
    ]
    for t in tests:
        t()
    print()
    if _failures:
        print(f"FAILED: {len(_failures)} test(s)")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print(f"OK: {len(tests) * 1} assertions all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
