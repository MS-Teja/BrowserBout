"""Stability under stress: many heavy tabs, a long session, crashes and hangs."""

from __future__ import annotations

import itertools
import time

from selenium.common.exceptions import TimeoutException, WebDriverException

from browserbout import stats
from browserbout.browsers.base import Session
from browserbout.config import Config
from browserbout.metrics.process import memory_mb
from browserbout.models import MetricValue, Mode
from browserbout.suites.base import Suite, SuiteContext, is_crash, load, metric, open_in_new_tab

PAGE_TIMEOUT = 45
PROBE_JS = "window.scrollBy(0, 1500); return document.readyState;"


class StabilitySuite(Suite):
    key = "stability"
    title = "Stability"
    description = "Crashes, hangs, responsiveness and memory growth under load (lower is better)."

    def reps(self, config: Config, mode: Mode) -> int:
        return config.suites.stability.reps(mode)

    def run(self, session: Session, ctx: SuiteContext) -> list[MetricValue]:
        cfg = ctx.config.suites.stability
        tabs = cfg.tabs(ctx.mode)
        duration = cfg.duration_minutes(ctx.mode) * 60
        urls = itertools.cycle([s.url for s in ctx.config.sites])

        crashes = hangs = 0
        open_times: list[float] = []
        probe_ms: list[float] = []
        mem_t: list[float] = []
        mem_mb: list[float] = []

        def open_tabs(count: int) -> None:
            load(session.driver, next(urls), PAGE_TIMEOUT)
            for _ in range(count - 1):
                open_times.append(open_in_new_tab(session.driver, next(urls), PAGE_TIMEOUT))

        ctx.log(f"opening {tabs} tabs…")
        open_tabs(tabs)
        session.driver.set_script_timeout(cfg.hang_threshold_seconds)
        start = time.monotonic()
        cycle = 0
        while time.monotonic() - start < duration:
            cycle += 1
            for handle in list(session.driver.window_handles):
                try:
                    session.driver.switch_to.window(handle)
                    t0 = time.perf_counter()
                    session.driver.execute_script(PROBE_JS)
                    elapsed = time.perf_counter() - t0
                    probe_ms.append(elapsed * 1000)
                    if elapsed > cfg.hang_threshold_seconds:
                        hangs += 1
                except TimeoutException:
                    hangs += 1
                except WebDriverException as exc:
                    if not is_crash(exc):
                        raise
                    crashes += 1
                    ctx.log(f"crash detected: {exc.msg}")
                    try:
                        session.driver.close()
                        session.driver.switch_to.window(session.driver.window_handles[0])
                    except (WebDriverException, IndexError):
                        # The whole browser went away: start over with a fresh session.
                        session.restart()
                        open_tabs(tabs)
                        session.driver.set_script_timeout(cfg.hang_threshold_seconds)
                        break
            # Churn: reload the current tab each cycle to exercise memory reclamation.
            try:
                session.driver.refresh()
            except TimeoutException:
                pass
            except WebDriverException as exc:
                if not is_crash(exc):
                    raise
            mem_t.append((time.monotonic() - start) / 60)
            mem_mb.append(memory_mb(session.processes()))
            ctx.log(f"cycle {cycle}: {mem_mb[-1]:.0f} MB, {crashes} crashes, {hangs} hangs")

        return [
            metric("crashes", "Crashes", "count", crashes, higher_is_better=False, floor=1),
            metric("hangs", f"Hangs (> {cfg.hang_threshold_seconds:g}s unresponsive)", "count",
                   hangs, higher_is_better=False, floor=1),
            metric("probe_p95", "Tab responsiveness under load (p95)", "ms",
                   stats.percentile(probe_ms, 95), higher_is_better=False, floor=50),
            metric("tab_open", "Time to open a tab under load (median)", "s",
                   stats.median(open_times) if open_times else 0, higher_is_better=False),
            metric("memory_growth", "Memory growth over the session", "MB/min",
                   max(0.0, stats.slope(mem_t, mem_mb)), higher_is_better=False, floor=5),
            metric("peak_memory", f"Peak memory with {tabs} tabs", "MB",
                   max(mem_mb, default=0), higher_is_better=False),
        ]
