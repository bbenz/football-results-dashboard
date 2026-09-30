"""Question 3 tools on synthetic data, with expectations computed by hand.

Non-neutral synthetic matches by decade:
  1900s: 2-0 H, 1-1 D, 0-3 A, 4-1 H              -> n=4, home 50.0%, draw 25.0%, away 25.0%, GD (2+0-3+3)/4 = 0.5
  2010s: 1-0 H, 2-2 D, 0-2 A, 1-0 H, 1-1 D, 0-1 A -> n=6, 33.3% each, GD (1+0-2+1+0-1)/6 = -0.17
  2020s: 2-2 D                                    -> n=1
Goals per match, all matches: 1900s 14/5 = 2.8; 2010s 15/7 = 2.14; 2020s 4/1 = 4.0.
"""

from __future__ import annotations

from football_insights.analytics import q3_trends
from football_insights.analytics.registry import function_tools, run_tool


def facts(result):  # type: ignore[no-untyped-def]
    return {f.id: f.value for f in result.facts}


def test_home_advantage_by_decade(ctx) -> None:  # type: ignore[no-untyped-def]
    result = q3_trends.home_advantage(ctx, min_matches=2)
    f = facts(result)
    assert f["q3.home.1900s.home_win_pct"] == 50.0
    assert f["q3.home.2010s.home_win_pct"] == 33.3
    assert f["q3.home.change_pts"] == -16.7
    assert f["q3.home.all.home_win_pct"] == 40.0
    assert f["q3.home.matches"] == 10
    rows = {r[0]: r for r in result.table.rows}
    assert rows["1900s"][1:5] == [4, 50.0, 25.0, 25.0]
    assert rows["1900s"][6] == 0.5
    assert rows["2010s"][6] == -0.17
    assert "2020s" not in rows
    assert any("fewer than 2" in c and "2020s" in c for c in result.coverage)


def test_home_advantage_keeps_small_decades_when_allowed(ctx) -> None:  # type: ignore[no-untyped-def]
    result = q3_trends.home_advantage(ctx, min_matches=1)
    f = facts(result)
    assert f["q3.home.2020s.home_win_pct"] == 0.0
    assert f["q3.home.change_pts"] == -50.0
    assert f["q3.home.matches"] == 11


def test_home_advantage_chart_has_interval_band_and_summary(ctx) -> None:  # type: ignore[no-untyped-def]
    chart = q3_trends.home_advantage(ctx, min_matches=2).chart
    assert chart is not None
    assert chart.x == ["1900s", "2010s"]
    home = chart.series[0]
    assert home.lower is not None and home.upper is not None
    assert all(lo <= v <= hi for lo, v, hi in zip(home.lower, home.values, home.upper, strict=True))
    assert "1900s" in chart.summary and "2010s" in chart.summary


def test_goals_per_match(ctx) -> None:  # type: ignore[no-untyped-def]
    result = q3_trends.goals_per_match(ctx, min_matches=1, split_min=1)
    f = facts(result)
    assert f["q3.goals.1900s"] == 2.8
    assert f["q3.goals.2020s"] == 4.0
    assert f["q3.goals.2010s.low"] == 2.14
    assert f["q3.goals.2020s.peak"] == 4.0
    assert f["q3.goals.all"] == round(33 / 13, 2)
    rows = {r[0]: r for r in result.table.rows}
    assert rows["2010s"][1:3] == [7, 2.14]


def test_registry_validates_arguments_and_caches(ctx) -> None:  # type: ignore[no-untyped-def]
    import pytest

    from football_insights.analytics.registry import ToolError

    first = run_tool(ctx, "trends", {"metric": "goals_per_match"})
    assert run_tool(ctx, "trends", {"metric": "goals_per_match"}) is first
    with pytest.raises(ToolError):
        run_tool(ctx, "trends", {"metric": "possession"})
    with pytest.raises(ToolError):
        run_tool(ctx, "trends", {"metric": "home_advantage", "extra": 1})
    with pytest.raises(ToolError):
        run_tool(ctx, "shell", {})


def test_function_tool_schemas_are_strict() -> None:
    for tool in function_tools():
        params = tool["parameters"]
        assert tool["strict"] is True
        assert params["additionalProperties"] is False
        assert set(params["required"]) == set(params["properties"])
