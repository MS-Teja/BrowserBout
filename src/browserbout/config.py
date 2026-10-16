"""Loading and validating the YAML configuration in config/."""

from __future__ import annotations

from pathlib import Path
from typing import Generic, TypeVar

import yaml
from pydantic import BaseModel, Field

from browserbout.models import Mode

T = TypeVar("T")


class PerMode(BaseModel, Generic[T]):
    quick: T
    full: T

    def __call__(self, mode: Mode) -> T:
        return self.quick if mode == "quick" else self.full


class Window(BaseModel):
    width: int = 1440
    height: int = 900


class SpeedConfig(BaseModel):
    reps: PerMode[int] = PerMode(quick=1, full=3)
    benchmarks: list[str] = ["speedometer", "jetstream", "motionmark"]
    timeout_seconds: int = 1200


class PageLoadConfig(BaseModel):
    reps: PerMode[int] = PerMode(quick=1, full=5)
    settle_seconds: float = 2
    timeout_seconds: int = 45


class ResourcesConfig(BaseModel):
    reps: PerMode[int] = PerMode(quick=1, full=3)
    tabs: PerMode[int] = PerMode(quick=5, full=10)
    idle_seconds: PerMode[float] = PerMode(quick=5, full=20)
    sample_seconds: float = 5


class PrivacyConfig(BaseModel):
    reps: PerMode[int] = PerMode(quick=1, full=3)
    settle_seconds: float = 3


class StabilityConfig(BaseModel):
    reps: PerMode[int] = PerMode(quick=1, full=1)
    tabs: PerMode[int] = PerMode(quick=6, full=20)
    duration_minutes: PerMode[float] = PerMode(quick=1, full=15)
    hang_threshold_seconds: float = 5


class BatteryConfig(BaseModel):
    reps: PerMode[int] = PerMode(quick=0, full=1)
    duration_minutes: PerMode[float] = PerMode(quick=5, full=30)
    video_url: str = (
        "https://www.youtube.com/embed/aqz-KE-bpKQ?autoplay=1&mute=1&loop=1&playlist=aqz-KE-bpKQ"
    )
    video_share: float = Field(default=0.5, ge=0, le=1)


class SuitesConfig(BaseModel):
    speed: SpeedConfig = SpeedConfig()
    pageload: PageLoadConfig = PageLoadConfig()
    resources: ResourcesConfig = ResourcesConfig()
    privacy: PrivacyConfig = PrivacyConfig()
    stability: StabilityConfig = StabilityConfig()
    battery: BatteryConfig = BatteryConfig()


class Site(BaseModel):
    name: str
    url: str


class Config(BaseModel):
    window: Window = Window()
    cooldown_seconds: PerMode[float] = PerMode(quick=2, full=20)
    site_limit: PerMode[int | None] = PerMode(quick=5, full=None)
    suites: SuitesConfig = SuitesConfig()
    sites: list[Site] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)

    def sites_for(self, mode: Mode) -> list[Site]:
        limit = self.site_limit(mode)
        return self.sites if limit is None else self.sites[:limit]


def _read_yaml(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_config(config_dir: Path) -> Config:
    """Merge default.yaml, sites.yaml and weights.yaml from config_dir."""
    data = _read_yaml(config_dir / "default.yaml")
    data["sites"] = _read_yaml(config_dir / "sites.yaml").get("sites", [])
    data["weights"] = _read_yaml(config_dir / "weights.yaml").get("weights", {})
    return Config.model_validate(data)
