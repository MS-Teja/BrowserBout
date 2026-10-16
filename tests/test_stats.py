from browserbout import stats


def test_median_and_iqr() -> None:
    assert stats.median([3, 1, 2]) == 2
    assert stats.iqr([5]) == (5, 5)
    q1, q3 = stats.iqr([1, 2, 3, 4, 5])
    assert (q1, q3) == (2, 4)


def test_geomean_ignores_non_positive() -> None:
    assert round(stats.geomean([2, 8]), 6) == 4
    assert stats.geomean([0, 4]) == 4
    assert stats.geomean([]) == 0


def test_percentile_nearest_rank() -> None:
    values = list(range(1, 101))
    assert stats.percentile(values, 95) == 95
    assert stats.percentile([], 95) == 0


def test_slope() -> None:
    assert stats.slope([0, 1, 2], [10, 12, 14]) == 2
    assert stats.slope([1], [5]) == 0
    assert stats.slope([1, 1], [5, 6]) == 0
