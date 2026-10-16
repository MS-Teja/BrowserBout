"""Browser registry. To add a browser, subclass Browser and add it to BROWSERS."""

from __future__ import annotations

from browserbout.browsers.base import Browser
from browserbout.browsers.safari import Safari
from browserbout.browsers.vivaldi import Vivaldi

BROWSERS: dict[str, type[Browser]] = {cls.key: cls for cls in (Safari, Vivaldi)}


def get_browser(key: str) -> Browser:
    try:
        return BROWSERS[key.lower()]()
    except KeyError:
        raise ValueError(f"Unknown browser '{key}'. Available: {', '.join(BROWSERS)}") from None
