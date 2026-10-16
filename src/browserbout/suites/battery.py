"""Battery drain while browsing and watching video, unplugged."""

from __future__ import annotations

import threading
import time

from browserbout import stats
from browserbout.browsers.base import Session
from browserbout.config import Config
from browserbout.metrics.power import read_battery
from browserbout.models import MetricValue, Mode
from browserbout.suites.base import Suite, SuiteContext, load, metric

CYCLE_SECONDS = 120
SITE_DWELL_SECONDS = 12
SAMPLE_SECONDS = 5


class PluggedInError(RuntimeError):
    pass


class BatterySuite(Suite):
    key = "battery"
    title = "Battery"
    description = "Energy drain while browsing and watching video on battery (lower is better)."

    def reps(self, config: Config, mode: Mode) -> int:
        return config.suites.battery.reps(mode)

    def preflight(self, config: Config, mode: Mode) -> str | None:
        state = read_battery()
        if state is None:
            return "this Mac has no battery"
        if state.on_ac:
            return "the Mac is plugged in; unplug it to measure battery drain"
        return None

    def run(self, session: Session, ctx: SuiteContext) -> list[MetricValue]:
        cfg = ctx.config.suites.battery
        duration = cfg.duration_minutes(ctx.mode) * 60
        sites = ctx.config.sites_for(ctx.mode)

        before = read_battery()
        if before is None or before.on_ac:
            raise PluggedInError("Battery suite needs the Mac on battery power")

        watts: list[float] = []
        plugged_in = threading.Event()
        stop = threading.Event()

        def sampler() -> None:
            while not stop.wait(SAMPLE_SECONDS):
                state = read_battery()
                if state is None:
                    continue
                if state.on_ac:
                    plugged_in.set()
                    return
                watts.append(state.discharge_watts)

        thread = threading.Thread(target=sampler, daemon=True)
        thread.start()
        start = time.monotonic()
        try:
            site_index = 0
            while time.monotonic() - start < duration and not plugged_in.is_set():
                load(session.driver, cfg.video_url, 45)
                time.sleep(CYCLE_SECONDS * cfg.video_share)
                browse_until = time.monotonic() + CYCLE_SECONDS * (1 - cfg.video_share)
                while time.monotonic() < browse_until:
                    load(session.driver, sites[site_index % len(sites)].url, 45)
                    site_index += 1
                    for _ in range(4):
                        session.driver.execute_script("window.scrollBy(0, 800);")
                        time.sleep(SITE_DWELL_SECONDS / 4)
                elapsed_min = (time.monotonic() - start) / 60
                ctx.log(f"{elapsed_min:.0f}/{duration / 60:.0f} min, "
                        f"avg {stats.median(watts) if watts else 0:.2f} W")
        finally:
            stop.set()
            thread.join(timeout=SAMPLE_SECONDS * 2)

        if plugged_in.is_set():
            raise PluggedInError("Power adapter was connected during the battery test")
        after = read_battery()
        assert after is not None
        hours = (time.monotonic() - start) / 3600
        used_mah = max(0.0, before.current_mah - after.current_mah)
        mah_per_hour = used_mah / hours
        avg_watts = sum(watts) / len(watts) if watts else 0.0
        return [
            metric("mah_per_hour", "Battery drain", "mAh/h", mah_per_hour, higher_is_better=False),
            metric("avg_watts", "Average battery power draw", "W", avg_watts,
                   higher_is_better=False, scored=False),
            metric("percent_per_hour", "Battery used per hour", "%/h",
                   max(0.0, before.percent - after.percent) / hours,
                   higher_is_better=False, scored=False),
            metric("estimated_hours", "Estimated battery life for this workload", "h",
                   after.max_mah / mah_per_hour if mah_per_hour else 0,
                   higher_is_better=True, scored=False),
        ]
