from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from browserbout.browsers.base import Browser
from browserbout.config import Config, Window
from browserbout.models import MetricValue, Mode
from browserbout.runner import Runner, browser_order
from browserbout.suites.base import Suite, SuiteContext, metric


class FakeDriver:
    window_handles: tuple[str, ...] = ()

    def set_window_rect(self, **_: Any) -> None: ...
    def quit(self) -> None: ...


class FakeBrowser(Browser):
    engine = "Fake"
    app_process_names = ()

    def __init__(self, key: str) -> None:
        self.key = key  # type: ignore[misc]
        self.name = key.title()  # type: ignore[misc]
        self.app_path = Path("/nonexistent")  # type: ignore[misc]

    def version(self) -> str:
        return "1.0"

    def create_driver(self, window: Window) -> Any:
        return FakeDriver()

    def processes(self, driver: Any) -> list[Any]:
        return []


class RecordingSuite(Suite):
    key = "speed"
    title = "Fake speed"
    description = "test"

    def __init__(self, reps: int = 2, fail_for: str | None = None, skip: str | None = None):
        self._reps, self.fail_for, self.skip, self.calls = reps, fail_for, skip, []

    def reps(self, config: Config, mode: Mode) -> int:
        return self._reps

    def preflight(self, config: Config, mode: Mode) -> str | None:
        return self.skip

    def run(self, session: Any, ctx: SuiteContext) -> list[MetricValue]:
        self.calls.append((ctx.browser, ctx.rep))
        if ctx.browser == self.fail_for:
            raise RuntimeError("boom")
        return [metric("score", "Score", "pts", 10, higher_is_better=True)]


@pytest.fixture(autouse=True)
def _no_caffeinate(monkeypatch: pytest.MonkeyPatch) -> None:
    import contextlib

    monkeypatch.setattr("browserbout.runner.keep_awake", contextlib.nullcontext)


def _runner(tmp_path: Path, suite: Suite) -> Runner:
    browsers: list[Browser] = [FakeBrowser("a"), FakeBrowser("b")]
    return Runner(Config(), "quick", browsers, [suite], tmp_path, log=lambda _: None,
                  sleep=lambda _: None)


def test_browser_order_alternates() -> None:
    a, b = FakeBrowser("a"), FakeBrowser("b")
    assert browser_order([a, b], 0) == [a, b]
    assert browser_order([a, b], 1) == [b, a]


def test_runner_interleaves_and_records(tmp_path: Path) -> None:
    suite = RecordingSuite(reps=2)
    run = _runner(tmp_path, suite).run()
    assert suite.calls == [("a", 0), ("b", 0), ("b", 1), ("a", 1)]
    assert len(run.measurements) == 4
    assert run.finished_at is not None
    assert not list(tmp_path.glob("*.partial.json"))


def test_runner_keeps_going_after_errors(tmp_path: Path) -> None:
    run = _runner(tmp_path, RecordingSuite(reps=1, fail_for="a")).run()
    assert [e.browser for e in run.errors] == ["a"]
    assert "boom" in run.errors[0].message
    assert {m.browser for m in run.measurements} == {"b"}


def test_runner_skips_suites(tmp_path: Path) -> None:
    run = _runner(tmp_path, RecordingSuite(skip="no battery")).run()
    assert run.measurements == []
    assert "no battery" in run.notes[0]
    run = _runner(tmp_path, RecordingSuite(reps=0)).run()
    assert "skipped in quick mode" in run.notes[0]
