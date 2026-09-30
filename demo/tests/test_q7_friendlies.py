"""Synthetic tests for question 7 friendly-match activity."""

from __future__ import annotations

from football_insights.analytics import q7_friendlies
from football_insights.analytics.context import ToolContext
from helpers import Economy, M, make_store


def test_leaders_counts_friendly_like_share_and_breaks_ties_by_team() -> None:
    store = make_store(
        [
            M("2000-01-01", "Borealis", "Dunmore", 0, 0, "Friendly"),
            M("2000-01-02", "Avalon", "Elbaria", 0, 0, "Friendly"),
            M("2000-01-03", "Avalon", "Borealis", 0, 0, "FIFA World Cup qualification"),
            M("2000-01-04", "Cascadia", "Fenwick", 0, 0, "Friendly"),
        ]
    )
    result = q7_friendlies.leaders(
        ToolContext(store),
        q7_friendlies.Params(view="leaders", era=None),
        all_time_min_matches=1,
    )

    assert result.table is not None
    # Avalon and Borealis have one friendly-like match each; alphabetical order is the deterministic tie-breaker.
    assert result.table.rows[0][0] == "Avalon"
    assert result.table.rows[0][1] == 1
    assert result.table.rows[0][3] == 50.0
    assert result.evidence_ids[:2] == ["q7.leaders.1.friendlies", "q7.leaders.1.share"]


def test_effect_uses_four_year_windows_and_rank_based_terciles() -> None:
    # Draws between equal-rated teams give next-window actual-minus-expected values of zero by hand.
    store = make_store(
        [
            M("1946-01-01", "Avalon", "Dunmore", 0, 0, "FIFA World Cup qualification", neutral=True),
            M("1946-01-02", "Borealis", "Dunmore", 0, 0, "Friendly", neutral=True),
            M("1946-01-03", "Cascadia", "Dunmore", 0, 0, "Friendly", neutral=True),
            M("1947-01-03", "Cascadia", "Dunmore", 0, 0, "Friendly", neutral=True),
            M("1950-01-01", "Avalon", "Dunmore", 0, 0, "FIFA World Cup qualification", neutral=True),
            M("1950-01-02", "Borealis", "Dunmore", 0, 0, "FIFA World Cup qualification", neutral=True),
            M("1950-01-03", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup qualification", neutral=True),
            M("1953-01-01", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup qualification", neutral=True),
        ]
    )
    result = q7_friendlies.effect(
        ToolContext(store),
        q7_friendlies.Params(view="effect", era=None),
        min_next_competitive=1,
    )

    assert result.table is not None
    assert result.table.rows == [["Low", 2, 0.0], ["Middle", 1, 0.0], ["High", 1, 0.0]]
    assert result.facts[0].id == "q7.effect.diff"
    assert result.facts[0].value == 0.0
    assert result.facts[4].value == 4


def test_by_income_counts_friendlies_per_team_year_and_unmapped_share() -> None:
    store = make_store(
        [
            M("1960-01-01", "Avalon", "Borealis", 0, 0, "Friendly"),
            M("1960-01-02", "Avalon", "Cascadia", 0, 0, "Friendly"),
            M("1961-01-01", "Borealis", "Cascadia", 0, 0, "FIFA World Cup qualification"),
        ],
        economies={
            "Avalon": Economy("XAV", "North", "High income"),
            "Borealis": Economy("XBO", "South", "Low income"),
        },
    )
    result = q7_friendlies.by_income(ToolContext(store), q7_friendlies.Params(view="by_income", era=None))

    assert result.table is not None
    assert result.table.rows[0] == ["High income", 1, 2, 2.0]
    assert result.table.rows[1] == ["Low income", 2, 1, 0.5]
    assert result.facts[0].id == "q7.by_income.unmapped_share"
    assert result.facts[0].value == 40.0


def test_leaders_insufficient_data_returns_valid_result() -> None:
    store = make_store([M("2000-01-01", "Avalon", "Borealis", 0, 0, "Friendly")])
    result = q7_friendlies.leaders(
        ToolContext(store),
        q7_friendlies.Params(view="leaders", era="current"),
        all_time_min_matches=100,
    )

    assert result.chart is None
    assert "No teams met" in result.headline
    assert result.evidence_ids == ["q7.leaders.minimum", "q7.leaders.teams"]
