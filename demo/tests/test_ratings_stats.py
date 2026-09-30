"""Rating model and statistics helpers, checked against hand-computed values."""

from __future__ import annotations

import pytest

from football_insights.analytics import ratings, stats


def test_expected_score_and_margin_multiplier() -> None:
    assert ratings.expected(0) == pytest.approx(0.5)
    assert ratings.expected(100) == pytest.approx(0.640065, abs=1e-6)
    assert [ratings.margin_multiplier(m) for m in (0, 1, -1, 2, 3, 5)] == [1.0, 1.0, 1.0, 1.5, 1.75, 2.0]


def test_two_matches_by_hand() -> None:
    # Match 1: A hosts B, friendly (K=20), 2-0. E_home = 0.640065; delta = 20 * 1.5 * 0.359935 = 10.798.
    # Match 2: B v A neutral, World Cup (K=60), 1-1. 10^(21.596/400) = 1.132376, so E_B = 0.468961;
    #          delta = 60 * 1.0 * (0.5 - 0.468961) = 1.8624.
    history = ratings.compute([
        ratings.MatchInput(1, 2000, "A", "B", 2, 0, False, 20),
        ratings.MatchInput(2, 2001, "B", "A", 1, 1, True, 60),
    ])
    first, second = history.matches
    assert first.home_post == pytest.approx(1510.798, abs=0.01)
    assert first.away_post == pytest.approx(1489.202, abs=0.01)
    assert second.expected_home == pytest.approx(0.468961, abs=1e-5)
    assert history.current["B"] == pytest.approx(1491.064, abs=0.01)
    assert history.current["A"] == pytest.approx(1508.936, abs=0.01)
    assert history.year_end["A"] == {2000: pytest.approx(1510.798, abs=0.01), 2001: pytest.approx(1508.936, abs=0.01)}
    # Neutral expectation ignores home advantage.
    assert first.expected_home_neutral == pytest.approx(0.5)


def test_ratings_are_zero_sum() -> None:
    history = ratings.compute([
        ratings.MatchInput(i, 2000 + i, h, a, hs, as_, n, 40)
        for i, (h, a, hs, as_, n) in enumerate([("A", "B", 3, 1, False), ("C", "A", 0, 0, True),
                                                 ("B", "C", 1, 4, False)])
    ])
    assert sum(history.current.values()) == pytest.approx(3 * ratings.START)


def test_active_teams_window() -> None:
    history = ratings.compute([ratings.MatchInput(1, 1990, "A", "B", 1, 0, True, 20),
                               ratings.MatchInput(2, 1995, "A", "C", 1, 0, True, 20)])
    assert set(ratings.active_teams(history, 1995)) == {"A", "C"}
    assert set(ratings.active_teams(history, 1992)) == {"A", "B"}


def test_wilson_interval_known_value() -> None:
    share, low, high = stats.wilson(2, 4)
    assert (round(share, 1), round(low, 1), round(high, 1)) == (50.0, 15.0, 85.0)
    assert stats.wilson(0, 0) == (0.0, 0.0, 0.0)


def test_percentile_stdev_spearman() -> None:
    assert stats.percentile([1, 2, 3, 4], 50) == 2.5
    assert stats.percentile([10], 90) == 10
    assert stats.stdev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.13809, abs=1e-5)
    assert stats.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert stats.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_bootstrap_is_deterministic_and_brackets_the_mean() -> None:
    values = [0.1, 0.4, -0.2, 0.3, 0.0, 0.5, -0.1]
    first = stats.bootstrap_mean(values)
    assert first == stats.bootstrap_mean(values)
    mean, low, high = first
    assert low <= mean <= high
    diff, dlow, dhigh = stats.bootstrap_difference([1.0, 1.2, 0.9], [0.1, 0.0, 0.2])
    assert diff == pytest.approx(0.9333, abs=1e-4)
    assert dlow <= diff <= dhigh
