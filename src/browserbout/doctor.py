"""Environment checks: can we automate each browser, and is the Mac in a fair state to benchmark?"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from typing import Literal

import psutil

from browserbout.browsers.base import Browser
from browserbout.config import Window
from browserbout.metrics.power import low_power_mode, read_battery

Status = Literal["ok", "warn", "fail"]


@dataclass
class Check:
    name: str
    status: Status
    detail: str
    hints: tuple[str, ...] = ()


def check_browser(browser: Browser, probe: bool) -> list[Check]:
    if not browser.is_installed():
        return [Check(browser.name, "fail", f"not found at {browser.app_path}")]
    engine = browser.engine_version()
    detail = f"{browser.version()} ({browser.engine}{' ' + engine if engine else ''})"
    checks = [Check(f"{browser.name} installed", "ok", detail)]
    if browser.is_running():
        checks.append(Check(f"{browser.name} closed", "warn",
                            "your own window is open — quit it before benchmarking"))
    if probe:
        try:
            with browser.launch(Window(width=800, height=600)) as session:
                session.driver.get("about:blank")
            checks.append(Check(f"{browser.name} automation", "ok", "session started"))
        except Exception as exc:
            msg = (getattr(exc, "msg", None) or str(exc)).strip().splitlines()[0][:200]
            checks.append(Check(f"{browser.name} automation", "fail", msg,
                                tuple(browser.setup_hints())))
    return checks


def check_system() -> list[Check]:
    checks = []
    battery = read_battery()
    if battery is None:
        checks.append(Check("Battery", "warn", "no battery; the battery suite will be skipped"))
    else:
        source = "on power adapter" if battery.on_ac else "on battery"
        status: Status = "ok"
        detail = (f"{battery.percent:.0f}% "
                  f"({battery.current_mah:.0f}/{battery.max_mah:.0f} mAh), {source}")
        if battery.on_ac:
            detail += " — battery suite needs it unplugged"
            status = "warn"
        elif battery.percent < 60:
            detail += " — charge to 100% before a full run"
            status = "warn"
        checks.append(Check("Battery", status, detail))
    if low_power_mode():
        checks.append(Check("Low Power Mode", "warn", "on — it throttles the CPU; turn it off"))
    else:
        checks.append(Check("Low Power Mode", "ok", "off"))

    cores = os.cpu_count() or 1
    load = psutil.getloadavg()[0]
    checks.append(Check("System load", "warn" if load > cores / 2 else "ok",
                        f"{load:.1f} (1-min avg, {cores} cores)"
                        + (" — close busy apps" if load > cores / 2 else "")))

    # Safari's numbers include every com.apple.WebKit.* process, so other WebKit apps count too.
    safari_running = any(p.info["name"] == "Safari" for p in psutil.process_iter(["name"]))
    webkit = [p for p in psutil.process_iter(["name"])
              if (p.info["name"] or "").startswith("com.apple.WebKit.")]
    if webkit and not safari_running:
        checks.append(Check("Other WebKit apps", "warn",
                            f"{len(webkit)} WebKit processes from other apps (Mail, App Store, …) "
                            "would be counted in Safari's memory/CPU — quit those apps"))
    else:
        checks.append(Check("Other WebKit apps", "ok", "none"))

    try:
        socket.create_connection(("browserbench.org", 443), timeout=5).close()
        checks.append(Check("Network", "ok", "browserbench.org reachable"))
    except OSError as exc:
        checks.append(Check("Network", "fail", f"browserbench.org unreachable ({exc})"))
    return checks
