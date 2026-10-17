"""Static HTML dashboard (docs/index.html), ready for GitHub Pages. No external assets."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from browserbout.browsers.registry import BROWSERS
from browserbout.config import load_config
from browserbout.models import Run
from browserbout.report.export import load_run
from browserbout.report.fmt import (
    browser_labels,
    browser_names,
    fmt_number,
    fmt_stat,
    metric_label,
    suite_title,
    unscored_notes,
)
from browserbout.report.readme import github_repo_url
from browserbout.scoring import MetricResult, Scorecard, build_scorecard

TEMPLATES = Path(str(resources.files("browserbout") / "report" / "templates"))
SERIES_SLOTS = 8


def _series_slot(key: str) -> int:
    """Colour follows the browser, never its position in a run: Safari is always slot 1."""
    order = list(BROWSERS)
    return (order.index(key) if key in order else len(order)) % SERIES_SLOTS + 1


def _metric_view(r: MetricResult, browsers: list[str]) -> dict[str, Any]:
    peak = max((s.median for s in r.stats.values()), default=0) or 1
    return {
        "label": metric_label(r),
        "unit": r.unit,
        "better": "higher is better" if r.higher_is_better else "lower is better",
        "scored": r.scored,
        "winner": r.winner,
        "confidence": r.confidence,
        "bars": [
            {
                "browser": b,
                "pct": r.stats[b].median / peak * 100,
                "text": fmt_stat(r.stats[b], r.unit),
                "n": r.stats[b].n,
                "score": f"{r.scores[b]:.1f}" if b in r.scores else None,
            }
            for b in browsers
            if b in r.stats
        ],
    }


def build_view(
    run: Run, card: Scorecard, history: list[dict[str, Any]], repo_url: str | None = None
) -> dict[str, Any]:
    names = browser_names(run)
    browsers = [
        {"key": b, "name": names[b], "label": browser_labels(run)[b], "slot": _series_slot(b)}
        for b in card.browsers
    ]
    categories = [
        {
            "key": c.suite,
            "title": suite_title(c.suite),
            "weight": f"{card.weights.get(c.suite, 0):.0f}%",
            "winner": c.winner,
            "scores": c.scores,
            "metrics": [_metric_view(r, card.browsers) for r in c.metrics],
        }
        for c in card.categories
    ]
    # Per-site cold page loads, for the "which sites" breakdown.
    sites = [
        {"site": r.item, **_metric_view(r, card.browsers)}
        for r in card.items
        if r.suite == "pageload" and r.name == "cold_load"
    ]
    return {
        "run": run,
        "browsers": browsers,
        "names": names,
        "winner": card.winner,
        "overall": {b: f"{s:.1f}" for b, s in card.overall.items()},
        "margin": (
            fmt_number(card.overall[card.winner] - min(card.overall.values()))
            if card.winner else None
        ),
        "categories": categories,
        "sites": sites,
        "fingerprint": run.artifacts.get("fingerprint", {}),
        "history": history,
        "unscored": unscored_notes(run, card),
        "repo_url": repo_url,
    }


def _history(results_dir: Path, weights: dict[str, float]) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(results_dir.glob("*.json"), reverse=True):
        if path.name.endswith(".partial.json"):
            continue
        try:
            run = load_run(path)
        except ValueError:
            continue
        card = build_scorecard(run, weights)
        names = browser_names(run)
        rows.append({
            "id": run.id,
            "date": f"{run.started_at:%Y-%m-%d %H:%M}",
            "mode": run.mode,
            "versions": " vs ".join(browser_labels(run).values()),
            "winner": names.get(card.winner, "tie") if card.winner else "tie",
            "scores": " / ".join(f"{names[b]} {s:.1f}" for b, s in card.overall.items()),
        })
    return rows[:30]


def write_dashboard(run: Run, card: Scorecard, out_dir: Path, results_dir: Path,
                    config_dir: Path) -> Path:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape())
    weights = load_config(config_dir).weights
    html = env.get_template("dashboard.html.j2").render(
        **build_view(run, card, _history(results_dir, weights), github_repo_url(Path.cwd()))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "index.html"
    out.write_text(html)
    # Tell GitHub Pages to serve the file as-is.
    (out_dir / ".nojekyll").touch()
    return out
