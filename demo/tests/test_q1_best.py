"""Question 1 analytics on synthetic teams with hand-checkable expectations."""

from __future__ import annotations

from football_insights.analytics import q1_best
from football_insights.analytics.context import ToolContext
from helpers import Economy, M, make_store


def fact_values(result):  # type: ignore[no-untyped-def]
    return {fact.id: fact.value for fact in result.facts}


def test_peak_rating_uses_post_match_rating_after_threshold() -> None:
    ctx = ToolContext(make_store([M("2000-01-01", "Avalon", "Borealis", 1, 0, neutral=True)]))

    result = q1_best.peak(ctx, min_matches_before_peak=0)

    assert result.table is not None
    assert result.table.rows[0][:4] == [1, "Avalon", 1510, "2000-01-01"]
    assert fact_values(result)["q1.peak.1.rating"] == 1510
    assert "q1.params.start_rating" in result.evidence_ids


def test_peak_returns_valid_insufficient_result() -> None:
    ctx = ToolContext(make_store([M("2000-01-01", "Avalon", "Borealis", 1, 0, neutral=True)]))

    result = q1_best.peak(ctx, min_matches_before_peak=2)

    assert result.chart is None
    assert "No team has more than 2 matches" in result.headline
    assert result.tool == "best_team"


def test_career_average_uses_year_end_ratings() -> None:
    ctx = ToolContext(make_store([M("2000-01-01", "Avalon", "Borealis", 1, 0, neutral=True)]))

    result = q1_best.career_average(ctx, min_active_years=1)

    assert result.table is not None
    assert result.table.rows[0] == [1, "Avalon", 1510, 1]
    assert fact_values(result)["q1.career_average.1.rating"] == 1510


def test_time_at_top_counts_year_end_leaders() -> None:
    ctx = ToolContext(make_store([M("2000-01-01", "Avalon", "Borealis", 1, 0, neutral=True)]))

    result = q1_best.time_at_top(ctx)

    assert result.table is not None
    assert result.table.rows[0] == [1, "Avalon", 1, 1]
    assert fact_values(result)["q1.time_at_top.1.first_years"] == 1


def test_records_rank_by_win_rate_then_tie_breakers() -> None:
    ctx = ToolContext(make_store([
        M("2000-01-01", "Avalon", "Borealis", 1, 0, neutral=True),
        M("2000-01-02", "Cascadia", "Dunmore", 1, 0, neutral=True),
    ]))

    result = q1_best.records(ctx, min_matches=1)

    assert result.table is not None
    assert [row[1] for row in result.table.rows[:2]] == ["Avalon", "Cascadia"]
    assert fact_values(result)["q1.records.1.win_rate"] == 100.0
    assert fact_values(result)["q1.records.1.points_per_match"] == 3.0


def test_wins_per_million_uses_latest_population_and_excludes_shared_mapping() -> None:
    ctx = ToolContext(make_store(
        [
            M("2000-01-01", "Avalon", "Borealis", 1, 0, neutral=True),
            M("2000-01-02", "Dunmore", "Avalon", 3, 0, neutral=True),
        ],
        economies={
            "Avalon": Economy("XAV", "North", "High income", indicators={("SP.POP.TOTL", 2010): 4_000_000}),
            "Borealis": Economy("XBO", "North", "High income", indicators={("SP.POP.TOTL", 2020): 1_000_000}),
            "Dunmore": Economy(
                "XDU",
                "North",
                "High income",
                mapping="shared",
                indicators={("SP.POP.TOTL", 2020): 1_000_000},
            ),
        },
    ))

    result = q1_best.wins_per_million(ctx, min_matches=1)

    assert result.table is not None
    assert [row[1] for row in result.table.rows] == ["Avalon", "Borealis"]
    assert result.table.rows[0][4:7] == [2010, 4.0, 0.25]
    assert "novelty" in result.title.lower()


def test_run_validates_params_object() -> None:
    ctx = ToolContext(make_store([M("2000-01-01", "Avalon", "Borealis", 1, 0, neutral=True)]))

    result = q1_best.run(ctx, q1_best.Params(lens="peak"))

    assert result.view == "peak"
