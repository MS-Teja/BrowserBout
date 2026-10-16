"""Memory and CPU used by the browser, idle and with many tabs open."""

from __future__ import annotations

import itertools
import time

from browserbout.browsers.base import Session
from browserbout.config import Config
from browserbout.metrics.process import sample
from browserbout.models import MetricValue, Mode
from browserbout.suites.base import Suite, SuiteContext, load, metric, open_in_new_tab

PAGE_TIMEOUT = 45


class ResourcesSuite(Suite):
    key = "resources"
    title = "Resource usage"
    description = "RAM and CPU of the whole browser process tree (lower is better)."

    def reps(self, config: Config, mode: Mode) -> int:
        return config.suites.resources.reps(mode)

    def run(self, session: Session, ctx: SuiteContext) -> list[MetricValue]:
        cfg = ctx.config.suites.resources
        idle_seconds = cfg.idle_seconds(ctx.mode)
        tabs = cfg.tabs(ctx.mode)

        load(session.driver, "about:blank", PAGE_TIMEOUT)
        time.sleep(idle_seconds)
        idle = sample(session.processes, cfg.sample_seconds)
        ctx.log(f"idle: {idle.memory_mb:.0f} MB, {idle.cpu_percent:.1f}% CPU")

        urls = itertools.cycle([s.url for s in ctx.config.sites])
        load(session.driver, next(urls), PAGE_TIMEOUT)
        for _ in range(tabs - 1):
            open_in_new_tab(session.driver, next(urls), PAGE_TIMEOUT)
        time.sleep(idle_seconds)
        loaded = sample(session.processes, cfg.sample_seconds)
        ctx.log(f"{tabs} tabs: {loaded.memory_mb:.0f} MB, {loaded.cpu_percent:.1f}% CPU")

        return [
            metric("idle_memory", "Memory, idle (1 blank tab)", "MB", idle.memory_mb,
                   higher_is_better=False),
            metric("idle_cpu", "CPU, idle", "% core", idle.cpu_percent,
                   higher_is_better=False, floor=5),
            metric("tabs_memory", f"Memory with {tabs} site tabs", "MB", loaded.memory_mb,
                   higher_is_better=False),
            metric("tabs_cpu", f"Background CPU with {tabs} site tabs", "% core",
                   loaded.cpu_percent, higher_is_better=False, floor=5),
            metric("memory_per_tab", "Memory per extra tab", "MB",
                   max(0.0, loaded.memory_mb - idle.memory_mb) / tabs, higher_is_better=False),
            metric("processes", f"Processes with {tabs} tabs", "count", loaded.process_count,
                   higher_is_better=False, scored=False),
        ]
