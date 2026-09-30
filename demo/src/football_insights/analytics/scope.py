"""Scope tools: honest limitations and a dataset overview, both deterministic.

The agent calls data_limits for anything the data cannot answer, so even a
refusal is grounded: it states what is covered, with numbers from the store,
and what data would be needed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import Fact, ToolResult
from .context import ToolContext, pct

Topic = Literal["club_football", "womens_football", "tactics", "player_statistics", "predictions_betting",
                "outside_date_range", "other"]

LIMITS: dict[str, tuple[str, str]] = {
    "club_football": (
        "The data contains men's full international matches between national teams only; club competitions such as "
        "the Premier League are not included.",
        "Club match results, or event-level data from club competitions, would be needed."),
    "womens_football": (
        "The data contains men's internationals only; women's international matches are excluded from it.",
        "A results dataset of women's international matches would be needed."),
    "tactics": (
        "The data records who played whom, where, when, and the score. It has no possession, passes, shots, "
        "formations, pressing, or counterattack information, so play styles cannot be identified.",
        "Event-level data (passes, shots, and player positions per match) would be needed."),
    "player_statistics": (
        "The only player information is goalscorer records, which cover about a third of all goals. There are no "
        "appearances, assists, minutes, or ratings, and this app does not analyse individual players.",
        "Player-level match data (lineups, minutes, and events) would be needed."),
    "predictions_betting": (
        "This app describes past results only. It makes no predictions and gives no betting advice.",
        "Nothing in this app is designed or validated for forecasting."),
    "outside_date_range": (
        "The data covers matches between its first and last recorded dates; anything outside that range is not in it.",
        "A newer dataset version, downloaded and re-ingested, would be needed for later matches."),
    "other": (
        "The question is outside what the seven questions and this data cover.",
        "Try one of the seven questions, or rephrase the question around international match results."),
}


class LimitsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: Topic = Field(description="What the viewer asked about that the data cannot answer: club football, "
                                     "women's football, tactics or play styles, player statistics, predictions or "
                                     "betting, dates outside the data, or other.")


class FactsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _coverage_facts(ctx: ToolContext) -> tuple[list[Fact], str, str]:
    n, first, last, teams = ctx.store.query_one(
        "select count(*), strftime(min(date), '%Y-%m-%d'), strftime(max(date), '%Y-%m-%d'), "
        "(select count(*) from teams) from matches")
    scoring, timelines = ctx.store.query_one(
        "select count(*) filter (where goals > 0), count(*) filter (where has_timeline and goals > 0) from matches")
    facts = [
        Fact(id="scope.matches", label="Men's international matches in the data", value=int(n), unit="matches"),
        Fact(id="scope.first_year", label=f"First match: {first}", value=int(first[:4])),
        Fact(id="scope.last_year", label=f"Last match: {last}", value=int(last[:4])),
        Fact(id="scope.teams", label="Teams", value=int(teams), unit="teams"),
        Fact(id="scope.goal_timeline_pct", label="Scoring matches with goalscorer records",
             value=pct(timelines, scoring), unit="%", decimals=1),
    ]
    return facts, str(first), str(last)


def data_limits(ctx: ToolContext, params: LimitsParams) -> ToolResult:
    facts, first, last = _coverage_facts(ctx)
    limitation, needed = LIMITS[params.topic]
    if params.topic == "outside_date_range":
        limitation = f"The data covers matches from {first} to {last}; anything outside that range is not in it."
    return ToolResult(
        tool="data_limits", question=0, view=params.topic, params=params.model_dump(),
        title="What this data can't tell you", headline=limitation, facts=facts,
        method="A fixed description of the dataset's scope, with coverage counts from the curated store.",
        coverage=[f"Matches from {first} to {last}."], caveats=[needed],
        cannot_tell=limitation, method_version="scope-v1", dataset_version=ctx.dataset_version,
        row_counts={"matches": int(facts[0].value)},
    )


def dataset_facts(ctx: ToolContext, params: FactsParams) -> ToolResult:
    facts, first, last = _coverage_facts(ctx)
    tournaments, neutral = ctx.store.query_one(
        "select count(distinct tournament), count(*) filter (where neutral) from matches")
    mapped, total = ctx.store.query_one(
        "select count(*) filter (where wdi_code is not null), count(*) from teams")
    facts += [
        Fact(id="scope.tournaments", label="Tournament names", value=int(tournaments)),
        Fact(id="scope.neutral", label="Matches at neutral venues", value=int(neutral), unit="matches"),
        Fact(id="scope.mapped_teams", label="Teams linked to World Bank development data", value=int(mapped),
             unit="teams"),
    ]
    label = ctx.store.dataset_label or "unknown version"
    return ToolResult(
        tool="dataset_facts", question=0, view="overview", params={},
        title="About the data", headline=(f"The data holds {facts[0].value:,} men's international matches from "
                                          f"{first} to {last} between {int(facts[3].value)} teams ({label})."),
        facts=facts,
        method="Counts from the curated store the app is running on.",
        coverage=[f"{mapped} of {total} teams are linked to World Bank development data."],
        caveats=["Scores include extra time but not penalty shootouts; there is no stage or round column."],
        cannot_tell="Anything about club football, women's football, tactics, or players beyond goals.",
        method_version="scope-v1", dataset_version=ctx.dataset_version, row_counts={"matches": int(facts[0].value)},
    )
