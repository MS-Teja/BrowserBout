"""Suite registry, in the order suites run."""

from __future__ import annotations

from browserbout.suites.base import Suite
from browserbout.suites.battery import BatterySuite
from browserbout.suites.pageload import PageLoadSuite
from browserbout.suites.privacy import PrivacySuite
from browserbout.suites.resources import ResourcesSuite
from browserbout.suites.speed import SpeedSuite
from browserbout.suites.stability import StabilitySuite

SUITES: dict[str, type[Suite]] = {
    cls.key: cls
    for cls in (SpeedSuite, PageLoadSuite, ResourcesSuite, PrivacySuite, StabilitySuite,
                BatterySuite)
}


def get_suites(keys: list[str] | None) -> list[Suite]:
    if not keys or keys == ["all"]:
        return [cls() for cls in SUITES.values()]
    unknown = [k for k in keys if k not in SUITES]
    if unknown:
        raise ValueError(f"Unknown suite(s): {', '.join(unknown)}. Available: {', '.join(SUITES)}")
    # Keep the canonical order regardless of how they were listed.
    return [cls() for key, cls in SUITES.items() if key in keys]
