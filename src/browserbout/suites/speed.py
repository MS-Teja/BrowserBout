"""Industry-standard browser benchmarks from browserbench.org."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from browserbout.browsers.base import Session
from browserbout.config import Config
from browserbout.models import MetricValue, Mode
from browserbout.suites.base import Suite, SuiteContext, load, metric


@dataclass(frozen=True)
class Benchmark:
    key: str
    label: str
    url: str
    # JS returning truthy once the page is ready to start.
    ready_js: str
    # JS that starts the run (empty when the URL starts it automatically).
    start_js: str
    # JS returning the final score as text, "ERROR", or null while still running.
    result_js: str


BENCHMARKS = {
    b.key: b
    for b in (
        Benchmark(
            key="speedometer",
            label="Speedometer 3.1 (web app responsiveness)",
            url="https://browserbench.org/Speedometer3.1/?startAutomatically",
            ready_js="return true;",
            start_js="",
            result_js="""
                const s = document.getElementById('summary');
                if (!s) return null;
                if (s.className === 'invalid') return 'ERROR';
                if (s.className !== 'valid') return null;
                return document.getElementById('result-number').textContent;
            """,
        ),
        Benchmark(
            key="jetstream",
            label="JetStream 2.2 (JavaScript & WebAssembly)",
            url="https://browserbench.org/JetStream2.2/",
            ready_js="return !!document.querySelector('#status a.button');",
            start_js="JetStream.start();",
            result_js="""
                const el = document.querySelector('#result-summary.done .score');
                return el ? el.textContent : null;
            """,
        ),
        Benchmark(
            key="motionmark",
            label="MotionMark 1.3 (graphics & animation)",
            url="https://browserbench.org/MotionMark1.3/",
            ready_js="return typeof benchmarkController !== 'undefined';",
            start_js="benchmarkController.startBenchmark();",
            result_js="""
                const section = document.getElementById('results');
                const el = document.querySelector('#results .score-container .score');
                if (!section || !el || !el.textContent.trim()) return null;
                return section.classList.contains('selected') ? el.textContent : null;
            """,
        ),
    )
}

_NUMBER = re.compile(r"[\d,]+(?:\.\d+)?")


def parse_score(text: str) -> float:
    match = _NUMBER.search(text)
    if not match:
        raise ValueError(f"Could not parse benchmark score from {text!r}")
    return float(match.group().replace(",", ""))


def _wait(session: Session, js: str, timeout: float, poll: float) -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = session.driver.execute_script(js)
        if value:
            return value
        time.sleep(poll)
    raise TimeoutError(f"Timed out after {timeout:.0f}s")


class SpeedSuite(Suite):
    key = "speed"
    title = "Speed"
    description = "Speedometer, JetStream and MotionMark scores (higher is better)."

    def reps(self, config: Config, mode: Mode) -> int:
        return config.suites.speed.reps(mode)

    def run(self, session: Session, ctx: SuiteContext) -> list[MetricValue]:
        cfg = ctx.config.suites.speed
        results = []
        for key in cfg.benchmarks:
            bench = BENCHMARKS[key]
            ctx.log(f"{bench.label}…")
            load(session.driver, bench.url, timeout=120)
            _wait(session, bench.ready_js, timeout=120, poll=1)
            if bench.start_js:
                session.driver.execute_script(bench.start_js)
            text = str(_wait(session, bench.result_js, timeout=cfg.timeout_seconds, poll=5))
            if text == "ERROR":
                raise RuntimeError(f"{bench.label} reported an invalid run")
            score = parse_score(text)
            ctx.log(f"{bench.label}: {score:g}")
            results.append(metric(key, bench.label, "score", score, higher_is_better=True))
        return results
