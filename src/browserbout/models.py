"""Data models for benchmark results (this is the schema of results/*.json)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Mode = Literal["quick", "full"]
Aggregate = Literal["geomean", "mean", "sum"]


class MetricValue(BaseModel):
    """A single number a suite measured in one repetition."""

    name: str
    label: str
    unit: str
    higher_is_better: bool
    value: float
    # Per-item metrics (e.g. one value per site) are combined across the items every browser
    # completed, using `aggregate`, before scoring.
    item: str | None = None
    aggregate: Aggregate = "geomean"
    # Informational metrics are reported but don't count towards the score.
    scored: bool = True
    # Differences below this size are noise: scoring compares (value + floor) ratios, so
    # 0.1% vs 0.5% idle CPU doesn't read as "5x better".
    floor: float = 0


class Measurement(MetricValue):
    browser: str
    suite: str
    rep: int


class BrowserInfo(BaseModel):
    key: str
    name: str
    version: str
    engine: str
    engine_version: str | None = None


class MachineInfo(BaseModel):
    model: str
    chip: str
    memory_gb: float
    os_version: str
    power_source: str


class RunError(BaseModel):
    browser: str
    suite: str
    rep: int
    message: str


class Run(BaseModel):
    id: str
    mode: Mode
    started_at: datetime
    finished_at: datetime | None = None
    machine: MachineInfo
    browsers: list[BrowserInfo]
    suites: list[str]
    measurements: list[Measurement] = Field(default_factory=list)
    errors: list[RunError] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # Free-form extra data, e.g. raw fingerprint attributes per browser.
    artifacts: dict[str, Any] = Field(default_factory=dict)
