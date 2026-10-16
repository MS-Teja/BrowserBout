"""macOS power helpers: battery state via ioreg/pmset, and keeping the Mac awake."""

from __future__ import annotations

import contextlib
import plistlib
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass
class BatteryState:
    percent: float
    current_mah: float
    max_mah: float
    on_ac: bool
    # Instantaneous draw from the battery in watts (0 when charging or unknown).
    discharge_watts: float


def _signed64(value: int) -> int:
    """ioreg prints negative amperage as an unsigned 64-bit integer."""
    return value - 2**64 if value >= 2**63 else value


def read_battery() -> BatteryState | None:
    """Read AppleSmartBattery from the IORegistry; None on Macs without a battery."""
    try:
        out = subprocess.run(
            ["ioreg", "-arn", "AppleSmartBattery"], capture_output=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    if not out.strip():
        return None
    entries = plistlib.loads(out)
    if not entries:
        return None
    b = entries[0]
    data = b.get("BatteryData", {})
    # Apple Silicon reports Current/MaxCapacity as percentages; real mAh live elsewhere.
    max_mah = float(
        b.get("AppleRawMaxCapacity") or data.get("FullChargeCapacity") or b.get("MaxCapacity", 0)
    )
    current_mah = float(
        b.get("AppleRawCurrentCapacity")
        or data.get("RemainingCapacity")
        or b.get("CurrentCapacity", 0)
    )
    percent = float(b.get("CurrentCapacity", 0))
    if percent > 100 and max_mah:
        percent = current_mah / max_mah * 100
    amperage_ma = _signed64(int(b.get("InstantAmperage", b.get("Amperage", 0))))
    voltage_mv = float(b.get("Voltage", 0))
    discharge_watts = max(0.0, -amperage_ma * voltage_mv / 1e6)
    return BatteryState(
        percent=percent,
        current_mah=current_mah,
        max_mah=max_mah,
        on_ac=bool(b.get("ExternalConnected", False)),
        discharge_watts=discharge_watts,
    )


def power_source() -> str:
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout
    except OSError:
        return "unknown"
    match = re.search(r"drawing from '([^']+)'", out)
    return match.group(1) if match else "unknown"


def low_power_mode() -> bool:
    try:
        out = subprocess.run(["pmset", "-g"], capture_output=True, text=True).stdout
    except OSError:
        return False
    match = re.search(r"lowpowermode\s+(\d)", out)
    return bool(match and match.group(1) == "1")


@contextlib.contextmanager
def keep_awake() -> Iterator[None]:
    """Prevent display/system sleep for the duration of a run."""
    try:
        proc = subprocess.Popen(["caffeinate", "-dims"])
    except OSError:
        yield
        return
    try:
        yield
    finally:
        proc.terminate()
