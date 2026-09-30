"""Synthetic tests for question 5 third-party host views."""

from __future__ import annotations

from football_insights.analytics import q5_hosts
from football_insights.analytics.context import ToolContext
from helpers import Economy, M, make_store


def _host_context() -> ToolContext:
    economies = {
        "Avalon": Economy("XAV", "North Region", "High income"),
        "Borealis": Economy("XBO", "North Region", "High income"),
        "Cascadia": Economy("XCA", "South Region", "Upper middle income"),
        "Dunmore": Economy("XDU", "East Region", "Low income"),
        "Elbaria": Economy("XEL", "East Region", "Low income"),
        "Fenwick": Economy("XFE", "West Region", "High income"),
    }
    return ToolContext(make_store([
        M("1999-01-01", "Elbaria", "Fenwick", 1, 0, venue="Elbaria", neutral=False, city="Port Elbaria"),
        M("2000-01-01", "Avalon", "Borealis", 1, 0, venue="Cascadia", neutral=True, city="Lumen"),
        M("2000-02-01", "Avalon", "Borealis", 0, 0, venue="Cascadia", neutral=True, city="Lumen"),
        M("2000-03-01", "Avalon", "Borealis", 2, 1, venue="Dunmore", neutral=True, city="Mere"),
        M("2000-04-01", "Borealis", "Avalon", 1, 1, venue="Dunmore", neutral=True, city="Mere"),
        M("2000-05-01", "Avalon", "Borealis", 3, 0, venue="Elbaria", neutral=True, city="Port Elbaria"),
        M("2000-06-01", "Avalon", "Borealis", 0, 1, venue="Avalon", neutral=True, city="Avalon City"),
        M("2000-07-01", "Avalon", "Borealis", 1, 1, venue="Fenwick", neutral=False, city="Fenwick City"),
        M("2010-01-01", "Cascadia", "Dunmore", 1, 0, venue="Harrowgate", neutral=True, city="Harbor"),
    ], economies=economies))


def test_ranking_counts_third_party_hosts_and_disagreements() -> None:
    ctx = _host_context()

    result = q5_hosts.run(ctx, q5_hosts.Params(view="ranking", era=None))

    assert result.tool == "neutral_hosts"
    assert result.table is not None
    # Cascadia and Dunmore both host two third-party matches; host name breaks the tie.
    assert result.table.rows[:2] == [["Cascadia", 2], ["Dunmore", 2]]
    facts = {fact.id: fact.value for fact in result.facts}
    assert facts["q5.ranking.total_third_party"] == 6
    assert facts["q5.ranking.distinct_hosts"] == 4
    assert facts["q5.ranking.neutral_participant"] == 1
    assert facts["q5.ranking.nonneutral_third_venue"] == 1


def test_trend_uses_wilson_view_and_minimum_sample_override() -> None:
    ctx = _host_context()

    result = q5_hosts.trend(ctx, min_matches=1)

    assert result.table is not None
    row_2000s = next(row for row in result.table.rows if row[0] == "2000s")
    # Five of seven matches in the 2000s are third-party hosted.
    assert row_2000s[1:4] == [7, 5, 71.4]
    assert "q5.trend.matches" in result.evidence_ids
    assert result.chart is not None and result.chart.series[0].lower is not None


def test_cities_counts_city_host_pairs_with_tie_breaker() -> None:
    ctx = _host_context()

    result = q5_hosts.cities(ctx, era=None)

    assert result.table is not None
    assert result.table.rows[0] == ["Lumen", "Cascadia", 2]
    assert result.table.rows[1] == ["Mere", "Dunmore", 2]
    assert "q5.cities.top1" in result.evidence_ids


def test_host_groups_reports_region_income_and_unmapped_share() -> None:
    ctx = _host_context()

    result = q5_hosts.host_groups(ctx)

    assert result.table is not None
    facts = {fact.id: fact.value for fact in result.facts}
    # One of six third-party hosts is Harrowgate, which is not a participating team in the synthetic store.
    assert facts["q5.host_groups.unmapped_share"] == 16.7
    assert ["Cascadia", 2, "South Region", "Upper middle income"] in result.table.rows
    assert result.chart is not None
    assert "q5.host_groups.top_region" in result.evidence_ids


def test_ranking_insufficient_path_has_no_chart() -> None:
    ctx = ToolContext(make_store([M("2000-01-01", "Avalon", "Borealis", 1, 0)]))

    result = q5_hosts.ranking(ctx, era=None)

    assert result.chart is None
    assert result.facts[0].id == "q5.ranking.matches"
