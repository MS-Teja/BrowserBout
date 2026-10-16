"""Describe the machine a run happened on, so results can be compared fairly."""

from __future__ import annotations

import platform
import subprocess

import psutil

from browserbout.metrics.power import power_source
from browserbout.models import MachineInfo


def _sysctl(key: str) -> str:
    try:
        return subprocess.run(
            ["sysctl", "-n", key], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def machine_info() -> MachineInfo:
    return MachineInfo(
        model=_sysctl("hw.model"),
        chip=_sysctl("machdep.cpu.brand_string"),
        memory_gb=round(psutil.virtual_memory().total / 1024**3, 1),
        os_version=f"macOS {platform.mac_ver()[0] or 'unknown'}",
        power_source=power_source(),
    )
