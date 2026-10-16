"""Browser abstraction: every supported browser is a subclass registered in registry.py."""

from __future__ import annotations

import contextlib
import plistlib
from abc import ABC, abstractmethod
from pathlib import Path
from types import TracebackType
from typing import ClassVar

import psutil
from selenium.webdriver.remote.webdriver import WebDriver

from browserbout.config import Window
from browserbout.models import BrowserInfo


class Browser(ABC):
    key: ClassVar[str]
    name: ClassVar[str]
    engine: ClassVar[str]
    app_path: ClassVar[Path]
    # Process names of the user's own browser instance; we refuse to benchmark while it's open.
    app_process_names: ClassVar[tuple[str, ...]]

    def is_installed(self) -> bool:
        return self.app_path.exists()

    def version(self) -> str:
        plist = self.app_path / "Contents" / "Info.plist"
        with plist.open("rb") as fh:
            return str(plistlib.load(fh).get("CFBundleShortVersionString", "unknown"))

    def engine_version(self) -> str | None:
        return None

    def info(self) -> BrowserInfo:
        return BrowserInfo(
            key=self.key,
            name=self.name,
            version=self.version(),
            engine=self.engine,
            engine_version=self.engine_version(),
        )

    def is_running(self) -> bool:
        return any(p.info["name"] in self.app_process_names for p in psutil.process_iter(["name"]))

    def setup_hints(self) -> list[str]:
        """Human instructions shown by `bout doctor` when a session can't be started."""
        return []

    @abstractmethod
    def create_driver(self, window: Window) -> WebDriver:
        """Start a fresh automation session with a clean profile."""

    @abstractmethod
    def processes(self, driver: WebDriver) -> list[psutil.Process]:
        """All OS processes belonging to the automated browser instance."""

    def ui_handles(self, driver: WebDriver) -> set[str]:
        """Window handles that belong to the browser's own UI rather than web tabs."""
        return set()

    def cleanup(self) -> None:  # noqa: B027 - optional hook
        """Remove anything create_driver left behind (temp profiles, ...)."""

    def launch(self, window: Window) -> Session:
        return Session(self, window)


class Session:
    """A running browser under automation. Use as a context manager."""

    def __init__(self, browser: Browser, window: Window) -> None:
        self.browser = browser
        self.window = window
        self._ui_handles: set[str] = set()
        self.driver = self._start()

    def _start(self) -> WebDriver:
        driver = self.browser.create_driver(self.window)
        self._ui_handles = self.browser.ui_handles(driver)
        tabs = [h for h in driver.window_handles if h not in self._ui_handles]
        if tabs:
            driver.switch_to.window(tabs[0])
        driver.set_window_rect(x=0, y=0, width=self.window.width, height=self.window.height)
        return driver

    def tab_handles(self) -> list[str]:
        """Handles of real web tabs (excludes browser-UI documents some browsers expose)."""
        return [h for h in self.driver.window_handles if h not in self._ui_handles]

    def processes(self) -> list[psutil.Process]:
        return self.browser.processes(self.driver)

    def restart(self) -> None:
        self.quit()
        self.driver = self._start()

    def quit(self) -> None:
        with contextlib.suppress(Exception):
            self.driver.quit()
        self.browser.cleanup()

    def __enter__(self) -> Session:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.quit()
