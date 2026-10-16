from pathlib import Path

from browserbout.config import Config, PerMode, load_config

REPO_CONFIG = Path(__file__).parent.parent / "config"


def test_repo_config_loads() -> None:
    config = load_config(REPO_CONFIG)
    assert any(site.name == "leetcode" for site in config.sites)
    assert config.weights["speed"] > 0
    assert config.suites.battery.reps("quick") == 0
    assert config.suites.battery.reps("full") >= 1


def test_sites_for_mode() -> None:
    config = load_config(REPO_CONFIG)
    assert len(config.sites_for("quick")) == config.site_limit("quick")
    assert config.sites_for("full") == config.sites


def test_missing_files_fall_back_to_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config == Config()


def test_per_mode() -> None:
    assert PerMode[int](quick=1, full=5)("full") == 5
