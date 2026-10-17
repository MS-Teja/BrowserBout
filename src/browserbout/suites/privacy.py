"""Privacy: tracker requests on real sites, and how fingerprintable the browser is."""

from __future__ import annotations

import contextlib
import functools
import threading
import time
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from browserbout.browsers.base import Session
from browserbout.config import Config
from browserbout.models import MetricValue, Mode
from browserbout.suites.base import Suite, SuiteContext, attempt, load, metric

ASSETS = Path(str(resources.files("browserbout") / "assets"))

# Resource Timing only lists requests that actually happened, so blocked trackers don't
# appear. Cross-origin iframe requests aren't visible, and the buffer holds 250 entries by
# default; both limits apply equally to every browser.
RESOURCES_JS = "return performance.getEntriesByType('resource').map(e => e.name);"
FINGERPRINT_JS = "const done = arguments[arguments.length - 1]; window.__fingerprint.then(done);"

_MULTI_PART_SUFFIXES = {"co", "com", "org", "net", "ac", "gov", "edu"}


class TrackerList:
    def __init__(self, lines: list[str]) -> None:
        self.domains: set[str] = set()
        self.path_rules: list[tuple[str, str]] = []
        for raw in lines:
            line = raw.split("#", 1)[0].strip().lower()
            if not line:
                continue
            host, _, path = line.partition("/")
            if path:
                self.path_rules.append((host, "/" + path))
            else:
                self.domains.add(host)

    @classmethod
    def bundled(cls) -> TrackerList:
        return cls((ASSETS / "trackers.txt").read_text().splitlines())

    @staticmethod
    def _host_matches(host: str, domain: str) -> bool:
        return host == domain or host.endswith("." + domain)

    def match(self, url: str) -> str | None:
        """Return the tracker rule a URL matches, or None."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        labels = host.split(".")
        for i in range(len(labels) - 1):
            candidate = ".".join(labels[i:])
            if candidate in self.domains:
                return candidate
        for rule_host, prefix in self.path_rules:
            if self._host_matches(host, rule_host) and parts.path.startswith(prefix):
                return rule_host + prefix
        return None


def site_domain(url: str) -> str:
    """Approximate registrable domain (e.g. news.bbc.co.uk -> bbc.co.uk)."""
    labels = (urlsplit(url).hostname or "").lower().split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _MULTI_PART_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


@contextlib.contextmanager
def serve_assets() -> Iterator[str]:
    """Serve the bundled assets over http://127.0.0.1 (file:// is restricted under automation)."""
    handler = functools.partial(_QuietHandler, directory=str(ASSETS))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


class PrivacySuite(Suite):
    key = "privacy"
    title = "Privacy"
    description = "Tracker requests on real sites and fingerprinting exposure (lower is better)."

    def reps(self, config: Config, mode: Mode) -> int:
        return config.suites.privacy.reps(mode)

    def run(self, session: Session, ctx: SuiteContext) -> list[MetricValue]:
        trackers = self._trackers(session, ctx)
        fingerprint = attempt(session, ctx, "fingerprint", lambda: self._fingerprint(session, ctx))
        return trackers + (fingerprint or [])

    def _trackers(self, session: Session, ctx: SuiteContext) -> list[MetricValue]:
        trackers = TrackerList.bundled()
        seen: dict[str, list[str]] = {}
        results = []
        for site in ctx.config.sites_for(ctx.mode):
            fetch = functools.partial(self._requests, session, site.url, ctx)
            urls = attempt(session, ctx, site.name, fetch)
            if urls is None:
                continue
            own = site_domain(site.url)
            matched = [rule for u in urls if (rule := trackers.match(u))]
            third_party = {site_domain(u) for u in urls if u.startswith("http")} - {own}
            seen[site.name] = sorted(set(matched))
            results += [
                metric("tracker_requests", "Tracker requests (all sites)", "requests",
                       len(matched), higher_is_better=False, item=site.name, aggregate="sum",
                       floor=1),
                metric("third_party_domains", "Third-party domains contacted (all sites)",
                       "domains", len(third_party), higher_is_better=False, item=site.name,
                       aggregate="sum", floor=1),
            ]
            ctx.log(f"{site.name}: {len(matched)} tracker requests, {len(third_party)} 3rd parties")
        ctx.artifacts.setdefault("trackers", {})[ctx.browser] = seen
        return results

    def _requests(self, session: Session, url: str, ctx: SuiteContext) -> list[str]:
        """URLs of every resource the page requested."""
        if not load(session.driver, url, 45):
            ctx.log(f"{url} timed out; counting what loaded")
        time.sleep(ctx.config.suites.privacy.settle_seconds)
        return list(session.driver.execute_script(RESOURCES_JS) or [])

    def _fingerprint(self, session: Session, ctx: SuiteContext) -> list[MetricValue]:
        session.driver.set_script_timeout(30)
        with serve_assets() as base:
            load(session.driver, f"{base}/fingerprint.html", 30)
            attrs: dict[str, Any] = session.driver.execute_async_script(FINGERPRINT_JS)

        # Each exposed surface is a stable, high-entropy signal a tracker can use.
        surfaces = {
            "canvas": not attrs["canvasNoisy"],
            "audio": attrs["audio"] is not None and not attrs["audioNoisy"],
            "webgl_unmasked_gpu": bool(attrs["webglUnmasked"]),
            "device_memory": attrs["deviceMemory"] is not None,
            "ua_high_entropy_hints": bool(attrs["highEntropyHints"]),
        }
        exposed = sum(surfaces.values())
        previous = ctx.artifacts.get("fingerprint", {}).get(ctx.browser)
        if previous is not None:
            # Informational only (needs a second rep): an identical fingerprint in a brand-new
            # session means it can be used to re-identify you.
            attrs["stableAcrossSessions"] = previous["fingerprint"] == attrs["fingerprint"]
        ctx.artifacts.setdefault("fingerprint", {})[ctx.browser] = {**attrs, "surfaces": surfaces}
        ctx.log(f"fingerprint: {exposed}/{len(surfaces)} surfaces exposed, "
                f"{len(attrs['fonts'])} fonts visible")
        return [
            metric("fingerprint_surfaces", "Fingerprinting surfaces exposed", "surfaces",
                   exposed, higher_is_better=False, floor=1),
            metric("fonts_visible", "Installed fonts visible to pages", "fonts",
                   len(attrs["fonts"]), higher_is_better=False, floor=1),
        ]
