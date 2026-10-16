"""Shared formatting for reports."""

from __future__ import annotations

from browserbout.models import Run
from browserbout.scoring import MetricResult, Stat
from browserbout.suites.registry import SUITES


def fmt_number(value: float) -> str:
    if value == int(value) and abs(value) < 1e6:
        return f"{int(value):,}"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:,.1f}"
    return f"{value:,.2f}"


def fmt_stat(stat: Stat, unit: str) -> str:
    text = fmt_number(stat.median) + ("" if unit == "count" else f" {unit}")
    if stat.n > 1 and stat.q3 > stat.q1:
        text += f" ±{fmt_number((stat.q3 - stat.q1) / 2)}"
    return text


def browser_names(run: Run) -> dict[str, str]:
    return {b.key: b.name for b in run.browsers}


def browser_labels(run: Run) -> dict[str, str]:
    return {b.key: f"{b.name} {b.version}" for b in run.browsers}


def suite_title(key: str) -> str:
    cls = SUITES.get(key)
    return cls.title if cls else key


def metric_label(result: MetricResult) -> str:
    label = result.label
    if result.items_compared:
        label += f" · {result.items_compared} sites"
    return label


def direction(result: MetricResult) -> str:
    return "↑" if result.higher_is_better else "↓"
