"""Question 7: friendly-match activity and subsequent competitive performance."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import Cell, Chart, Fact, Series, Table, ToolResult
from . import stats
from .context import ToolContext

TOOL_NAME = "friendlies"
DESCRIPTION = (
    "Question 7, friendly-like match activity. Views: leaders = teams with the most friendly-like matches; "
    "effect = four-year-window friendly volume versus next-window competitive performance; "
    "by_income = friendly-like matches per team-year by current WDI income group."
)

Era = Literal["all", "early", "interwar", "postwar", "expansion", "modern", "current"]
View = Literal["leaders", "effect", "by_income"]

ALL_TIME_MIN_MATCHES = 100
MIN_NEXT_COMPETITIVE = 5
WINDOW_START = 1946


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")

    view: View = Field(description="Which friendly-match view to return.")
    era: Era | None = Field(description="Era for leaders; null means all time.")


@dataclass(frozen=True)
class _WindowPoint:
    window_start: int
    team: str
    friendly_matches: int
    next_performance: float
    third: str


CARD_ARGUMENTS = {"view": "leaders", "era": None}


def _round(value: float, digits: int = 2) -> float:
    return round(value, digits)


def _pct(numerator: float, denominator: float) -> float:
    return round(100.0 * numerator / denominator, 1) if denominator else 0.0


def _actual(home_score: int, away_score: int, side_is_home: bool) -> float:
    if home_score == away_score:
        return 0.5
    home_win = home_score > away_score
    return 1.0 if home_win == side_is_home else 0.0


def _era_filter(ctx: ToolContext, era: str | None) -> tuple[str, list[object], str, int]:
    if era in (None, "all"):
        return "", [], "all time", ALL_TIME_MIN_MATCHES
    selected = next(e for e in ctx.reference.eras if e.id == era)
    return "where era = ?", [era], selected.label, selected.min_matches


def leaders(ctx: ToolContext, params: Params, all_time_min_matches: int = ALL_TIME_MIN_MATCHES) -> ToolResult:
    where, query_params, label, min_matches = _era_filter(ctx, params.era)
    if params.era in (None, "all"):
        min_matches = all_time_min_matches
    rows = ctx.store.query(
        f"""
        with appearances as (
          select home_team as team, friendly_like from matches {where}
          union all
          select away_team as team, friendly_like from matches {where}
        )
        select team, count(*) as matches, count(*) filter (where friendly_like) as friendlies
        from appearances
        group by team
        having count(*) >= ?
        order by friendlies desc, team asc
        limit 10
        """,
        [*query_params, *query_params, min_matches],
    )
    total_teams = ctx.store.query_one(
        f"""
        with appearances as (
          select home_team as team from matches {where}
          union all
          select away_team as team from matches {where}
        )
        select count(*) from (select team from appearances group by team having count(*) >= ?)
        """,
        [*query_params, *query_params, min_matches],
    )[0]
    if not rows:
        return ToolResult(
            tool=TOOL_NAME,
            question=7,
            view="leaders",
            params=params.model_dump(),
            title="Friendly-like activity leaders",
            headline=f"No teams met the minimum of {min_matches} matches for {label}.",
            facts=[
                Fact(id="q7.leaders.minimum", label="Minimum matches", value=min_matches, unit="matches"),
                Fact(id="q7.leaders.teams", label="Teams meeting minimum", value=0, unit="teams"),
            ],
            method="Counts each team's friendly-like match appearances in the selected era.",
            coverage=[f"0 teams met the minimum in {label}."],
            caveats=["Observational, not causal; selection effects run both ways."],
            cannot_tell="Whether playing more friendlies would help a particular team.",
            method_version="q7-leaders-v1",
            dataset_version=ctx.dataset_version,
            row_counts={"teams": 0},
        )

    table_rows: list[list[Cell]] = []
    labels: list[str] = []
    values: list[float] = []
    share_values: list[float] = []
    for team, matches, friendlies in rows:
        share = _pct(float(friendlies), float(matches))
        table_rows.append([str(team), int(friendlies), int(matches), share])
        labels.append(str(team))
        values.append(float(friendlies))
        share_values.append(share)
    leader_team = str(rows[0][0])
    leader_matches_i = int(rows[0][1])
    leader_friendlies_i = int(rows[0][2])
    leader_share_f = _pct(leader_friendlies_i, leader_matches_i)
    high_share_i = max(range(len(table_rows)), key=lambda i: (share_values[i], -i))
    facts = [
        Fact(id="q7.leaders.1.friendlies", label=f"{leader_team} friendly-like matches", value=leader_friendlies_i,
             unit="matches"),
        Fact(id="q7.leaders.1.share", label=f"{leader_team} friendly-like share", value=leader_share_f, unit="%",
             decimals=1),
        Fact(id="q7.leaders.minimum", label="Minimum matches", value=min_matches, unit="matches"),
        Fact(id="q7.leaders.teams", label="Teams meeting minimum", value=int(total_teams), unit="teams"),
        Fact(id="q7.leaders.high_share", label=f"Highest share shown: {table_rows[high_share_i][0]}",
             value=share_values[high_share_i], unit="%", decimals=1),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=7,
        view="leaders",
        params=params.model_dump(),
        title=f"Friendly-like activity leaders, {label}",
        headline=(
            f"{leader_team} leads {label} with {leader_friendlies_i} friendly-like matches and a "
            f"{leader_share_f}% friendly-like share."
        ),
        facts=facts,
        table=Table(columns=["Team", "Friendly-like matches", "All matches", "Friendly-like share %"], rows=table_rows),
        chart=Chart(
            kind="hbar",
            title=f"Friendly-like matches, {label}",
            x=labels,
            series=[Series(name="Friendly-like matches", values=values)],
            x_label="Team",
            y_label="Friendly-like matches",
            summary=(
                f"Horizontal bar chart of the top teams; {leader_team} is highest with {leader_friendlies_i} and "
                f"{table_rows[-1][0]} is tenth with {int(values[-1])}."
            ),
        ),
        method="Friendly-like means friendlies plus reviewed invitational friendly tournaments and bilateral trophies.",
        coverage=[f"{int(total_teams)} teams met the minimum of {min_matches} matches for {label}."],
        caveats=[
            "Observational, not causal.",
            "Selection effects run both ways: strong teams receive more invitations, and teams eliminated early fill "
            "calendars with friendlies.",
        ],
        cannot_tell="Whether playing more friendlies would help a particular team.",
        method_version="q7-leaders-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"teams": int(total_teams), "shown": len(rows)},
    )


def _effect_cache(ctx: ToolContext, min_next_competitive: int) -> tuple[list[_WindowPoint], int]:
    key = f"q7_effect:{ctx.dataset_version}:{min_next_competitive}"
    cached = ctx.cache.get(key)
    if isinstance(cached, tuple):
        return cached

    max_year = int(ctx.store.query_one("select max(year) from matches")[0])
    rows = ctx.store.query(
        """
        select match_id, year, home_team, away_team, home_score, away_score, friendly_like, competitive
        from matches
        where year >= ?
        order by year, match_id
        """,
        [WINDOW_START],
    )
    rated = ctx.ratings().by_id()
    by_window_team: dict[tuple[int, str], dict[str, float]] = defaultdict(lambda: {"matches": 0.0, "friendlies": 0.0})
    next_comp: dict[tuple[int, str], list[float]] = defaultdict(list)
    starts = list(range(WINDOW_START, max_year + 1, 4))
    complete_starts = [start for start in starts if start + 7 <= max_year]
    start_set = set(complete_starts)
    for match_id, year, home, away, home_score, away_score, friendly_like, competitive in rows:
        year_i = int(year)
        current_start = WINDOW_START + ((year_i - WINDOW_START) // 4) * 4
        if current_start in start_set:
            for team in (str(home), str(away)):
                bucket = by_window_team[(current_start, team)]
                bucket["matches"] += 1
                if bool(friendly_like):
                    bucket["friendlies"] += 1
        previous_start = current_start - 4
        if previous_start in start_set and bool(competitive):
            rated_match = rated[int(match_id)]
            for team, side_is_home in ((str(home), True), (str(away), False)):
                actual = _actual(int(home_score), int(away_score), side_is_home)
                expected = rated_match.expected_home if side_is_home else 1.0 - rated_match.expected_home
                next_comp[(previous_start, team)].append(actual - expected)

    points: list[_WindowPoint] = []
    for start in complete_starts:
        candidates: list[tuple[str, int, float]] = []
        for (window_start, team), bucket in by_window_team.items():
            if window_start != start or bucket["matches"] < 1:
                continue
            values = next_comp.get((start, team), [])
            if len(values) >= min_next_competitive:
                candidates.append((team, int(bucket["friendlies"]), stats.mean(values)))
        if len(candidates) < 3:
            continue
        ordered = sorted(candidates, key=lambda item: (item[1], item[0]))
        n = len(ordered)
        for i, (team, friendly_matches, performance) in enumerate(ordered):
            third_index = i * 3 // n
            third = ("low", "middle", "high")[third_index]
            points.append(
                _WindowPoint(
                    window_start=start,
                    team=team,
                    friendly_matches=friendly_matches,
                    next_performance=performance,
                    third=third,
                )
            )
    result = (points, len(complete_starts))
    ctx.cache[key] = result
    return result


def effect(ctx: ToolContext, params: Params, min_next_competitive: int = MIN_NEXT_COMPETITIVE) -> ToolResult:
    points, window_count = _effect_cache(ctx, min_next_competitive)
    low = [p.next_performance for p in points if p.third == "low"]
    middle = [p.next_performance for p in points if p.third == "middle"]
    high = [p.next_performance for p in points if p.third == "high"]
    if not low or not high:
        return ToolResult(
            tool=TOOL_NAME,
            question=7,
            view="effect",
            params=params.model_dump(),
            title="Friendly volume and later competitive performance",
            headline=f"Only {len(points)} team-windows met the comparison rules, so no effect estimate is shown.",
            facts=[
                Fact(id="q7.effect.team_windows", label="Team-windows", value=len(points), unit="team-windows"),
                Fact(id="q7.effect.minimum_next", label="Minimum next-window competitive matches",
                     value=min_next_competitive, unit="matches"),
            ],
            method="Teams are split into friendly-volume thirds within fixed four-year windows.",
            coverage=[f"{len(points)} team-windows across {window_count} complete comparison windows."],
            caveats=["Observational, not causal; selection effects run both ways."],
            cannot_tell="Whether playing more friendlies would help a particular team.",
            method_version="q7-effect-v1",
            dataset_version=ctx.dataset_version,
            row_counts={"team_windows": len(points), "windows": window_count},
        )

    diff, lo, hi = stats.bootstrap_difference(high, low)
    correlation = stats.spearman([float(p.friendly_matches) for p in points], [p.next_performance for p in points])
    means = [_round(stats.mean(low)), _round(stats.mean(middle)), _round(stats.mean(high))]
    diff_r, lo_r, hi_r, corr_r = _round(diff), _round(lo), _round(hi), _round(correlation, 3)
    table_rows: list[list[Cell]] = [
        ["Low", len(low), means[0]],
        ["Middle", len(middle), means[1]],
        ["High", len(high), means[2]],
    ]
    facts = [
        Fact(id="q7.effect.diff", label="High-minus-low next competitive performance", value=diff_r, decimals=2),
        Fact(id="q7.effect.low", label="Effect interval lower", value=lo_r, decimals=2),
        Fact(id="q7.effect.high", label="Effect interval upper", value=hi_r, decimals=2),
        Fact(id="q7.effect.spearman", label="Spearman correlation", value=corr_r, decimals=3),
        Fact(id="q7.effect.team_windows", label="Team-windows", value=len(points), unit="team-windows"),
        Fact(id="q7.effect.windows", label="Complete comparison windows", value=window_count, unit="windows"),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=7,
        view="effect",
        params=params.model_dump(),
        title="Friendly volume and later competitive performance",
        headline=(
            f"Across {len(points)} team-windows, high-friendly teams were {diff_r} above low-friendly teams "
            f"next window, with Spearman correlation {corr_r}."
        ),
        facts=facts,
        table=Table(columns=["Friendly-volume third", "Team-windows", "Mean next performance"], rows=table_rows),
        chart=Chart(
            kind="bar",
            title="Next-window competitive performance by friendly-volume third",
            x=["Low", "Middle", "High"],
            series=[Series(name="Mean next performance", values=means)],
            y_label="Actual minus expected",
            summary=f"Bar chart from low {means[0]} to middle {means[1]} to high {means[2]}.",
        ),
        method=(
            "Fixed four-year windows start in the postwar period. Teams are ranked by friendly-like volume within each "
            "window and compared on next-window competitive actual-minus-expected performance."
        ),
        coverage=[f"{len(points)} team-windows across {window_count} complete comparison windows."],
        caveats=[
            "Observational, not causal.",
            "Selection effects run both ways: strong teams receive more invitations, and teams eliminated early fill "
            "calendars with friendlies.",
        ],
        cannot_tell="Whether playing more friendlies would help a particular team.",
        method_version="q7-effect-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"team_windows": len(points), "windows": window_count},
    )


def by_income(ctx: ToolContext, params: Params) -> ToolResult:
    rows = ctx.store.query(
        """
        with appearances as (
          select year, home_team as team, friendly_like from matches where year >= 1960
          union all
          select year, away_team as team, friendly_like from matches where year >= 1960
        ),
        team_years as (
          select year, team, count(*) filter (where friendly_like) as friendly_matches
          from appearances
          group by year, team
        ),
        mapped as (
          select ty.year, ty.team, ty.friendly_matches, t.income_group
          from team_years ty
          left join teams t on t.team = ty.team
            and t.mapping in ('exact', 'alias', 'shared')
            and t.income_group is not null
            and (t.valid_from is null or ty.year >= t.valid_from)
        )
        select income_group, count(*) as team_years, sum(friendly_matches) as friendlies
        from mapped
        where income_group is not null
        group by income_group
        order by (sum(friendly_matches)::double / count(*)) desc, income_group asc
        """
    )
    total_team_years = int(
        ctx.store.query_one(
            """
            with appearances as (
              select year, home_team as team from matches where year >= 1960
              union all
              select year, away_team as team from matches where year >= 1960
            )
            select count(*) from (select year, team from appearances group by year, team)
            """
        )[0]
    )
    mapped_team_years = sum(int(row[1]) for row in rows)
    unmapped_share = _pct(total_team_years - mapped_team_years, total_team_years)
    table_rows: list[list[Cell]] = []
    labels: list[str] = []
    values: list[float] = []
    for income_group, team_years, friendlies in rows:
        value = _round(float(friendlies) / float(team_years))
        table_rows.append([str(income_group), int(team_years), int(friendlies), value])
        labels.append(str(income_group))
        values.append(value)
    if not rows:
        return ToolResult(
            tool=TOOL_NAME,
            question=7,
            view="by_income",
            params=params.model_dump(),
            title="Friendly-like matches by income group",
            headline="No mapped team-years are available for the income-group view.",
            facts=[Fact(id="q7.by_income.unmapped_share", label="Unmapped team-year share", value=unmapped_share,
                        unit="%", decimals=1)],
            method="Counts friendly-like appearances per mapped team-year since the indicator series begins.",
            coverage=[f"{unmapped_share}% of team-years were unmapped."],
            caveats=["Income groups are current classifications and are context, not explanations."],
            cannot_tell="Whether playing more friendlies would help a particular team.",
            method_version="q7-by-income-v1",
            dataset_version=ctx.dataset_version,
            row_counts={"team_years": total_team_years},
        )
    high_i = max(range(len(values)), key=lambda i: (values[i], labels[i]))
    low_i = min(range(len(values)), key=lambda i: (values[i], labels[i]))
    facts = [
        Fact(id="q7.by_income.unmapped_share", label="Unmapped team-year share", value=unmapped_share, unit="%",
             decimals=1),
        Fact(id="q7.by_income.mapped_team_years", label="Mapped team-years", value=mapped_team_years,
             unit="team-years"),
        Fact(id="q7.by_income.total_team_years", label="Total team-years", value=total_team_years,
             unit="team-years"),
        Fact(id="q7.by_income.high", label=f"Highest group shown: {labels[high_i]}", value=values[high_i], decimals=2),
        Fact(id="q7.by_income.low", label=f"Lowest group shown: {labels[low_i]}", value=values[low_i], decimals=2),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=7,
        view="by_income",
        params=params.model_dump(),
        title="Friendly-like matches by current income group",
        headline=(
            f"Since 1960, mapped team-years average from {values[low_i]} to {values[high_i]} friendly-like matches "
            f"per team-year across current income groups."
        ),
        facts=facts,
        table=Table(
            columns=["Current income group", "Team-years", "Friendly-like matches", "Friendlies per team-year"],
            rows=table_rows,
        ),
        chart=Chart(
            kind="bar",
            title="Friendly-like matches per team-year by current income group",
            x=labels,
            series=[Series(name="Friendlies per team-year", values=values)],
            y_label="Friendly-like matches per team-year",
            summary=f"Bar chart ranges from {values[low_i]} to {values[high_i]} friendly-like matches per team-year.",
        ),
        method=(
            "Counts friendly-like appearances per team-year since the indicator series begins, "
            "using current WDI groups."
        ),
        coverage=[f"{unmapped_share}% of team-years were unmapped for current income group."],
        caveats=[
            "Observational, not causal.",
            "Income groups are current classifications and are context, not explanations or rankings of worth.",
        ],
        cannot_tell="Whether playing more friendlies would help a particular team.",
        method_version="q7-by-income-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"team_years": total_team_years, "mapped_team_years": mapped_team_years},
    )


def run(ctx: ToolContext, params: Params) -> ToolResult:
    if params.view == "leaders":
        return leaders(ctx, params)
    if params.view == "effect":
        return effect(ctx, params)
    return by_income(ctx, params)
