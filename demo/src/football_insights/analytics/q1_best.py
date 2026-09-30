"""Question 1: best team of all time, by several deterministic lenses."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import Cell, Chart, Fact, Series, Table, ToolResult
from . import ratings
from .context import ToolContext, pct
from .stats import mean

TOOL_NAME = "best_team"
DESCRIPTION = (
    "Question 1, who is the best team of all time. Views: peak = highest post-match rating after a team's "
    "30th match; career_average = mean year-end rating for long-running teams; time_at_top = year-end ranking "
    "leadership among active teams; records = win rate, points per match, and goal difference per match; "
    "wins_per_million = novelty lens dividing wins by latest WDI population in millions."
)
CARD_ARGUMENTS = {"lens": "peak"}

MIN_MATCHES_BEFORE_PEAK = 30
MIN_ACTIVE_YEARS = 40
MIN_MATCHES_RECORDS = 300
MIN_MATCHES_NOVELTY = 100
EARLY_BOUNDARY_YEAR = 1915

Lens = Literal["peak", "career_average", "time_at_top", "records", "wins_per_million"]


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lens: Lens = Field(
        description=(
            "peak: highest post-match rating after a team's 30th match; career_average: mean year-end rating for "
            "teams with at least 40 active years; time_at_top: year-end first and top-five counts; records: win "
            "rate for teams with at least 300 matches; wins_per_million: novelty wins divided by latest population."
        )
    )


@dataclass(frozen=True)
class PeakRow:
    team: str
    rating: float
    date: str
    match_number: int


def _early_team_count(ctx: ToolContext) -> int:
    key = f"{ctx.dataset_version}:q1:early_team_count"
    cached = ctx.cache.get(key)
    if cached is not None:
        return int(cached)
    row = ctx.store.query_one(
        "select count(distinct team) from ("
        "select home_team as team from matches where year < ? "
        "union select away_team as team from matches where year < ?)",
        [EARLY_BOUNDARY_YEAR, EARLY_BOUNDARY_YEAR],
    )
    value = int(row[0] or 0)
    ctx.cache[key] = value
    return value


def _parameter_facts(ctx: ToolContext) -> list[Fact]:
    return [
        Fact(id="q1.params.start_rating", label="Rating model start rating", value=round(ratings.START)),
        Fact(id="q1.params.home_advantage", label="Rating model home advantage", value=round(ratings.HOME_ADVANTAGE)),
        Fact(
            id="q1.params.k_world_cup",
            label="Rating model World Cup K",
            value=ctx.reference.categories["world_cup"].k,
        ),
        Fact(id="q1.params.k_friendly", label="Rating model friendly K", value=ctx.reference.categories["friendly"].k),
        Fact(
            id="q1.params.early_boundary_year",
            label="Early-era boundary year",
            value=EARLY_BOUNDARY_YEAR,
        ),
        Fact(
            id="q1.params.pre_1915_teams",
            label="Distinct teams with matches before 1915",
            value=_early_team_count(ctx),
            unit="teams",
        ),
    ]


def _caveats(ctx: ToolContext, lens: str) -> list[str]:
    prefix = "This novelty lens is a population-scaled curiosity; " if lens == "wins_per_million" else ""
    return [
        f"{prefix}Best depends on the definition, here the {lens} lens; the rating parameters are shown as facts.",
        f"Early eras have sparse schedules: before 1915, { _early_team_count(ctx) } distinct teams appear in the data.",
    ]


def _cannot_tell() -> str:
    return "Which team would beat which across eras; anything about players, tactics, or club football."


def _insufficient(ctx: ToolContext, lens: Lens, title: str, reason: str, row_counts: dict[str, int]) -> ToolResult:
    return ToolResult(
        tool=TOOL_NAME,
        question=1,
        view=lens,
        params={"lens": lens},
        title=title,
        headline=reason,
        facts=_parameter_facts(ctx),
        method="The requested lens was computed, but no team met the minimum sample threshold.",
        coverage=[reason],
        caveats=_caveats(ctx, lens),
        cannot_tell=_cannot_tell(),
        method_version=f"q1-{lens}-v1",
        dataset_version=ctx.dataset_version,
        row_counts=row_counts,
    )


def peak(ctx: ToolContext, min_matches_before_peak: int = MIN_MATCHES_BEFORE_PEAK) -> ToolResult:
    key = f"{ctx.dataset_version}:q1:peak:{min_matches_before_peak}"
    cached = ctx.cache.get(key)
    if cached is not None:
        rows = cached
    else:
        counts: dict[str, int] = defaultdict(int)
        best: dict[str, PeakRow] = {}
        for match in ctx.ratings().matches:
            for team, post in ((match.home, match.home_post), (match.away, match.away_post)):
                counts[team] += 1
                match_number = counts[team]
                if match_number <= min_matches_before_peak:
                    continue
                current = best.get(team)
                candidate = PeakRow(team=team, rating=post, date=match.date, match_number=match_number)
                is_better = (
                    current is None
                    or post > current.rating
                    or (post == current.rating and candidate.date < current.date)
                )
                if is_better:
                    best[team] = candidate
        rows = sorted(best.values(), key=lambda r: (-r.rating, r.team))[:10]
        ctx.cache[key] = rows
    if not rows:
        return _insufficient(
            ctx,
            "peak",
            "Peak rating",
            f"No team has more than {min_matches_before_peak} matches, so no peak ranking is shown.",
            {"teams": 0},
        )
    table_rows: list[list[Cell]] = [
        [i, r.team, round(r.rating), r.date, r.match_number] for i, r in enumerate(rows, start=1)
    ]
    top = rows[0]
    facts = [
        Fact(id="q1.peak.1.rating", label=f"Peak rating: {top.team}", value=round(top.rating), unit="rating points"),
        Fact(id="q1.peak.1.date_year", label=f"Peak year: {top.team}", value=int(top.date[:4])),
        Fact(
            id="q1.peak.min_matches_before_peak",
            label="Matches before peaks are counted",
            value=min_matches_before_peak,
            unit="matches",
        ),
        *_parameter_facts(ctx),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=1,
        view="peak",
        params={"lens": "peak"},
        title="Best team by peak rating",
        headline=f"The peak lens ranks {top.team} first at {round(top.rating)} rating points.",
        facts=facts,
        table=Table(columns=["Rank", "Team", "Peak rating", "Peak date", "Team match number"], rows=table_rows),
        chart=Chart(
            kind="hbar",
            title="Top peak ratings after the sample threshold",
            x=[r.team for r in rows],
            series=[Series(name="Peak rating", values=[round(r.rating) for r in rows])],
            x_label="Team",
            y_label="Peak rating",
            y_unit="rating points",
            summary=(
                f"Horizontal bar chart of peak ratings; {rows[0].team} is highest at {round(rows[0].rating)} "
                f"and {rows[-1].team} is tenth at {round(rows[-1].rating)}."
            ),
        ),
        method=(
            "Process matches with the ratings-v1 model, then take each team's highest post-match rating after its "
            "sample threshold and rank by rating, with team name as the tie-breaker."
        ),
        coverage=[f"Teams need more than {min_matches_before_peak} rated matches before a peak is eligible."],
        caveats=_caveats(ctx, "peak"),
        cannot_tell=_cannot_tell(),
        method_version="q1-peak-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"teams_ranked": len(rows)},
    )


def career_average(ctx: ToolContext, min_active_years: int = MIN_ACTIVE_YEARS) -> ToolResult:
    rows = [
        (team, mean(list(years.values())), len(years))
        for team, years in ctx.ratings().year_end.items()
        if len(years) >= min_active_years
    ]
    rows = sorted(rows, key=lambda r: (-r[1], r[0]))[:10]
    if not rows:
        return _insufficient(
            ctx,
            "career_average",
            "Best team by career-average rating",
            f"No team has at least {min_active_years} active years, so no career-average ranking is shown.",
            {"teams_ranked": 0},
        )
    table_rows: list[list[Cell]] = [
        [i, team, round(avg), years] for i, (team, avg, years) in enumerate(rows, start=1)
    ]
    top = rows[0]
    facts = [
        Fact(id="q1.career_average.1.rating", label=f"Career-average rating: {top[0]}", value=round(top[1])),
        Fact(id="q1.career_average.1.years", label=f"Active years: {top[0]}", value=top[2], unit="years"),
        Fact(id="q1.career_average.min_active_years", label="Minimum active years", value=min_active_years),
        *_parameter_facts(ctx),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=1,
        view="career_average",
        params={"lens": "career_average"},
        title="Best team by career-average rating",
        headline=f"The career-average lens ranks {top[0]} first at {round(top[1])} rating points.",
        facts=facts,
        table=Table(columns=["Rank", "Team", "Mean year-end rating", "Active years"], rows=table_rows),
        chart=Chart(
            kind="hbar",
            title="Top career-average ratings",
            x=[r[0] for r in rows],
            series=[Series(name="Mean year-end rating", values=[round(r[1]) for r in rows])],
            x_label="Team",
            y_label="Mean rating",
            y_unit="rating points",
            summary=(
                f"Horizontal bar chart of career-average ratings; {rows[0][0]} is highest at {round(rows[0][1])} "
                f"and {rows[-1][0]} is tenth at {round(rows[-1][1])}."
            ),
        ),
        method=(
            "Average every year-end rating for each team with enough active years, ranking by average rating and then "
            "team name."
        ),
        coverage=[f"Teams need at least {min_active_years} years with a year-end rating."],
        caveats=_caveats(ctx, "career_average"),
        cannot_tell=_cannot_tell(),
        method_version="q1-career_average-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"teams_ranked": len(rows)},
    )


def time_at_top(ctx: ToolContext) -> ToolResult:
    history = ctx.ratings()
    if not history.matches:
        return _insufficient(ctx, "time_at_top", "Best team by time at the top", "No rated matches are loaded.", {})
    first_year = min(m.year for m in history.matches)
    last_year = max(m.year for m in history.matches)
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for year in range(first_year, last_year + 1):
        active = ratings.active_teams(history, year)
        ordered = sorted(active.items(), key=lambda r: (-r[1], r[0]))
        for i, (team, _rating) in enumerate(ordered[:5]):
            counts[team][1] += 1
            if i == 0:
                counts[team][0] += 1
    rows = sorted(((team, v[0], v[1]) for team, v in counts.items()), key=lambda r: (-r[1], -r[2], r[0]))[:10]
    if not rows:
        return _insufficient(ctx, "time_at_top", "Best team by time at the top", "No active year-end teams.", {})
    table_rows: list[list[Cell]] = [[i, team, firsts, top5] for i, (team, firsts, top5) in enumerate(rows, start=1)]
    top = rows[0]
    facts = [
        Fact(id="q1.time_at_top.1.first_years", label=f"Year-ends ranked first: {top[0]}", value=top[1], unit="years"),
        Fact(
            id="q1.time_at_top.1.top_five_years",
            label=f"Year-ends in top five: {top[0]}",
            value=top[2],
            unit="years",
        ),
        Fact(id="q1.time_at_top.first_year", label="First year-end ranked", value=first_year),
        Fact(id="q1.time_at_top.last_year", label="Last year-end ranked", value=last_year),
        *_parameter_facts(ctx),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=1,
        view="time_at_top",
        params={"lens": "time_at_top"},
        title="Best team by time at the top",
        headline=f"The time-at-top lens ranks {top[0]} first with {top[1]} year-ends ranked first.",
        facts=facts,
        table=Table(columns=["Rank", "Team", "Year-ends ranked first", "Year-ends in top five"], rows=table_rows),
        chart=Chart(
            kind="hbar",
            title="Year-ends ranked first",
            x=[r[0] for r in rows],
            series=[Series(name="Ranked first", values=[r[1] for r in rows])],
            x_label="Team",
            y_label="Year-ends ranked first",
            y_unit="years",
            summary=(
                f"Horizontal bar chart of year-ends ranked first; {rows[0][0]} leads with {rows[0][1]} "
                f"and {rows[-1][0]} is tenth with {rows[-1][1]}."
            ),
        ),
        method=(
            "For every year-end in the data, rank active teams by rating. Count first-place and top-five finishes, "
            "ranking by first-place years, then top-five years, then team name."
        ),
        coverage=[
            f"Year-ends from {first_year} through {last_year}; active means played that year or the three before."
        ],
        caveats=_caveats(ctx, "time_at_top"),
        cannot_tell=_cannot_tell(),
        method_version="q1-time_at_top-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"teams_ranked": len(rows), "years_ranked": last_year - first_year + 1},
    )


def records(ctx: ToolContext, min_matches: int = MIN_MATCHES_RECORDS) -> ToolResult:
    rows = ctx.store.query(
        """
        with appearances as (
          select home_team as team, home_score as gf, away_score as ga from matches
          union all
          select away_team as team, away_score as gf, home_score as ga from matches
        )
        select team, count(*) as matches,
          count(*) filter (where gf > ga) as wins,
          count(*) filter (where gf = ga) as draws,
          avg(gf - ga) as gd_per_match
        from appearances
        group by team
        having count(*) >= ?
        """,
        [min_matches],
    )
    ranked = []
    for team, matches, wins, draws, gd_per_match in rows:
        n, w, d = int(matches), int(wins), int(draws)
        ranked.append((team, n, w, d, pct(w, n), round((3 * w + d) / n, 2), round(float(gd_per_match), 2)))
    ranked = sorted(ranked, key=lambda r: (-r[4], -r[5], -r[6], r[0]))[:10]
    if not ranked:
        return _insufficient(
            ctx,
            "records",
            "Best team by records",
            f"No team has at least {min_matches} matches, so no records ranking is shown.",
            {"teams_ranked": 0},
        )
    table_rows: list[list[Cell]] = [
        [i, team, n, win_rate, ppg, gd] for i, (team, n, _w, _d, win_rate, ppg, gd) in enumerate(ranked, start=1)
    ]
    top = ranked[0]
    facts = [
        Fact(id="q1.records.1.win_rate", label=f"Win rate: {top[0]}", value=top[4], unit="%", decimals=1),
        Fact(id="q1.records.1.points_per_match", label=f"Points per match: {top[0]}", value=top[5], decimals=2),
        Fact(id="q1.records.min_matches", label="Minimum matches", value=min_matches, unit="matches"),
        *_parameter_facts(ctx),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=1,
        view="records",
        params={"lens": "records"},
        title="Best team by match records",
        headline=f"The records lens ranks {top[0]} first with a {top[4]}% win rate.",
        facts=facts,
        table=Table(
            columns=["Rank", "Team", "Matches", "Win rate %", "Points per match", "Goal difference per match"],
            rows=table_rows,
        ),
        chart=Chart(
            kind="hbar",
            title="Top win rates",
            x=[r[0] for r in ranked],
            series=[Series(name="Win rate", values=[r[4] for r in ranked])],
            x_label="Team",
            y_label="Win rate",
            y_unit="%",
            summary=(
                f"Horizontal bar chart of win rates; {ranked[0][0]} is highest at {ranked[0][4]}% "
                f"and {ranked[-1][0]} is tenth at {ranked[-1][4]}%."
            ),
        ),
        method=(
            "Count every team appearance, scoring wins as three points and draws as one point. Rank by win rate, "
            "then points per match, goal difference per match, and team name."
        ),
        coverage=[f"Teams need at least {min_matches} matches."],
        caveats=_caveats(ctx, "records"),
        cannot_tell=_cannot_tell(),
        method_version="q1-records-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"teams_ranked": len(ranked)},
    )


def wins_per_million(ctx: ToolContext, min_matches: int = MIN_MATCHES_NOVELTY) -> ToolResult:
    rows = ctx.store.query(
        """
        with latest_population as (
          select code, year, value,
                 row_number() over (partition by code order by year desc) as rn
          from indicators
          where indicator = 'SP.POP.TOTL' and value is not null
        ),
        appearances as (
          select home_team as team, year, case when home_score > away_score then 1 else 0 end as win from matches
          union all
          select away_team as team, year, case when away_score > home_score then 1 else 0 end as win from matches
        )
        select t.team, count(a.team) as matches, sum(a.win) as wins, p.year as population_year, p.value as population
        from teams t
        join latest_population p on p.code = t.wdi_code and p.rn = 1
        join appearances a on a.team = t.team and (t.valid_from is null or a.year >= t.valid_from)
        where t.mapping in ('exact', 'alias')
        group by t.team, p.year, p.value
        having count(a.team) >= ?
        """,
        [min_matches],
    )
    ranked = []
    for team, matches, wins, population_year, population in rows:
        wins_float = float(wins or 0)
        pop = float(population)
        per_million = round(wins_float / (pop / 1_000_000), 2) if pop else 0.0
        ranked.append(
            (team, int(matches), int(wins_float), int(population_year), round(pop / 1_000_000, 2), per_million)
        )
    ranked = sorted(ranked, key=lambda r: (-r[5], -r[2], r[0]))[:10]
    if not ranked:
        return _insufficient(
            ctx,
            "wins_per_million",
            "Novelty lens: wins per million inhabitants",
            f"No exact or alias-mapped team has at least {min_matches} matches and population data.",
            {"teams_ranked": 0},
        )
    table_rows: list[list[Cell]] = [
        [i, team, matches, wins, population_year, population_millions, per_million]
        for i, (team, matches, wins, population_year, population_millions, per_million) in enumerate(ranked, start=1)
    ]
    top = ranked[0]
    facts = [
        Fact(id="q1.wins_per_million.1.value", label=f"Wins per million: {top[0]}", value=top[5], decimals=2),
        Fact(id="q1.wins_per_million.1.population_year", label=f"Population year: {top[0]}", value=top[3]),
        Fact(id="q1.wins_per_million.min_matches", label="Minimum matches", value=min_matches, unit="matches"),
        *_parameter_facts(ctx),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=1,
        view="wins_per_million",
        params={"lens": "wins_per_million"},
        title="Novelty lens: best team by wins per million inhabitants",
        headline=f"The novelty wins-per-million lens ranks {top[0]} first at {top[5]} wins per million inhabitants.",
        facts=facts,
        table=Table(
            columns=["Rank", "Team", "Matches", "Wins", "Population year", "Population (millions)", "Wins per million"],
            rows=table_rows,
        ),
        chart=Chart(
            kind="hbar",
            title="Novelty wins per million inhabitants",
            x=[r[0] for r in ranked],
            series=[Series(name="Wins per million", values=[r[5] for r in ranked])],
            x_label="Team",
            y_label="Wins per million inhabitants",
            summary=(
                f"Horizontal bar chart of novelty wins per million; {ranked[0][0]} is highest at {ranked[0][5]} "
                f"and {ranked[-1][0]} is tenth at {ranked[-1][5]}."
            ),
        ),
        method=(
            "Novelty calculation: count wins for exact or alias WDI-mapped teams, respect mapping start years, and "
            "divide by the latest available WDI population in millions. Rank by wins per million, then wins, then name."
        ),
        coverage=[
            f"Teams need at least {min_matches} matches and an exact or alias mapping; shared and unmapped teams "
            "are excluded."
        ],
        caveats=[
            *_caveats(ctx, "wins_per_million"),
            "This novelty lens divides all recorded wins by the latest available population, not historical "
            "population.",
        ],
        cannot_tell=_cannot_tell(),
        method_version="q1-wins_per_million-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"teams_ranked": len(ranked)},
    )


def run(ctx: ToolContext, params: Params) -> ToolResult:
    views = {
        "peak": peak,
        "career_average": career_average,
        "time_at_top": time_at_top,
        "records": records,
        "wins_per_million": wins_per_million,
    }
    return views[params.lens](ctx)
