"""Raw results: one JSON document per run plus a flat CSV of every measurement."""

from __future__ import annotations

import csv
from pathlib import Path

from browserbout.models import Run

CSV_FIELDS = ["run_id", "browser", "suite", "name", "item", "rep", "value", "unit",
              "higher_is_better", "scored", "label"]


def save_run(run: Run, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(run.model_dump_json(indent=2))
    tmp.replace(path)
    return path


def save_csv(run: Run, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for m in run.measurements:
            writer.writerow({
                "run_id": run.id, "browser": m.browser, "suite": m.suite, "name": m.name,
                "item": m.item or "", "rep": m.rep, "value": m.value, "unit": m.unit,
                "higher_is_better": m.higher_is_better, "scored": m.scored, "label": m.label,
            })
    return path


def load_run(path: Path) -> Run:
    return Run.model_validate_json(path.read_text())


def export_all(run: Run, results_dir: Path) -> tuple[Path, Path]:
    return (
        save_run(run, results_dir / f"{run.id}.json"),
        save_csv(run, results_dir / f"{run.id}.csv"),
    )


def latest_run(results_dir: Path) -> Path | None:
    runs = sorted(p for p in results_dir.glob("*.json") if not p.name.endswith(".partial.json"))
    return runs[-1] if runs else None
