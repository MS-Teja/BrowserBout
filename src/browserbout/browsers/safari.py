from __future__ import annotations

from pathlib import Path

import psutil
from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver

from browserbout.browsers.base import Browser
from browserbout.config import Window


class Safari(Browser):
    key = "safari"
    name = "Safari"
    engine = "WebKit"
    app_path = Path("/Applications/Safari.app")
    app_process_names = ("Safari",)

    def setup_hints(self) -> list[str]:
        return [
            "Run once: `sudo safaridriver --enable`",
            "Safari → Settings → Advanced → enable 'Show features for web developers', "
            "then Develop → 'Allow Remote Automation'",
        ]

    def create_driver(self, window: Window) -> WebDriver:
        # safaridriver always runs in an isolated automation session with a clean, ephemeral
        # profile and no extensions, so no extra setup is needed for a fair run.
        return webdriver.Safari()

    def processes(self, driver: WebDriver) -> list[psutil.Process]:
        # Safari is launched by launchd, not as a child of safaridriver, and its web content
        # runs in shared com.apple.WebKit.* XPC services. `bout doctor` warns when other
        # WebKit apps are open, since their WebKit processes would be counted too.
        procs = []
        for p in psutil.process_iter(["name"]):
            name = p.info["name"] or ""
            if name == "Safari" or name.startswith("com.apple.WebKit."):
                procs.append(p)
        return procs
