"""Turn raw measurements into per-metric winners, category scores and an overall verdict.

1. Repetitions are summarised as median and interquartile range (IQR).
2. Per-item metrics (one value per site) are combined over the items *every* browser
   completed, so a site that timed out for one browser can't skew the comparison
   (timeouts are scored separately). Each item's median across repetitions is used, so
   a site missing from one repetition doesn't discard the rest of that repetition.
3. Each scored metric gives the best browser 100 and the others a ratio of it.
4. A category score is the mean of its metric scores; the overall score is the
   weighted mean of category scores.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from browserbout import stats
from browserbout.models import Aggregate, Measurement, Run

TIE_MARGIN = 0.5  # score points


@dataclass
class Stat:
    median: float
    q1: float
    q3: float
    n: int

    @classmethod
    def of(cls, values: list[float]) -> Stat:
        q1, q3 = stats.iqr(values)
        return cls(median=stats.median(values), q1=q1, q3=q3, n=len(values))


@dataclass
class MetricResult:
    suite: str
    name: str
    label: str
    unit: str
    higher_is_better: bool
    scored: bool
    floor: float
    item: str | None
    stats: dict[str, Stat]
    scores: dict[str, float] = field(default_factory=dict)
    winner: str | None = None
    # "high": full-mode IQRs don't overlap; "low": they do; None: too few reps to tell.
    confidence: str | None = None
    items_compared: int | None = None

    @property
    def key(self) -> str:
        return f"{self.suite}.{self.name}" + (f"[{self.item}]" if self.item else "")


@dataclass
class CategoryResult:
    suite: str
    metrics: list[MetricResult]
    scores: dict[str, float]
    winner: str | None


@dataclass
class Scorecard:
    browsers: list[str]
    categories: list[CategoryResult]
    overall: dict[str, float]
    winner: str | None
    weights: dict[str, float]
    # Per-item breakdowns (e.g. each site), for detailed reports; not scored directly.
    items: list[MetricResult]
    # Categories left out of the overall score -> browsers that have no data for them.
    unscored: dict[str, list[str]] = field(default_factory=dict)


def _aggregate(values: list[float], how: Aggregate) -> float:
    if how == "sum":
        return float(sum(values))
    if how == "mean":
        return statistics.fmean(values)
    return stats.geomean(values)


def _score(values: dict[str, float], higher_is_better: bool, floor: float) -> dict[str, float]:
    shifted = {b: v + floor for b, v in values.items()}
    if higher_is_better:
        best = max(shifted.values())
        return {b: 100.0 if best <= 0 else 100.0 * v / best for b, v in shifted.items()}
    best = min(shifted.values())
    return {b: 100.0 if v <= 0 else 100.0 * best / v for b, v in shifted.items()}


def _winner(scores: dict[str, float]) -> str | None:
    if len(scores) < 2:
        return None
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if ranked[0][1] - ranked[1][1] < TIE_MARGIN:
        return None
    return ranked[0][0]


def _confidence(result: MetricResult) -> str | None:
    if result.winner is None or any(s.n < 3 for s in result.stats.values()):
        return None
    best = result.stats[result.winner]
    for browser, s in result.stats.items():
        if browser == result.winner:
            continue
        overlaps = s.q1 <= best.q3 and best.q1 <= s.q3
        if overlaps:
            return "low"
    return "high"


def _finish(result: MetricResult) -> MetricResult:
    if len(result.stats) >= 2:
        medians = {b: s.median for b, s in result.stats.items()}
        result.scores = _score(medians, result.higher_is_better, result.floor)
        if result.scored:
            result.winner = _winner(result.scores)
            result.confidence = _confidence(result)
    return result


def build_scorecard(run: Run, weights: dict[str, float]) -> Scorecard:
    browsers = [b.key for b in run.browsers]
    # (suite, name, item) -> browser -> rep -> value
    grouped: dict[tuple[str, str, str | None], dict[str, dict[int, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    meta: dict[tuple[str, str], Measurement] = {}
    for m in run.measurements:
        grouped[(m.suite, m.name, m.item)][m.browser][m.rep] = m.value
        meta.setdefault((m.suite, m.name), m)

    def base(m: Measurement, item: str | None, per_browser: dict[str, list[float]]) -> MetricResult:
        return MetricResult(
            suite=m.suite, name=m.name, label=m.label, unit=m.unit,
            higher_is_better=m.higher_is_better, scored=m.scored, floor=m.floor, item=item,
            stats={b: Stat.of(v) for b, v in per_browser.items() if v},
        )

    summaries: list[MetricResult] = []
    items: list[MetricResult] = []
    for (suite, name), m in meta.items():
        keys = [k for k in grouped if k[0] == suite and k[1] == name]
        if all(k[2] is None for k in keys):
            per_browser = {
                b: list(reps.values()) for b, reps in grouped[(suite, name, None)].items()
            }
            summaries.append(_finish(base(m, None, per_browser)))
            continue

        for key in keys:
            per_browser = {b: list(reps.values()) for b, reps in grouped[key].items()}
            items.append(_finish(base(m, key[2], per_browser)))
        # Only compare items every browser has a value for.
        present = [{k[2] for k in keys if k[2] is not None and grouped[k].get(b)} for b in browsers]
        common = sorted(set.intersection(*present)) if present else []
        summary = base(m, None, {})
        if common:
            for b in browsers:
                item_stats = [Stat.of(list(grouped[(suite, name, i)][b].values())) for i in common]
                summary.stats[b] = Stat(
                    median=_aggregate([s.median for s in item_stats], m.aggregate),
                    q1=_aggregate([s.q1 for s in item_stats], m.aggregate),
                    q3=_aggregate([s.q3 for s in item_stats], m.aggregate),
                    n=min(s.n for s in item_stats),
                )
        summary.items_compared = len(common)
        summaries.append(_finish(summary))

    categories = []
    for suite in run.suites:
        metrics = [r for r in summaries if r.suite == suite]
        scored = [r for r in metrics if r.scored and len(r.scores) == len(browsers)]
        scores = (
            {b: statistics.fmean(r.scores[b] for r in scored) for b in browsers} if scored else {}
        )
        if metrics:
            categories.append(CategoryResult(suite, metrics, scores, _winner(scores)))

    used = {c.suite: weights.get(c.suite, 0.0) for c in categories if c.scores}
    total = sum(used.values())
    overall: dict[str, float] = {}
    if total > 0:
        for b in browsers:
            overall[b] = sum(
                c.scores[b] * used[c.suite] for c in categories if c.suite in used
            ) / total
    norm_weights = {k: v / total * 100 for k, v in used.items()} if total else {}
    with_data = defaultdict(set)
    for m in run.measurements:
        with_data[m.suite].add(m.browser)
    unscored = {
        suite: [b for b in browsers if b not in with_data[suite]]
        for suite in run.suites
        if suite not in used and any(b not in with_data[suite] for b in browsers)
    }
    return Scorecard(
        browsers, categories, overall, _winner(overall), norm_weights, items, unscored
    )
