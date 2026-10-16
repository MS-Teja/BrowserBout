import pytest

from browserbout.suites.speed import BENCHMARKS, parse_score


def test_parse_score() -> None:
    assert parse_score("25.4") == 25.4
    assert parse_score(" 1,234.5 ") == 1234.5
    assert parse_score("Score: 310.12") == 310.12
    with pytest.raises(ValueError):
        parse_score("Error")


def test_benchmarks_defined() -> None:
    assert set(BENCHMARKS) == {"speedometer", "jetstream", "motionmark"}
    assert all(b.url.startswith("https://browserbench.org/") for b in BENCHMARKS.values())
