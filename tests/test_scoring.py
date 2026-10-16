from conftest import make_run, measurement

from browserbout.models import Run
from browserbout.scoring import build_scorecard

WEIGHTS = {"speed": 50, "pageload": 30, "resources": 20}


def _metric(card, suite: str, name: str):  # type: ignore[no-untyped-def]
    cat = next(c for c in card.categories if c.suite == suite)
    return next(m for m in cat.metrics if m.name == name)


def test_higher_is_better_metric(sample_run: Run) -> None:
    card = build_scorecard(sample_run, WEIGHTS)
    speedometer = _metric(card, "speed", "speedometer")
    assert speedometer.winner == "safari"
    assert speedometer.scores["safari"] == 100
    assert round(speedometer.scores["vivaldi"], 2) == round(450 / 510 * 100, 2)
    # Three reps with non-overlapping IQRs.
    assert speedometer.confidence == "high"


def test_lower_is_better_metric(sample_run: Run) -> None:
    card = build_scorecard(sample_run, WEIGHTS)
    memory = _metric(card, "resources", "idle_memory")
    assert memory.winner == "safari"
    assert memory.scores == {"safari": 100, "vivaldi": 50}
    assert memory.confidence is None  # single rep


def test_items_are_aggregated_with_geomean(sample_run: Run) -> None:
    card = build_scorecard(sample_run, WEIGHTS)
    load = _metric(card, "pageload", "cold_load")
    assert load.item is None
    assert load.items_compared == 2
    assert round(load.stats["safari"].median) == round((800 * 2000) ** 0.5)
    assert round(load.stats["vivaldi"].median) == round((1000 * 1800) ** 0.5)
    assert {r.item for r in card.items} == {"google", "leetcode"}


def test_unscored_metrics_do_not_count(sample_run: Run) -> None:
    card = build_scorecard(sample_run, WEIGHTS)
    resources = next(c for c in card.categories if c.suite == "resources")
    # Only idle_memory is scored, so the category equals that metric's scores.
    assert resources.scores == {"safari": 100, "vivaldi": 50}


def test_overall_is_weighted_mean(sample_run: Run) -> None:
    card = build_scorecard(sample_run, WEIGHTS)
    expected = sum(
        c.scores["vivaldi"] * WEIGHTS[c.suite] for c in card.categories
    ) / sum(WEIGHTS.values())
    assert round(card.overall["vivaldi"], 6) == round(expected, 6)
    assert card.winner == "safari"
    assert round(sum(card.weights.values())) == 100


def test_missing_categories_renormalise_weights() -> None:
    run = make_run([
        measurement("safari", "speed", "x", 10, higher_is_better=True),
        measurement("vivaldi", "speed", "x", 5, higher_is_better=True),
    ])
    card = build_scorecard(run, {"speed": 25, "battery": 75})
    assert card.weights == {"speed": 100}
    assert card.overall == {"safari": 100, "vivaldi": 50}


def test_sites_missing_for_one_browser_are_excluded() -> None:
    run = make_run([
        measurement("safari", "pageload", "cold_load", 100, item="a"),
        measurement("vivaldi", "pageload", "cold_load", 100, item="a"),
        # Vivaldi timed out on b, so b must not count against (or for) either browser.
        measurement("safari", "pageload", "cold_load", 9000, item="b"),
    ])
    card = build_scorecard(run, {"pageload": 1})
    load = card.categories[0].metrics[0]
    assert load.items_compared == 1
    assert load.winner is None  # tie on the only common site


def test_floor_dampens_tiny_differences() -> None:
    run = make_run([
        measurement("safari", "stability", "crashes", 0, floor=1),
        measurement("vivaldi", "stability", "crashes", 1, floor=1),
        measurement("safari", "resources", "idle_cpu", 0.1, floor=5),
        measurement("vivaldi", "resources", "idle_cpu", 0.5, floor=5),
    ])
    card = build_scorecard(run, {"stability": 1, "resources": 1})
    assert _metric(card, "stability", "crashes").scores["vivaldi"] == 50
    assert _metric(card, "resources", "idle_cpu").scores["vivaldi"] > 90


def test_sum_aggregate_and_zero_values() -> None:
    run = make_run([
        measurement("safari", "privacy", "trackers", 0, item="a", aggregate="sum", floor=1),
        measurement("safari", "privacy", "trackers", 0, item="b", aggregate="sum", floor=1),
        measurement("vivaldi", "privacy", "trackers", 2, item="a", aggregate="sum", floor=1),
        measurement("vivaldi", "privacy", "trackers", 1, item="b", aggregate="sum", floor=1),
    ])
    card = build_scorecard(run, {"privacy": 1})
    trackers = card.categories[0].metrics[0]
    assert trackers.stats["vivaldi"].median == 3
    assert trackers.scores == {"safari": 100, "vivaldi": 25}


def test_near_equal_scores_are_a_tie() -> None:
    run = make_run([
        measurement("safari", "speed", "x", 1000, higher_is_better=True),
        measurement("vivaldi", "speed", "x", 999, higher_is_better=True),
    ])
    card = build_scorecard(run, {"speed": 1})
    assert card.winner is None
