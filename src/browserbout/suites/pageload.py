"""Real-world page loads: cold (empty cache) and warm (cached) visits to popular sites."""

from __future__ import annotations

import time
from functools import partial
from typing import Any

from browserbout.browsers.base import Session
from browserbout.config import Config, Site
from browserbout.models import MetricValue, Mode
from browserbout.suites.base import Suite, SuiteContext, attempt, load, metric

# Reads Navigation Timing, paint timing and LCP (via a buffered observer, since LCP entries
# aren't exposed through getEntriesByType). Missing APIs come back as null.
TIMING_JS = """
const done = arguments[arguments.length - 1];
const nav = performance.getEntriesByType('navigation')[0];
const fcp = performance.getEntriesByName('first-contentful-paint')[0];
const result = {
  ttfb: nav ? nav.responseStart - nav.startTime : null,
  dcl: nav ? nav.domContentLoadedEventEnd - nav.startTime : null,
  load: nav && nav.loadEventEnd > 0 ? nav.loadEventEnd - nav.startTime : null,
  fcp: fcp ? fcp.startTime : null,
  lcp: null,
};
const types = (window.PerformanceObserver && PerformanceObserver.supportedEntryTypes) || [];
if (!types.includes('largest-contentful-paint')) { done(result); return; }
new PerformanceObserver((list) => {
  const entries = list.getEntries();
  if (entries.length) result.lcp = entries[entries.length - 1].startTime;
}).observe({ type: 'largest-contentful-paint', buffered: true });
setTimeout(() => done(result), 250);
"""

METRICS = {
    # key in TIMING_JS result -> (label, measured on cold visit, measured on warm visit)
    "ttfb": ("Time to first byte", True, False),
    "fcp": ("First contentful paint", True, True),
    "lcp": ("Largest contentful paint", True, True),
    "dcl": ("DOMContentLoaded", True, True),
    "load": ("Full page load", True, True),
}


class PageLoadSuite(Suite):
    key = "pageload"
    title = "Page loads"
    description = "Cold and warm load timings for real sites (lower is better)."

    def reps(self, config: Config, mode: Mode) -> int:
        return config.suites.pageload.reps(mode)

    def run(self, session: Session, ctx: SuiteContext) -> list[MetricValue]:
        cfg = ctx.config.suites.pageload
        results: list[MetricValue] = []
        for site in ctx.config.sites_for(ctx.mode):
            visit = partial(self._visit, session, site, ctx)
            site_results = attempt(session, ctx, site.name, visit)
            timed_out = site_results is None or site_results[1]
            if site_results is not None:
                results += site_results[0]
            if timed_out and site_results is not None:
                # A load that hit the timeout can leave the tab stuck; start clean.
                session.restart()
            results.append(
                metric("timeouts", f"Page loads that didn't finish in {cfg.timeout_seconds}s",
                       "pages", int(timed_out), higher_is_better=False, item=site.name,
                       aggregate="sum", floor=1)
            )
            ctx.log(f"{site.name} {'timed out' if timed_out else 'done'}")
        return results

    def _visit(
        self, session: Session, site: Site, ctx: SuiteContext
    ) -> tuple[list[MetricValue], bool]:
        """Cold then warm visit. Returns the timings and whether a load timed out."""
        cfg = ctx.config.suites.pageload
        driver = session.driver
        driver.set_script_timeout(10)
        results: list[MetricValue] = []
        for visit in ("cold", "warm"):
            load(driver, "about:blank", cfg.timeout_seconds)
            if not load(driver, site.url, cfg.timeout_seconds):
                return results, True
            time.sleep(cfg.settle_seconds)
            timing: dict[str, Any] = driver.execute_async_script(TIMING_JS)
            for key, (label, on_cold, on_warm) in METRICS.items():
                value = timing.get(key)
                if value is None or value <= 0 or not (on_cold if visit == "cold" else on_warm):
                    continue
                results.append(
                    metric(f"{visit}_{key}", f"{label} ({visit})", "ms", value,
                           higher_is_better=False, item=site.name)
                )
        return results, False
