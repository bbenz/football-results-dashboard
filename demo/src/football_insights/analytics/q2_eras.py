"""Question 2: teams that dominated defined eras of international football."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import Cell, Chart, Fact, Series, Table, ToolResult
from .context import ToolContext
from .stats import mean

TOOL_NAME = "era_leaders"
DESCRIPTION = (
    "Question 2, which teams dominated different eras of football. era=all returns one leader per reference era; "
    "a specific era returns the top five teams by mean post-match rating and the leader's record against the other "
    "top-five teams."
)
CARD_ARGUMENTS = {"era": "all"}

EraParam = Literal["all", "early", "interwar", "postwar", "expansion", "modern", "current"]


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    era: EraParam = Field(description="One of the era ids from eras.yaml, or all for one leader per era.")


@dataclass(frozen=True)
class EraTeamRating:
    team: str
    rating: float
    matches: int


@dataclass(frozen=True)
class MatchRow:
    era: str
    home: str
    away: str
    home_score: int
    away_score: int


def _era_match_counts(ctx: ToolContext) -> dict[str, int]:
    key = f"{ctx.dataset_version}:q2:era_match_counts"
    cached = ctx.cache.get(key)
    if cached is not None:
        return cached
    counts = {str(era): int(n) for era, n in ctx.store.query("select era, count(*) from matches group by era")}
    ctx.cache[key] = counts
    return counts


def _rated_by_era(ctx: ToolContext) -> dict[str, list[EraTeamRating]]:
    key = f"{ctx.dataset_version}:q2:rated_by_era"
    cached = ctx.cache.get(key)
    if cached is not None:
        return cached
    match_eras = {
        int(match_id): str(era)
        for match_id, era in ctx.store.query("select match_id, era from matches order by match_id")
    }
    sums: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for match in ctx.ratings().matches:
        era = match_eras[match.match_id]
        sums[era][match.home].append(match.home_post)
        sums[era][match.away].append(match.away_post)
    out = {}
    for era, team_values in sums.items():
        out[era] = sorted(
            (EraTeamRating(team=team, rating=mean(values), matches=len(values))
             for team, values in team_values.items()),
            key=lambda r: (-r.rating, r.team),
        )
    ctx.cache[key] = out
    return out


def _match_rows(ctx: ToolContext) -> list[MatchRow]:
    key = f"{ctx.dataset_version}:q2:match_rows"
    cached = ctx.cache.get(key)
    if cached is not None:
        return cached
    rows = [
        MatchRow(str(era), str(home), str(away), int(home_score), int(away_score))
        for era, home, away, home_score, away_score in ctx.store.query(
            "select era, home_team, away_team, home_score, away_score from matches"
        )
    ]
    ctx.cache[key] = rows
    return rows


def _caveats(ctx: ToolContext, era_id: str) -> list[str]:
    counts = _era_match_counts(ctx)
    if era_id == "all":
        early_count = counts.get("early", 0)
        return [
            "Era boundaries are a choice; a team that peaked across a boundary splits its dominance.",
            f"Early eras have small samples: the early era has {early_count} matches in this data.",
        ]
    count = counts.get(era_id, 0)
    return [
        "Era boundaries are a choice; a team that peaked across a boundary splits its dominance.",
        f"This era's sample size is {count} matches in this data.",
    ]


def _cannot_tell() -> str:
    return "Why a team dominated."


def _eligible(ctx: ToolContext, era_id: str) -> list[EraTeamRating]:
    era = next(e for e in ctx.reference.eras if e.id == era_id)
    return [row for row in _rated_by_era(ctx).get(era_id, []) if row.matches >= era.min_matches]


def _insufficient(ctx: ToolContext, era: EraParam, title: str, reason: str) -> ToolResult:
    return ToolResult(
        tool=TOOL_NAME,
        question=2,
        view=era,
        params={"era": era},
        title=title,
        headline=reason,
        method="Era ratings were computed, but too few teams met the era minimum sample.",
        coverage=[reason],
        caveats=_caveats(ctx, era),
        cannot_tell=_cannot_tell(),
        method_version=f"q2-{era}-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"matches": _era_match_counts(ctx).get(era, 0)},
    )


def all_eras(ctx: ToolContext) -> ToolResult:
    rows: list[list[Cell]] = []
    chart_labels: list[str] = []
    margins: list[int] = []
    facts: list[Fact] = []
    for era in ctx.reference.eras:
        ranked = _eligible(ctx, era.id)
        if len(ranked) < 2:
            rows.append([era.label, _era_match_counts(ctx).get(era.id, 0), "Insufficient data", None, None, None])
            continue
        leader, runner_up = ranked[0], ranked[1]
        margin = round(leader.rating - runner_up.rating)
        leader_rating = round(leader.rating)
        rows.append([
            era.label,
            _era_match_counts(ctx).get(era.id, 0),
            leader.team,
            leader_rating,
            runner_up.team,
            margin,
            leader.matches,
        ])
        chart_labels.append(f"{era.label}: {leader.team}")
        margins.append(margin)
        fact_prefix = f"q2.all.{era.id}"
        facts.extend([
            Fact(id=f"{fact_prefix}.leader_rating", label=f"{era.label} leader rating: {leader.team}",
                 value=leader_rating, unit="rating points"),
            Fact(id=f"{fact_prefix}.margin", label=f"{era.label} dominance margin", value=margin,
                 unit="rating points"),
        ])
    if not margins:
        return _insufficient(ctx, "all", "Era leaders", "No era has two teams meeting its minimum match sample.")
    max_i = max(range(len(margins)), key=lambda i: (margins[i], chart_labels[i]))
    widest_era, widest_leader = chart_labels[max_i].split(": ", 1)
    return ToolResult(
        tool=TOOL_NAME,
        question=2,
        view="all",
        params={"era": "all"},
        title="Era leaders by mean post-match rating",
        headline=(f"The widest lead in any era was {widest_leader}'s {margins[max_i]} rating points over the "
                  f"runner-up in {widest_era}."),
        facts=facts,
        table=Table(
            columns=["Era", "Era matches", "Leader", "Leader rating", "Runner-up", "Margin", "Leader matches"],
            rows=rows,
        ),
        chart=Chart(
            kind="hbar",
            title="Dominance margin by era",
            x=chart_labels,
            series=[Series(name="Leader margin", values=margins)],
            x_label="Era leader",
            y_label="Leader margin",
            y_unit="rating points",
            summary=(
                f"Horizontal bar chart of leader margins, not leader ratings; the largest margin is {margins[max_i]} "
                f"for {chart_labels[max_i]}."
            ),
        ),
        method=(
            "For each reference era, average every team's post-match ratings within that era. Keep teams with at "
            "least the era minimum matches, then rank by rating and team name."
        ),
        coverage=["Each row uses the era boundaries and minimum match count from eras.yaml."],
        caveats=_caveats(ctx, "all"),
        cannot_tell=_cannot_tell(),
        method_version="q2-all-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"eras": len(ctx.reference.eras), "matches": sum(_era_match_counts(ctx).values())},
    )


def _leader_record(ctx: ToolContext, era_id: str, leader: str, rivals: set[str]) -> tuple[int, int, int, int, int]:
    wins = draws = losses = gf = ga = 0
    for match in _match_rows(ctx):
        if match.era != era_id:
            continue
        if match.home == leader and match.away in rivals:
            for_goals, against_goals = match.home_score, match.away_score
        elif match.away == leader and match.home in rivals:
            for_goals, against_goals = match.away_score, match.home_score
        else:
            continue
        gf += for_goals
        ga += against_goals
        if for_goals > against_goals:
            wins += 1
        elif for_goals == against_goals:
            draws += 1
        else:
            losses += 1
    return wins, draws, losses, gf, ga


SpecificEraParam = Literal["early", "interwar", "postwar", "expansion", "modern", "current"]


def specific_era(ctx: ToolContext, era_id: SpecificEraParam) -> ToolResult:
    era = next(e for e in ctx.reference.eras if e.id == era_id)
    ranked = _eligible(ctx, era_id)[:5]
    if len(ranked) < 2:
        return _insufficient(
            ctx,
            era_id,
            f"{era.label} era leaders",
            f"Fewer than 2 teams meet the {era.min_matches}-match minimum in {era.label}.",
        )
    leader, runner_up = ranked[0], ranked[1]
    margin = round(leader.rating - runner_up.rating)
    table_rows: list[list[Cell]] = [
        [i, row.team, round(row.rating), row.matches] for i, row in enumerate(ranked, start=1)
    ]
    rivals = {row.team for row in ranked[1:]}
    wins, draws, losses, gf, ga = _leader_record(ctx, era_id, leader.team, rivals)
    prefix = f"q2.{era_id}"
    facts = [
        Fact(id=f"{prefix}.leader_rating", label=f"{era.label} leader rating: {leader.team}",
             value=round(leader.rating), unit="rating points"),
        Fact(id=f"{prefix}.runner_up_rating", label=f"{era.label} runner-up rating: {runner_up.team}",
             value=round(runner_up.rating), unit="rating points"),
        Fact(id=f"{prefix}.margin", label="Dominance margin", value=margin, unit="rating points"),
        Fact(id=f"{prefix}.leader_matches", label=f"Leader matches in era: {leader.team}", value=leader.matches,
             unit="matches"),
        Fact(id=f"{prefix}.era_matches", label=f"Matches in {era.label}", value=_era_match_counts(ctx).get(era_id, 0),
             unit="matches"),
        Fact(id=f"{prefix}.h2h_wins", label=f"{leader.team} wins against the other top five", value=wins),
        Fact(id=f"{prefix}.h2h_draws", label=f"{leader.team} draws against the other top five", value=draws),
        Fact(id=f"{prefix}.h2h_losses", label=f"{leader.team} losses against the other top five", value=losses),
        Fact(id=f"{prefix}.h2h_goals_for", label=f"{leader.team} goals for against the other top five", value=gf),
        Fact(id=f"{prefix}.h2h_goals_against", label=f"{leader.team} goals against the other top five", value=ga),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=2,
        view=era_id,
        params={"era": era_id},
        title=f"{era.id.capitalize()} era leaders",
        headline=(
            f"In the {era.id} era, {leader.team} leads with a {round(leader.rating)} rating and a "
            f"{margin}-point margin."
        ),
        facts=facts,
        table=Table(columns=["Rank", "Team", "Era rating", "Rated matches"], rows=table_rows),
        chart=Chart(
            kind="hbar",
            title=f"Top five era ratings, {era.label}",
            x=[row.team for row in ranked],
            series=[Series(name="Era rating", values=[round(row.rating) for row in ranked])],
            x_label="Team",
            y_label="Mean post-match rating",
            y_unit="rating points",
            summary=(
                f"Horizontal bar chart of top-five era ratings; {leader.team} leads at {round(leader.rating)} "
                f"and {ranked[-1].team} is fifth at {round(ranked[-1].rating)}."
            ),
        ),
        method=(
            "Average each team's post-match ratings inside the selected era, keep teams with the era minimum number "
            "of matches, and rank by rating then team name. The head-to-head record counts the leader's matches "
            "against the other top-five teams in the same era."
        ),
        coverage=[f"{_era_match_counts(ctx).get(era_id, 0)} matches fall in {era.label}."],
        caveats=_caveats(ctx, era_id),
        cannot_tell=_cannot_tell(),
        method_version=f"q2-{era_id}-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"matches": _era_match_counts(ctx).get(era_id, 0), "teams_ranked": len(ranked)},
    )


def run(ctx: ToolContext, params: Params) -> ToolResult:
    if params.era == "all":
        return all_eras(ctx)
    return specific_era(ctx, params.era)
