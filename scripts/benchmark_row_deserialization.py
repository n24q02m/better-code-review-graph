"""Đo chi phí bỏ qua json.loads cho extra='{}'."""

from __future__ import annotations

import json
from statistics import median, stdev
from timeit import repeat

ROWS = ["{}"] * 9_500 + ['{"kind":"Function"}'] * 500


def baseline() -> None:
    for raw in ROWS:
        json.loads(raw) if raw else {}


def optimized() -> None:
    for raw in ROWS:
        json.loads(raw) if raw and raw != "{}" else {}


def measure(function) -> list[float]:
    return repeat(function, number=100, repeat=25)


def report(name: str, samples: list[float]) -> None:
    print(
        f"{name}: min={min(samples):.6f}s "
        f"median={median(samples):.6f}s "
        f"stdev={stdev(samples):.6f}s"
    )


if __name__ == "__main__":
    baseline_samples = measure(baseline)
    optimized_samples = measure(optimized)
    report("baseline", baseline_samples)
    report("optimized", optimized_samples)
    print(f"rows={len(ROWS)} empty_rows={ROWS.count('{}')} reps=25 number=100")
