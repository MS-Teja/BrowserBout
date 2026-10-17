from typing import Any

import pytest
from selenium.common.exceptions import TimeoutException, WebDriverException
from urllib3.exceptions import ReadTimeoutError

from browserbout.config import Config
from browserbout.suites.base import SuiteContext, attempt


class FakeSession:
    def __init__(self) -> None:
        self.restarts = 0

    def restart(self) -> None:
        self.restarts += 1


def _ctx(logs: list[str]) -> SuiteContext:
    return SuiteContext(config=Config(), mode="quick", browser="x", rep=0, log=logs.append)


def test_success_passes_through() -> None:
    session, logs = FakeSession(), []
    assert attempt(session, _ctx(logs), "step", lambda: 42) == 42  # type: ignore[arg-type]
    assert session.restarts == 0 and logs == []


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutException("timeout: Timed out receiving message from renderer: 45.000"),
        ReadTimeoutError(None, "localhost", "Read timed out."),  # type: ignore[arg-type]
        WebDriverException("tab crashed"),
    ],
)
def test_stuck_or_crashed_browser_is_restarted(exc: Exception) -> None:
    session, logs = FakeSession(), []

    def step() -> Any:
        raise exc

    assert attempt(session, _ctx(logs), "cnn", step) is None  # type: ignore[arg-type]
    assert session.restarts == 1
    assert logs and logs[0].startswith("cnn: browser")


def test_other_errors_propagate() -> None:
    session = FakeSession()

    def step() -> Any:
        raise WebDriverException("no such element")

    with pytest.raises(WebDriverException):
        attempt(session, _ctx([]), "x", step)  # type: ignore[arg-type]
    assert session.restarts == 0
