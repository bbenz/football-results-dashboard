"""Synthetic tests for question 4 geopolitics views."""

from __future__ import annotations

from football_insights.analytics import q4_geopolitics
from football_insights.analytics.context import ToolContext
from helpers import Economy, M, make_store


def test_team_counts_reports_peak_latest_full_year_and_evidence_ids() -> None:
    ctx = ToolContext(make_store([
        M("1900-01-01", "Avalon", "Borealis", 1, 0),
        M("1900-02-01", "Avalon", "Cascadia", 0, 0),
        M("1950-01-01", "Dunmore", "Elbaria", 2, 1),
        M("1990-01-01", "Avalon", "Dunmore", 1, 1),
        M("2000-01-01", "Fenwick", "Glenmoor", 3, 0),
        M("2020-08-01", "Avalon", "Borealis", 2, 2),
    ]))

    result = q4_geopolitics.run(ctx, q4_geopolitics.Params(view="team_counts", era=None))

    assert result.tool == "geopolitics"
    assert result.view == "team_counts"
    # Hand count: 1900 has Avalon, Borealis, and Cascadia; no other year has more teams.
    assert "q4.team_counts.peak_count" in result.evidence_ids
    assert result.facts[[f.id for f in result.facts].index("q4.team_counts.peak_count")].value == 3
    assert result.table is not None
    assert ["First appearances", "1900s", 1900, 3, "Teams whose first match falls here"] in result.table.rows


def test_frequent_pairings_uses_unordered_pairs_record_and_tie_breaker() -> None:
    ctx = ToolContext(make_store([
        M("2000-01-01", "Avalon", "Borealis", 1, 0),
        M("2000-02-01", "Borealis", "Avalon", 1, 1),
        M("2000-03-01", "Borealis", "Avalon", 0, 2),
        M("2000-04-01", "Cascadia", "Dunmore", 1, 0),
        M("2000-05-01", "Dunmore", "Cascadia", 0, 0),
        M("2000-06-01", "Dunmore", "Cascadia", 2, 0),
    ]))

    result = q4_geopolitics.frequent_pairings(ctx, era=None)

    assert result.table is not None
    # Both pairs occur three times; alphabetical pair label is the deterministic tie-breaker.
    assert result.table.rows[0] == ["Avalon v Borealis", 3, 2, 1, 0]
    assert result.headline.startswith("Avalon v Borealis")
    assert {"q4.pairings.top.matches", "q4.pairings.top.wins"} <= set(result.evidence_ids)


def test_communities_split_obvious_clusters_and_are_deterministic() -> None:
    matches: list[M] = []
    north = ["Avalon", "Borealis", "Cascadia"]
    south = ["Dunmore", "Elbaria", "Fenwick"]
    for teams in (north, south):
        for i, home in enumerate(teams):
            for away in teams[i + 1:]:
                matches.extend([
                    M("2019-01-01", home, away, 1, 0),
                    M("2020-01-01", away, home, 0, 0),
                    M("2021-01-01", home, away, 2, 1),
                ])
    matches.append(M("2022-01-01", "Avalon", "Dunmore", 0, 0))
    economies = {
        team: Economy(f"X{i:02d}", "North Region", "High income")
        for i, team in enumerate(north)
    } | {
        team: Economy(f"Y{i:02d}", "South Region", "Low income")
        for i, team in enumerate(south)
    }
    ctx = ToolContext(make_store(matches, economies=economies))

    first = q4_geopolitics.communities(ctx, min_node_matches=2)
    second = q4_geopolitics.communities(ctx, min_node_matches=2)

    assert first.table is not None and second.table is not None
    assert first.table.rows == second.table.rows
    assert [row[1] for row in first.table.rows] == [3, 3]
    agreement = first.facts[[f.id for f in first.facts].index("q4.communities.region_agreement")].value
    assert agreement == 100.0


def test_region_mixing_computes_hand_checked_decade_shares() -> None:
    economies = {
        "Avalon": Economy("XAV", "North Region", "High income"),
        "Borealis": Economy("XBO", "North Region", "High income"),
        "Cascadia": Economy("XCA", "South Region", "High income"),
        "Dunmore": Economy("XDU", "North Region", "Low income"),
    }
    ctx = ToolContext(make_store([
        M("1960-01-01", "Avalon", "Borealis", 1, 0),
        M("1960-02-01", "Avalon", "Cascadia", 1, 0),
        M("1960-03-01", "Avalon", "Dunmore", 1, 0),
    ], economies=economies))

    result = q4_geopolitics.region_mixing(ctx)

    assert result.table is not None
    # Same region: two of three; same current income group: two of three.
    assert result.table.rows[0] == ["1960s", 3, 3, 100.0, 66.7, 66.7]
    assert "q4.region_mixing.1960s.same_region" in result.evidence_ids


def test_communities_insufficient_path_has_no_chart() -> None:
    ctx = ToolContext(make_store([M("2020-01-01", "Avalon", "Borealis", 1, 0)]))

    result = q4_geopolitics.communities(ctx, min_node_matches=5)

    assert result.chart is None
    assert result.facts[0].id == "q4.communities.matches"
