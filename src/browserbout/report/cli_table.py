"""Rich terminal scorecard."""

from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from browserbout.models import Run
from browserbout.report.fmt import (
    browser_labels,
    browser_names,
    direction,
    fmt_number,
    fmt_stat,
    metric_label,
    suite_title,
    unscored_notes,
)
from browserbout.scoring import Scorecard


def render(run: Run, card: Scorecard, console: Console) -> None:
    names = browser_names(run)
    labels = browser_labels(run)
    m = run.machine
    console.print(
        Panel(
            f"[bold]{run.id}[/] · {run.mode} mode · {m.model} ({m.chip}, {m.memory_gb:g} GB) · "
            f"{m.os_version} · {m.power_source}\n" + "  vs  ".join(labels.values()),
            title="🥊 BrowserBout",
            border_style="cyan",
        )
    )

    for cat in card.categories:
        table = Table(title=suite_title(cat.suite), box=box.SIMPLE_HEAVY, title_justify="left")
        table.add_column("Metric")
        for b in card.browsers:
            table.add_column(names[b], justify="right")
        table.add_column("Winner")
        table.add_column("Confidence", style="dim")
        for r in cat.metrics:
            row: list[str | Text] = [f"{metric_label(r)} {direction(r)}"]
            for b in card.browsers:
                stat = r.stats.get(b)
                cell = Text(fmt_stat(stat, r.unit) if stat else "—")
                if r.winner == b:
                    cell.stylize("bold green")
                row.append(cell)
            if not r.scored:
                row += ["[dim]info[/]", ""]
            else:
                row += [names[r.winner] if r.winner else "tie", r.confidence or ""]
            table.add_row(*row, style=None if r.scored else "dim")
        console.print(table)

    summary = Table(title="Scorecard (0-100, best = 100)", box=box.ROUNDED, title_justify="left")
    summary.add_column("Category")
    summary.add_column("Weight", justify="right", style="dim")
    for b in card.browsers:
        summary.add_column(names[b], justify="right")
    summary.add_column("Winner")
    for cat in card.categories:
        if not cat.scores:
            continue
        summary.add_row(
            suite_title(cat.suite),
            f"{card.weights.get(cat.suite, 0):.0f}%",
            *[_score_cell(cat.scores[b], cat.winner == b) for b in card.browsers],
            names[cat.winner] if cat.winner else "tie",
        )
    if card.overall:
        summary.add_section()
        summary.add_row(
            "[bold]Overall[/]",
            "100%",
            *[_score_cell(card.overall[b], card.winner == b) for b in card.browsers],
            f"[bold]{names[card.winner]}[/]" if card.winner else "tie",
        )
    console.print(summary)

    if card.winner:
        others = ", ".join(
            f"{names[b]} {fmt_number(s)}" for b, s in card.overall.items() if b != card.winner
        )
        console.print(
            f"\n🏆 [bold green]{names[card.winner]}[/] wins with "
            f"{fmt_number(card.overall[card.winner])} points (vs {others}).\n"
        )
    elif card.overall:
        console.print("\n🤝 It's a tie overall.\n")

    extras = [f"• [yellow]{n}[/]" for n in unscored_notes(run, card)]
    extras += [f"• {n}" for n in run.notes] + [
        f"• [red]{names.get(e.browser, e.browser)} / {suite_title(e.suite)} rep {e.rep + 1}:[/] "
        f"{e.message.splitlines()[0][:200]}"
        for e in run.errors
    ]
    if extras:
        console.print(Panel(Group(*extras), title="Notes", border_style="yellow"))


def _score_cell(score: float, winner: bool) -> Text:
    return Text(f"{score:.1f}", style="bold green" if winner else "")
