"""Suite abstraction and shared browser helpers."""

from __future__ import annotations

import contextlib
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from browserbout.browsers.base import Session
from browserbout.config import Config
from browserbout.models import Aggregate, MetricValue, Mode


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
