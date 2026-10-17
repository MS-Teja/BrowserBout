"""Suite abstraction and shared browser helpers."""

from __future__ import annotations

import contextlib
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, TypeVar

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver
from urllib3.exceptions import ReadTimeoutError

from browserbout.browsers.base import Session
from browserbout.config import Config
from browserbout.models import Aggregate, MetricValue, Mode

T = TypeVar("T")


@dataclass
class SuiteContext:
    config: Config
    mode: Mode
    browser: str
    rep: int
    # Shared across the whole run; saved into Run.artifacts.
    artifacts: dict[str, Any] = field(default_factory=dict)
    log: Callable[[str], None] = lambda _msg: None


class Suite(ABC):
    key: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str]

    @abstractmethod
    def reps(self, config: Config, mode: Mode) -> int: ...

    def preflight(self, config: Config, mode: Mode) -> str | None:
        """Return a reason to skip this suite entirely, or None to run it."""
        return None

    @abstractmethod
    def run(self, session: Session, ctx: SuiteContext) -> list[MetricValue]: ...


def metric(
    name: str,
    label: str,
    unit: str,
    value: float,
    *,
    higher_is_better: bool,
    item: str | None = None,
    aggregate: Aggregate = "geomean",
    scored: bool = True,
    floor: float = 0,
) -> MetricValue:
    return MetricValue(
        name=name,
        label=label,
        unit=unit,
        value=float(value),
        higher_is_better=higher_is_better,
        item=item,
        aggregate=aggregate,
        scored=scored,
        floor=floor,
    )


def load(driver: WebDriver, url: str, timeout: float) -> bool:
    """Navigate and wait for the load event. On timeout, stop loading and return False."""
    driver.set_page_load_timeout(timeout)
    try:
        driver.get(url)
        return True
    except TimeoutException:
        with contextlib.suppress(WebDriverException):
            driver.execute_script("window.stop();")
        return False


def open_in_new_tab(driver: WebDriver, url: str, timeout: float) -> float:
    """Open url in a new tab; return seconds until its load event (or the timeout)."""
    start = time.perf_counter()
    driver.switch_to.new_window("tab")
    load(driver, url, timeout)
    return time.perf_counter() - start


def is_crash(exc: WebDriverException) -> bool:
    msg = (exc.msg or str(exc)).lower()
    return any(
        s in msg for s in ("tab crashed", "invalid session id", "session deleted", "no such window",
                           "disconnected", "not connected", "session is not created")
    )


def attempt(session: Session, ctx: SuiteContext, what: str, step: Callable[[], T]) -> T | None:
    """Run one browser step; if it leaves the browser stuck, restart it and return None.

    `step` must return a non-None value on success.

    A page that never finishes loading can wedge chromedriver: every later command then
    fails with "Timed out receiving message from renderer". Instead of losing the whole
    repetition, the suite records what it can, gets a fresh session and carries on.
    """
    try:
        return step()
    except (TimeoutException, ReadTimeoutError, TimeoutError) as exc:
        reason = "stopped responding"
        detail = str(getattr(exc, "msg", None) or exc)
    except WebDriverException as exc:
        if not is_crash(exc):
            raise
        reason = "crashed"
        detail = str(exc.msg or exc)
    ctx.log(f"{what}: browser {reason} ({detail.strip().splitlines()[0][:120]}); restarting it")
    session.restart()
    return None
