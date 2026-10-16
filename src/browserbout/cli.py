"""`bout` command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from browserbout import __version__
from browserbout.browsers.registry import BROWSERS, get_browser
from browserbout.config import load_config
from browserbout.doctor import check_browser, check_system
from browserbout.models import Mode, Run
from browserbout.report import cli_table, readme
from browserbout.report.dashboard import write_dashboard
from browserbout.report.export import export_all, latest_run, load_run
from browserbout.runner import Runner
from browserbout.scoring import build_scorecard
from browserbout.suites.registry import SUITES, get_suites

app = typer.Typer(
    help="🥊 BrowserBout — automated head-to-head browser benchmarks for macOS.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

ConfigDir = Annotated[Path, typer.Option(help="Folder with default/sites/weights.yaml.")]
ResultsDir = Annotated[Path, typer.Option(help="Where raw run results are stored.")]
DocsDir = Annotated[Path, typer.Option(help="Where the HTML dashboard is written.")]
ReadmePath = Annotated[Path, typer.Option(help="README to update between BOUT markers.")]


def _split(value: str) -> list[str]:
    return [v.strip().lower() for v in value.split(",") if v.strip()]


def _publish(run: Run, config_dir: Path, results_dir: Path, docs_dir: Path,
             readme_path: Path) -> None:
    weights = load_config(config_dir).weights
    card = build_scorecard(run, weights)
    cli_table.render(run, card, console)
    dashboard = write_dashboard(run, card, docs_dir, results_dir, config_dir)
    console.print(f"📊 Dashboard: [link=file://{dashboard.resolve()}]{dashboard}[/]")
    if readme_path.exists():
        link = readme.pages_url(readme_path.resolve().parent) or "docs/index.html"
        if readme.inject(readme_path, readme.render_markdown(run, card, link)):
            console.print(f"📝 Updated results in {readme_path}")
        else:
            console.print(f"[yellow]{readme_path} has no {readme.START} markers; skipped.[/]")


@app.command()
def run(
    browsers: Annotated[str, typer.Option(help="Comma-separated browsers.")] = "safari,vivaldi",
    suite: Annotated[str, typer.Option(help="Comma-separated suites, or 'all'.")] = "all",
    full: Annotated[bool, typer.Option("--full/--quick",
                                       help="Full (published) or quick (dev) run.")] = False,
    allow_running: Annotated[bool, typer.Option(
        help="Benchmark even if your own browser windows are open (less fair).")] = False,
    publish: Annotated[bool, typer.Option(help="Update README and dashboard afterwards.")] = True,
    config_dir: ConfigDir = Path("config"),
    results_dir: ResultsDir = Path("results"),
    docs_dir: DocsDir = Path("docs"),
    readme_path: ReadmePath = Path("README.md"),
) -> None:
    """Run the benchmark suites and report the winner."""
    mode: Mode = "full" if full else "quick"
    config = load_config(config_dir)
    try:
        selected = [get_browser(b) for b in _split(browsers)]
        suites = get_suites(_split(suite))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if len(selected) < 2:
        raise typer.BadParameter("Pick at least two browsers to compare.")

    missing = [b.name for b in selected if not b.is_installed()]
    if missing:
        console.print(f"[red]Not installed: {', '.join(missing)}[/]")
        raise typer.Exit(1)
    running = [b.name for b in selected if b.is_running()]
    if running and not allow_running:
        console.print(
            f"[red]Please quit {', '.join(running)} first.[/] Your own windows would skew memory, "
            "CPU and battery numbers. (Override with --allow-running.)"
        )
        raise typer.Exit(1)

    console.rule(f"🥊 {' vs '.join(b.name for b in selected)} · {mode} mode")
    runner = Runner(config, mode, selected, suites, results_dir, log=console.log)
    result = runner.run()
    json_path, csv_path = export_all(result, results_dir)
    console.print(f"💾 Saved {json_path} and {csv_path}")
    if publish:
        _publish(result, config_dir, results_dir, docs_dir, readme_path)
    else:
        cli_table.render(result, build_scorecard(result, config.weights), console)


@app.command()
def report(
    path: Annotated[Path | None, typer.Argument(help="Run JSON (default: latest).")] = None,
    publish: Annotated[bool, typer.Option(help="Also update README and dashboard.")] = True,
    config_dir: ConfigDir = Path("config"),
    results_dir: ResultsDir = Path("results"),
    docs_dir: DocsDir = Path("docs"),
    readme_path: ReadmePath = Path("README.md"),
) -> None:
    """Re-score a saved run (e.g. after changing weights) and regenerate reports."""
    path = path or latest_run(results_dir)
    if path is None:
        console.print(f"[red]No runs found in {results_dir}/[/]")
        raise typer.Exit(1)
    result = load_run(path)
    if publish:
        _publish(result, config_dir, results_dir, docs_dir, readme_path)
    else:
        cli_table.render(result, build_scorecard(result, load_config(config_dir).weights), console)


@app.command()
def doctor(
    browsers: Annotated[str, typer.Option(help="Comma-separated browsers.")] = "safari,vivaldi",
    probe: Annotated[bool, typer.Option(help="Start a real automation session.")] = True,
) -> None:
    """Check that browsers can be automated and the Mac is ready for a fair run."""
    icons = {"ok": "[green]✓[/]", "warn": "[yellow]![/]", "fail": "[red]✗[/]"}
    table = Table(show_header=False, box=None, padding=(0, 1))
    checks = [c for b in _split(browsers) for c in check_browser(get_browser(b), probe)]
    checks += check_system()
    for c in checks:
        table.add_row(icons[c.status], c.name, c.detail)
        for hint in c.hints:
            table.add_row("", "", f"[dim]→ {hint}[/]")
    console.print(table)
    if any(c.status == "fail" for c in checks):
        raise typer.Exit(1)


@app.command(name="list")
def list_() -> None:
    """List available browsers and suites."""
    table = Table(title="Browsers")
    table.add_column("Key")
    table.add_column("Name")
    table.add_column("Engine")
    table.add_column("Installed")
    for key, cls in BROWSERS.items():
        b = cls()
        table.add_row(key, b.name, b.engine, b.version() if b.is_installed() else "no")
    console.print(table)
    table = Table(title="Suites")
    table.add_column("Key")
    table.add_column("What it measures")
    for key, scls in SUITES.items():
        table.add_row(key, scls.description)
    console.print(table)


@app.command()
def version() -> None:
    """Print the BrowserBout version."""
    console.print(__version__)


if __name__ == "__main__":
    app()
