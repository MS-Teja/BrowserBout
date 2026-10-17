"""Keep the results section of README.md in sync with the latest run."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from browserbout.models import Run
from browserbout.report.fmt import (
    browser_labels,
    browser_names,
    direction,
    fmt_stat,
    metric_label,
    suite_title,
    unscored_notes,
)
from browserbout.scoring import Scorecard

START = "<!-- BOUT:START -->"
END = "<!-- BOUT:END -->"


def _origin_remote(repo_dir: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _github_owner_repo(remote: str) -> tuple[str, str] | None:
    match = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$", remote)
    return (match.group(1), match.group(2)) if match else None


def pages_url(repo_dir: Path) -> str | None:
    """https://<user>.github.io/<repo>/ derived from the GitHub origin remote, if any."""
    remote = _origin_remote(repo_dir)
    return github_pages_url(remote) if remote else None


def github_repo_url(repo_dir: Path) -> str | None:
    """https://github.com/<user>/<repo> for the origin remote, if it's on GitHub."""
    remote = _origin_remote(repo_dir)
    parts = _github_owner_repo(remote) if remote else None
    return f"https://github.com/{parts[0]}/{parts[1]}" if parts else None


def github_pages_url(remote: str) -> str | None:
    parts = _github_owner_repo(remote)
    return f"https://{parts[0].lower()}.github.io/{parts[1]}/" if parts else None


def render_markdown(run: Run, card: Scorecard, dashboard_link: str | None = None) -> str:
    names = browser_names(run)
    labels = browser_labels(run)
    m = run.machine
    lines = [
        f"### Latest results — {run.started_at:%Y-%m-%d}",
        "",
        f"_{run.mode.capitalize()} run on {m.model} ({m.chip}, {m.memory_gb:g} GB), "
        f"{m.os_version}, {m.power_source.lower()}._",
        "",
    ]
    if card.winner:
        lines += [f"**🏆 Overall winner: {names[card.winner]}**", ""]

    header = "| Category | Weight | " + " | ".join(labels[b] for b in card.browsers) + " | Winner |"
    lines += [header, "|" + "---|" * (len(card.browsers) + 3)]
    for cat in card.categories:
        if not cat.scores:
            continue
        cells = [_bold(f"{cat.scores[b]:.1f}", cat.winner == b) for b in card.browsers]
        lines.append(
            f"| {suite_title(cat.suite)} | {card.weights.get(cat.suite, 0):.0f}% | "
            + " | ".join(cells)
            + f" | {names[cat.winner] if cat.winner else 'tie'} |"
        )
    if card.overall:
        cells = [_bold(f"{card.overall[b]:.1f}", card.winner == b) for b in card.browsers]
        winner = f"🏆 {names[card.winner]}" if card.winner else "tie"
        lines.append("| **Overall** | | " + " | ".join(cells) + f" | **{winner}** |")

    lines += ["", "<details><summary>All metrics</summary>", ""]
    lines.append("| Category | Metric | " + " | ".join(names[b] for b in card.browsers) + " |")
    lines.append("|" + "---|" * (len(card.browsers) + 2))
    for cat in card.categories:
        for r in cat.metrics:
            cells = [
                _bold(fmt_stat(r.stats[b], r.unit), r.winner == b) if b in r.stats else "—"
                for b in card.browsers
            ]
            info = "" if r.scored else " _(info)_"
            lines.append(
                f"| {suite_title(cat.suite)} | {metric_label(r)} {direction(r)}{info} | "
                + " | ".join(cells) + " |"
            )
    lines += ["", "</details>", ""]
    for note in unscored_notes(run, card):
        lines += [f"> ⚠️ {note}", ""]
    notes = list(run.notes)
    if run.errors:
        notes.append(f"{len(run.errors)} step(s) failed; see the raw results.")
    if notes:
        lines += ["Notes: " + " ".join(notes), ""]
    if dashboard_link:
        lines.append(f"📊 **[Interactive dashboard]({dashboard_link})** · "
                     f"raw data: [`results/{run.id}.json`](results/{run.id}.json)")
    return "\n".join(lines).strip()


def _bold(text: str, on: bool) -> str:
    return f"**{text}**" if on else text


def inject(readme: Path, content: str) -> bool:
    """Replace the text between the BOUT markers. Returns False if markers are missing."""
    text = readme.read_text()
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        return False
    readme.write_text(pattern.sub(lambda _: f"{START}\n{content}\n{END}", text, count=1))
    return True
