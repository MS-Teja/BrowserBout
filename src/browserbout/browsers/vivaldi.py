from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

import psutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.selenium_manager import SeleniumManager
from selenium.webdriver.remote.webdriver import WebDriver

from browserbout.browsers.base import Browser
from browserbout.config import Window

_CACHE_DIR = Path.home() / ".cache" / "browserbout"
_CHROMIUM_VERSION = re.compile(rb"\x00(1\d\d\.0\.\d{4}\.\d{1,4})\x00")


class Vivaldi(Browser):
    key = "vivaldi"
    name = "Vivaldi"
    engine = "Blink"
    app_path = Path("/Applications/Vivaldi.app")
    app_process_names = ("Vivaldi",)

    def __init__(self) -> None:
        self._profile_dir: str | None = None

    @property
    def binary(self) -> Path:
        return self.app_path / "Contents" / "MacOS" / "Vivaldi"

    def engine_version(self) -> str | None:
        """The Chromium version Vivaldi is built on, needed to pick a matching chromedriver.

        Vivaldi only reports its own version, so we scan the framework binary for the embedded
        Chromium version string once and cache the answer per Vivaldi version.
        """
        if not self.is_installed():
            return None
        cache = _CACHE_DIR / f"vivaldi-{self.version()}.chromium"
        if cache.exists():
            return cache.read_text().strip() or None
        framework = next(
            (self.app_path / "Contents" / "Frameworks").glob(
                "Vivaldi Framework.framework/Versions/Current/Vivaldi Framework"
            ),
            None,
        )
        if framework is None:
            return None
        found: str | None = None
        tail = b""
        with framework.open("rb") as fh:
            while chunk := fh.read(8 * 1024 * 1024):
                match = _CHROMIUM_VERSION.search(tail + chunk)
                if match:
                    found = match.group(1).decode()
                    break
                tail = chunk[-32:]
        if found:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(found)
        return found

    def setup_hints(self) -> list[str]:
        return [
            "The first run downloads a chromedriver matching Vivaldi's Chromium version "
            "(needs access to storage.googleapis.com).",
            "Or point BOUT_CHROMEDRIVER at a chromedriver of the same major version.",
        ]

    def chromedriver_path(self) -> str:
        """Resolve a chromedriver whose major version matches Vivaldi's Chromium.

        Selenium Manager can't do this on its own: it runs `Vivaldi --version`, sees "8.x"
        and treats that as the Chrome version. So we ask for the Chromium major explicitly.
        """
        if override := os.environ.get("BOUT_CHROMEDRIVER"):
            return override
        chromium = self.engine_version()
        if chromium is None:
            raise RuntimeError("Could not determine Vivaldi's Chromium version")
        os.environ.setdefault("SE_AVOID_STATS", "true")
        args = ["--driver", "chromedriver", "--browser-version", chromium.split(".")[0],
                "--skip-driver-in-path", "--avoid-browser-download"]
        return str(SeleniumManager().binary_paths(args)["driver_path"])

    def create_driver(self, window: Window) -> WebDriver:
        service = Service(executable_path=self.chromedriver_path())
        self._profile_dir = tempfile.mkdtemp(prefix="bout-vivaldi-")
        opts = webdriver.ChromeOptions()
        opts.binary_location = str(self.binary)
        for arg in (
            f"--user-data-dir={self._profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            f"--window-size={window.width},{window.height}",
        ):
            opts.add_argument(arg)
        return webdriver.Chrome(options=opts, service=service)

    def processes(self, driver: WebDriver) -> list[psutil.Process]:
        # chromedriver launches Vivaldi as its child, so the whole browser is its process tree.
        service = getattr(driver, "service", None)
        pid = getattr(getattr(service, "process", None), "pid", None)
        if pid is None:
            return []
        try:
            return psutil.Process(pid).children(recursive=True)
        except psutil.NoSuchProcess:
            return []

    def cleanup(self) -> None:
        if self._profile_dir:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
            self._profile_dir = None
