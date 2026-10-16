"""Memory and CPU sampling across a browser's process tree."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass

import psutil

MB = 1024 * 1024


@dataclass
class ResourceSample:
    memory_mb: float
    cpu_percent: float
    process_count: int


def memory_mb(procs: list[psutil.Process]) -> float:
    """Sum of unique set size (USS) — memory freed if the browser quit. Falls back to RSS."""
    total = 0
    for p in procs:
        try:
            try:
                total += p.memory_full_info().uss
            except psutil.AccessDenied:
                total += p.memory_info().rss
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return total / MB


def sample(get_procs: Callable[[], list[psutil.Process]], seconds: float) -> ResourceSample:
    """Measure total CPU% (100 = one core) over `seconds`, then current memory."""
    # psutil keeps the CPU baseline on the Process *object*, so the second reading must use
    # the same objects; get_procs() may return fresh ones (e.g. Process.children()).
    baseline = {p.pid: p for p in get_procs()}
    for p in baseline.values():
        with contextlib.suppress(psutil.Error):
            p.cpu_percent(None)
    time.sleep(seconds)
    procs_after = get_procs()
    cpu = 0.0
    for p in procs_after:
        try:
            # Processes that appeared mid-sample have no baseline; they're not counted.
            if p.pid in baseline:
                cpu += baseline[p.pid].cpu_percent(None)
        except psutil.Error:
            continue
    return ResourceSample(
        memory_mb=memory_mb(procs_after), cpu_percent=cpu, process_count=len(procs_after)
    )
