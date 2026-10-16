"""Run suites against browsers: interleaved order, fresh session per step, crash-safe saves."""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from browserbout.browsers.base import Browser
from browserbout.config import Config
from browserbout.metrics.machine import machine_info
from browserbout.metrics.power import keep_awake
from browserbout.models import Measurement, Mode, Run, RunError
from browserbout.report.export import save_run
from browserbout.suites.base import Suite, SuiteContext

Logger = Callable[[str], None]


def browser_order(browsers: list[Browser], rep: int) -> list[Browser]:
    """Alternate who goes first each repetition (A,B then B,A) to cancel out drift
    in thermals, network and caches."""
    return browsers if rep % 2 == 0 else browsers[::-1]


class Runner:
    def __init__(
        self,
        config: Config,
        mode: Mode,
        browsers: list[Browser],
        suites: list[Suite],
        results_dir: Path,
        log: Logger = print,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.mode = mode
        self.browsers = browsers
        self.suites = suites
        self.results_dir = results_dir
        self.log = log
        self.sleep = sleep

    def new_run(self) -> Run:
        now = datetime.now().astimezone()
        return Run(
            id=now.strftime("%Y%m%d-%H%M%S") + f"-{self.mode}",
            mode=self.mode,
            started_at=now,
            machine=machine_info(),
            browsers=[b.info() for b in self.browsers],
            suites=[s.key for s in self.suites],
        )

    def run(self) -> Run:
        run = self.new_run()
        partial = self.results_dir / f"{run.id}.partial.json"
        try:
            with keep_awake():
                self._run_suites(run, partial)
        except KeyboardInterrupt:
            run.notes.append("Run was interrupted; results are partial.")
            self.log("[yellow]Interrupted — keeping the results collected so far.[/]")
        run.finished_at = datetime.now().astimezone()
        partial.unlink(missing_ok=True)
        return run

    def _run_suites(self, run: Run, partial: Path) -> None:
        cooldown = self.config.cooldown_seconds(self.mode)
        first = True
        for suite in self.suites:
            reps = suite.reps(self.config, self.mode)
            if reps == 0:
                run.notes.append(f"{suite.title}: skipped in {self.mode} mode.")
                self.log(f"[dim]Skipping {suite.title} in {self.mode} mode[/]")
                continue
            if reason := suite.preflight(self.config, self.mode):
                run.notes.append(f"{suite.title}: skipped because {reason}.")
                self.log(f"[yellow]Skipping {suite.title}: {reason}[/]")
                continue
            for rep in range(reps):
                for browser in browser_order(self.browsers, rep):
                    if not first:
                        self.sleep(cooldown)
                    first = False
                    self._step(run, suite, browser, rep, reps)
                    save_run(run, partial)

    def _step(self, run: Run, suite: Suite, browser: Browser, rep: int, reps: int) -> None:
        prefix = f"[bold]{suite.title}[/] · {browser.name} · rep {rep + 1}/{reps}"
        self.log(f"{prefix}: starting")
        ctx = SuiteContext(
            config=self.config,
            mode=self.mode,
            browser=browser.key,
            rep=rep,
            artifacts=run.artifacts,
            log=lambda msg: self.log(f"{prefix}: {msg}"),
        )
        started = time.monotonic()
        try:
            with browser.launch(self.config.window) as session:
                values = suite.run(session, ctx)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}".strip()
            run.errors.append(
                RunError(browser=browser.key, suite=suite.key, rep=rep, message=message[:2000])
            )
            self.log(f"[red]{prefix}: failed — {message.splitlines()[0][:300]}[/]")
            self.log(f"[dim]{traceback.format_exc(limit=3)}[/]")
            return
        run.measurements += [
            Measurement(**v.model_dump(), browser=browser.key, suite=suite.key, rep=rep)
            for v in values
        ]
        self.log(f"{prefix}: done in {time.monotonic() - started:.0f}s ({len(values)} metrics)")
