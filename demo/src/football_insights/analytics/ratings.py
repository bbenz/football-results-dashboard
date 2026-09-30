"""The rating model (method version ratings-v1): a transparent Elo-style rating.

Parameters are in docs/METHODS.md: start 1500, home advantage 100, match
importance K from the tournament category, and a goal-margin multiplier.
Ratings use the score after extra time; a penalty shootout does not change the
result. Matches are processed in the data's date order.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

METHOD_VERSION = "ratings-v1"
START = 1500.0
HOME_ADVANTAGE = 100.0


@dataclass(frozen=True)
class MatchInput:
    match_id: int
    year: int
    home: str
    away: str
    home_score: int
    away_score: int
    neutral: bool
    k: int


@dataclass
class RatedMatch:
    match_id: int
    year: int
    home: str
    away: str
    home_pre: float
    away_pre: float
    home_post: float
    away_post: float
    expected_home: float
    expected_home_neutral: float
    actual_home: float


@dataclass
class RatingHistory:
    matches: list[RatedMatch] = field(default_factory=list)
    # team -> year -> rating after the team's last match of that year
    year_end: dict[str, dict[int, float]] = field(default_factory=dict)
    # team -> list of (match_index, rating after the match)
    trajectory: dict[str, list[tuple[int, float]]] = field(default_factory=dict)
    current: dict[str, float] = field(default_factory=dict)

    def by_id(self) -> dict[int, RatedMatch]:
        return {m.match_id: m for m in self.matches}


def expected(rating_diff: float) -> float:
    return 1.0 / (1.0 + 10 ** (-rating_diff / 400.0))


def margin_multiplier(margin: int) -> float:
    margin = abs(margin)
    if margin <= 1:
        return 1.0
    if margin == 2:
        return 1.5
    return (11 + margin) / 8


def compute(matches: Iterable[MatchInput]) -> RatingHistory:
    history = RatingHistory()
    ratings = history.current
    for index, m in enumerate(matches):
        home_pre = ratings.get(m.home, START)
        away_pre = ratings.get(m.away, START)
        advantage = 0.0 if m.neutral else HOME_ADVANTAGE
        e_home = expected(home_pre + advantage - away_pre)
        if m.home_score > m.away_score:
            actual = 1.0
        elif m.home_score < m.away_score:
            actual = 0.0
        else:
            actual = 0.5
        delta = m.k * margin_multiplier(m.home_score - m.away_score) * (actual - e_home)
        ratings[m.home] = home_pre + delta
        ratings[m.away] = away_pre - delta
        history.matches.append(RatedMatch(
            match_id=m.match_id, year=m.year, home=m.home, away=m.away,
            home_pre=home_pre, away_pre=away_pre, home_post=ratings[m.home], away_post=ratings[m.away],
            expected_home=e_home, expected_home_neutral=expected(home_pre - away_pre), actual_home=actual,
        ))
        for team in (m.home, m.away):
            history.year_end.setdefault(team, {})[m.year] = ratings[team]
            history.trajectory.setdefault(team, []).append((index, ratings[team]))
    return history


def active_teams(history: RatingHistory, year: int, window: int = 4) -> dict[str, float]:
    """Teams that played in `year` or the three years before it, with their latest rating by year end."""
    out: dict[str, float] = {}
    for team, years in history.year_end.items():
        played = [y for y in years if year - window < y <= year]
        if played:
            out[team] = years[max(played)]
    return out
