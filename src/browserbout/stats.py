"""Small statistics helpers used by suites and scoring."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence


def median(values: Sequence[float]) -> float:
    return float(statistics.median(values))


def iqr(values: Sequence[float]) -> tuple[float, float]:
    """Return the (Q1, Q3) interquartile range. A single value has zero spread."""
    if len(values) < 2:
        return (float(values[0]), float(values[0]))
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return (float(q1), float(q3))


def geomean(values: Sequence[float]) -> float:
    positive = [v for v in values if v > 0]
    if not positive:
        return 0.0
    return math.exp(sum(math.log(v) for v in positive) / len(positive))


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile, pct in [0, 100]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return float(ordered[rank - 1])


def slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Least-squares slope of ys over xs (0 when undefined)."""
    if len(xs) < 2:
        return 0.0
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / denom
