from __future__ import annotations

from datetime import UTC, datetime

import pytest

from browserbout.models import BrowserInfo, MachineInfo, Measurement, Run


def measurement(
    browser: str, suite: str, name: str, value: float, *, rep: int = 0,
    item: str | None = None, higher_is_better: bool = False, **kw: object,
) -> Measurement:
    return Measurement(browser=browser, suite=suite, name=name, label=name, unit="ms",
                       value=value, rep=rep, item=item, higher_is_better=higher_is_better,
                       **kw)  # type: ignore[arg-type]


def make_run(measurements: list[Measurement], suites: list[str] | None = None) -> Run:
    return Run(
        id="20261016-120000-quick",
        mode="quick",
        started_at=datetime(2026, 10, 16, 12, tzinfo=UTC),
        machine=MachineInfo(model="Mac17,5", chip="Apple A18 Pro", memory_gb=8,
                            os_version="macOS 27.0.1", power_source="Battery Power"),
        browsers=[
            BrowserInfo(key="safari", name="Safari", version="27.0.1", engine="WebKit"),
            BrowserInfo(key="vivaldi", name="Vivaldi", version="8.2", engine="Blink"),
        ],
        suites=suites or sorted({m.suite for m in measurements}),
        measurements=measurements,
    )


@pytest.fixture
def sample_run() -> Run:
    ms = []
    for rep, (s, v) in enumerate([(500, 450), (520, 440), (510, 460)]):
        ms.append(measurement("safari", "speed", "speedometer", s, rep=rep, higher_is_better=True))
        ms.append(measurement("vivaldi", "speed", "speedometer", v, rep=rep, higher_is_better=True))
    for site, (s, v) in {"google": (800, 1000), "leetcode": (2000, 1800)}.items():
        ms.append(measurement("safari", "pageload", "cold_load", s, item=site))
        ms.append(measurement("vivaldi", "pageload", "cold_load", v, item=site))
    ms.append(measurement("safari", "resources", "idle_memory", 300))
    ms.append(measurement("vivaldi", "resources", "idle_memory", 600))
    ms.append(measurement("safari", "resources", "processes", 9, scored=False))
    ms.append(measurement("vivaldi", "resources", "processes", 12, scored=False))
    return make_run(ms, suites=["speed", "pageload", "resources"])
