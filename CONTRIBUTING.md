# Contributing

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests && mypy && pytest
```

Unit tests use fake browsers and synthetic runs, so they don't need Safari or Vivaldi.

## Adding a browser

1. Create `src/browserbout/browsers/<name>.py`:

```python
from pathlib import Path

import psutil
from selenium import webdriver

from browserbout.browsers.base import Browser
from browserbout.config import Window


class Chrome(Browser):
    key = "chrome"
    name = "Chrome"
    engine = "Blink"
    app_path = Path("/Applications/Google Chrome.app")
    app_process_names = ("Google Chrome",)

    def create_driver(self, window: Window):
        opts = webdriver.ChromeOptions()
        opts.add_argument("--user-data-dir=/tmp/bout-chrome")  # clean profile
        return webdriver.Chrome(options=opts)

    def processes(self, driver) -> list[psutil.Process]:
        # Every OS process that belongs to this browser instance.
        return psutil.Process(driver.service.process.pid).children(recursive=True)
```

2. Register it in `browsers/registry.py`. The order of the registry also fixes the browser's colour in the
   dashboard.
3. `bout doctor --browsers chrome` and then `bout run --browsers safari,vivaldi,chrome`.

## Adding a test suite

Subclass `Suite` in `src/browserbout/suites/`, return a list of `metric(...)` values from `run()`, and register
it in `suites/registry.py`. Add its weight to `config/weights.yaml`. Useful flags on `metric()`:

- `higher_is_better`: the direction of the metric
- `item="site-name"`: per-item values, which scoring combines over items every browser completed (`aggregate`
  can be `"geomean"`, `"mean"` or `"sum"`)
- `scored=False`: shown in reports, not counted in the score
- `floor`: differences smaller than this are treated as noise
