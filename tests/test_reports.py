from pathlib import Path

from rich.console import Console

from browserbout.models import Run
from browserbout.report import cli_table, readme
from browserbout.report.dashboard import build_view, write_dashboard
from browserbout.report.export import export_all, latest_run, load_run
from browserbout.scoring import build_scorecard

WEIGHTS = {"speed": 50, "pageload": 30, "resources": 20}
REPO_CONFIG = Path(__file__).parent.parent / "config"


def test_export_roundtrip(tmp_path: Path, sample_run: Run) -> None:
    json_path, csv_path = export_all(sample_run, tmp_path)
    assert load_run(json_path) == sample_run
    lines = csv_path.read_text().splitlines()
    assert lines[0].startswith("run_id,browser,suite")
    assert len(lines) == len(sample_run.measurements) + 1
    (tmp_path / "zzz.partial.json").write_text("{}")
    assert latest_run(tmp_path) == json_path


def test_readme_injection(tmp_path: Path, sample_run: Run) -> None:
    path = tmp_path / "README.md"
    path.write_text(f"# Title\n\n{readme.START}\nPLACEHOLDER-BLOCK\n{readme.END}\n\nFooter\n")
    md = readme.render_markdown(sample_run, build_scorecard(sample_run, WEIGHTS), "https://x/")
    assert readme.inject(path, md)
    text = path.read_text()
    assert "PLACEHOLDER-BLOCK" not in text
    assert "Overall winner: Safari" in text
    assert text.startswith("# Title") and text.rstrip().endswith("Footer")
    # Idempotent: injecting again keeps exactly one block.
    assert readme.inject(path, md)
    assert path.read_text().count(readme.START) == 1


def test_readme_without_markers(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("# nothing\n")
    assert not readme.inject(path, "x")


def test_github_pages_url() -> None:
    assert readme.github_pages_url("git@github.com:Teja/browserbout.git") == (
        "https://teja.github.io/browserbout/"
    )
    assert readme.github_pages_url("https://github.com/teja/browserbout") == (
        "https://teja.github.io/browserbout/"
    )
    assert readme.github_pages_url("https://gitlab.com/a/b") is None


def test_cli_table_renders(sample_run: Run) -> None:
    console = Console(record=True, width=140)
    cli_table.render(sample_run, build_scorecard(sample_run, WEIGHTS), console)
    out = console.export_text()
    assert "Scorecard" in out and "Safari" in out and "wins" in out


def test_dashboard(tmp_path: Path, sample_run: Run) -> None:
    card = build_scorecard(sample_run, WEIGHTS)
    view = build_view(sample_run, card, [])
    # Colour follows the browser, not its position.
    assert {b["key"]: b["slot"] for b in view["browsers"]} == {"safari": 1, "vivaldi": 2}
    export_all(sample_run, tmp_path / "results")
    out = write_dashboard(sample_run, card, tmp_path / "docs", tmp_path / "results", REPO_CONFIG)
    html = out.read_text()
    assert "🏆 Safari" in html
    assert "leetcode" in html
    assert (tmp_path / "docs" / ".nojekyll").exists()
