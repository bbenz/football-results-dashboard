"""Question 2 era tools on synthetic teams and lowered synthetic era thresholds."""

from __future__ import annotations

from dataclasses import replace

from football_insights.analytics import q2_eras
from football_insights.analytics.context import ToolContext
from football_insights.reference import Reference, get_reference
from helpers import M, make_store


def low_threshold_reference() -> Reference:
    ref = get_reference()
    return replace(ref, eras=tuple(replace(era, min_matches=1) for era in ref.eras))


def era_ctx() -> ToolContext:
    ref = low_threshold_reference()
    store = make_store(
        [
            M("1900-01-01", "Avalon", "Borealis", 1, 0, neutral=True),
            M("1900-01-02", "Cascadia", "Dunmore", 1, 0, neutral=True),
            M("1900-01-03", "Avalon", "Cascadia", 1, 0, neutral=True),
            M("1900-01-04", "Borealis", "Dunmore", 1, 0, neutral=True),
            M("1900-01-05", "Elbaria", "Fenwick", 1, 0, neutral=True),
            M("1930-01-01", "Glenmoor", "Harrowgate", 1, 0, neutral=True),
        ],
        reference=ref,
    )
    return ToolContext(store, reference=ref)


def facts(result):  # type: ignore[no-untyped-def]
    return {fact.id: fact.value for fact in result.facts}


def test_specific_era_ranks_top_five_and_h2h_record() -> None:
    result = q2_eras.specific_era(era_ctx(), "early")

    assert result.table is not None
    assert [row[1] for row in result.table.rows[:3]] == ["Avalon", "Elbaria", "Cascadia"]
    values = facts(result)
    assert values["q2.early.leader_rating"] == 1515
    assert values["q2.early.margin"] == 5
    assert values["q2.early.h2h_wins"] == 2
    assert values["q2.early.h2h_draws"] == 0
    assert values["q2.early.h2h_goals_for"] == 2
    assert values["q2.early.h2h_goals_against"] == 0


def test_all_eras_reports_leader_rating_and_margin_facts() -> None:
    result = q2_eras.all_eras(era_ctx())

    assert result.table is not None
    values = facts(result)
    assert values["q2.all.early.leader_rating"] == 1515
    assert values["q2.all.early.margin"] == 5
    assert values["q2.all.interwar.leader_rating"] == 1510
    assert result.chart is not None
    assert result.chart.series[0].name == "Leader margin"


def test_specific_era_insufficient_path_is_valid() -> None:
    ctx = ToolContext(make_store([M("2000-01-01", "Avalon", "Borealis", 1, 0, neutral=True)]))

    result = q2_eras.specific_era(ctx, "early")

    assert result.chart is None
    assert result.view == "early"
    assert "Fewer than 2 teams" in result.headline


def test_run_dispatches_all_view() -> None:
    result = q2_eras.run(era_ctx(), q2_eras.Params(era="all"))

    assert result.tool == "era_leaders"
    assert result.view == "all"
