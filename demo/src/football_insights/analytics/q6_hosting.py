"""Question 6: host performance in major tournaments."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import Cell, Chart, Fact, Series, Table, ToolResult
from . import stats
from .context import ToolContext, slug
from .ratings import RatedMatch

TOOL_NAME = "hosting_effect"
DESCRIPTION = (
    "Question 6, host performance in major tournaments. Views: pooled = pooled host-minus-non-host comparison; "
    "by_tournament = tournament-level comparisons; edition = the hosts and comparison rows for one edition; "
    "gdp_split = descriptive split of paired hosts by GDP per capita."
)

Tournament = Literal[
    "FIFA World Cup",
    "UEFA Euro",
    "Copa América",
    "African Cup of Nations",
    "AFC Asian Cup",
    "CONCACAF Championship",
    "Gold Cup",
    "Oceania Nations Cup",
]
View = Literal["pooled", "by_tournament", "edition", "gdp_split"]

MIN_NEUTRAL_SHARE = 0.4
MAX_VENUES = 3
MIN_TEAMS = 4
MIN_POOLED = 20
MIN_PER_TOURNAMENT = 6


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")

    view: View = Field(description="Which hosting-effect view to return.")
    tournament: Tournament | None = Field(description="Major tournament for the edition view; null uses defaults.")
    year: int | None = Field(description="Edition first-match year for the edition view; null uses defaults.")


@dataclass(frozen=True)
class _MatchRow:
    match_id: int
    date: date
    year: int
    tournament: str
    home: str
    away: str
    home_score: int
    away_score: int
    neutral: bool
    venue_team: str | None


@dataclass
class _TeamEdition:
    tournament: str
    year: int
    team: str
    is_host: bool
    matches: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    performance: float
    progression: float


@dataclass
class _Edition:
    tournament: str
    year: int
    matches: list[_MatchRow]
    participants: set[str]
    hosts: set[str]
    neutral_share: float
    venue_count: int
    excluded_reasons: tuple[str, ...]
    teams: dict[str, _TeamEdition]


@dataclass(frozen=True)
class _Pair:
    tournament: str
    year: int
    host: str
    host_performance: float
    non_host_performance: float
    performance_diff: float
    host_progression: float
    non_host_progression: float
    progression_diff: float
    gdp_per_capita: float | None = None


CARD_ARGUMENTS = {"view": "pooled", "tournament": None, "year": None}


def _round(value: float, digits: int = 2) -> float:
    return round(value, digits)


def _actual(home_score: int, away_score: int, side_is_home: bool) -> float:
    if home_score == away_score:
        return 0.5
    home_win = home_score > away_score
    return 1.0 if home_win == side_is_home else 0.0


def _side_expected_neutral(expected_home_neutral: float, side_is_home: bool) -> float:
    return expected_home_neutral if side_is_home else 1.0 - expected_home_neutral


def _edition_cache(ctx: ToolContext) -> dict[str, object]:
    key = f"q6_editions:{ctx.dataset_version}"
    cached = ctx.cache.get(key)
    if isinstance(cached, dict):
        return cached

    rows = ctx.store.query(
        """
        select match_id, date, year, tournament, home_team, away_team, home_score, away_score, neutral, venue_team
        from matches
        where tournament in (select unnest(?))
        order by tournament, date, match_id
        """,
        [list(ctx.reference.major_tournaments)],
    )
    match_rows = [
        _MatchRow(
            match_id=int(r[0]),
            date=r[1],
            year=int(r[2]),
            tournament=str(r[3]),
            home=str(r[4]),
            away=str(r[5]),
            home_score=int(r[6]),
            away_score=int(r[7]),
            neutral=bool(r[8]),
            venue_team=str(r[9]) if r[9] is not None else None,
        )
        for r in rows
    ]
    rated = ctx.ratings().by_id()
    editions: list[_Edition] = []
    by_tournament: dict[str, list[_MatchRow]] = defaultdict(list)
    for row in match_rows:
        by_tournament[row.tournament].append(row)
    for tournament in ctx.reference.major_tournaments:
        current: list[_MatchRow] = []
        previous: _MatchRow | None = None
        for row in by_tournament.get(tournament, []):
            if previous is not None and (row.date - previous.date).days >= 90:
                editions.append(_build_edition(tournament, current, rated))
                current = []
            current.append(row)
            previous = row
        if current:
            editions.append(_build_edition(tournament, current, rated))

    included = [edition for edition in editions if not edition.excluded_reasons]
    pairs = _paired_hosts(included)
    result: dict[str, object] = {
        "editions": editions,
        "included": included,
        "pairs": pairs,
        "excluded_reasons": Counter(reason for e in editions for reason in e.excluded_reasons),
    }
    ctx.cache[key] = result
    return result


def _build_edition(tournament: str, matches: list[_MatchRow], rated: dict[int, RatedMatch]) -> _Edition:
    participants = {m.home for m in matches} | {m.away for m in matches}
    venues = {m.venue_team for m in matches if m.venue_team}
    hosts = {m.venue_team for m in matches if m.venue_team in participants}
    neutral_share = sum(1 for m in matches if m.neutral) / len(matches)
    reasons: list[str] = []
    if neutral_share < MIN_NEUTRAL_SHARE:
        reasons.append("low_neutral_share")
    if len(venues) > MAX_VENUES:
        reasons.append("too_many_venues")
    if len(participants) < MIN_TEAMS:
        reasons.append("too_few_teams")

    counts = {team: 0 for team in participants}
    for match in matches:
        counts[match.home] += 1
        counts[match.away] += 1
    median_matches = float(median(counts.values())) if counts else 0.0
    team_rows: dict[str, _TeamEdition] = {}
    for team in sorted(participants):
        played = wins = draws = losses = goals_for = goals_against = 0
        deltas: list[float] = []
        for match in matches:
            if team not in (match.home, match.away):
                continue
            played += 1
            side_is_home = team == match.home
            gf = match.home_score if side_is_home else match.away_score
            ga = match.away_score if side_is_home else match.home_score
            goals_for += gf
            goals_against += ga
            if gf > ga:
                wins += 1
            elif gf == ga:
                draws += 1
            else:
                losses += 1
            rated_match = rated[match.match_id]
            expected = _side_expected_neutral(rated_match.expected_home_neutral, side_is_home)
            deltas.append(_actual(match.home_score, match.away_score, side_is_home) - expected)
        team_rows[team] = _TeamEdition(
            tournament=tournament,
            year=matches[0].year,
            team=team,
            is_host=team in hosts,
            matches=played,
            wins=wins,
            draws=draws,
            losses=losses,
            goals_for=goals_for,
            goals_against=goals_against,
            performance=stats.mean(deltas),
            progression=played / median_matches if median_matches else 0.0,
        )
    return _Edition(
        tournament=tournament,
        year=matches[0].year,
        matches=matches,
        participants=participants,
        hosts=hosts,
        neutral_share=neutral_share,
        venue_count=len(venues),
        excluded_reasons=tuple(reasons),
        teams=team_rows,
    )


def _paired_hosts(editions: list[_Edition]) -> list[_Pair]:
    by_team_tournament: dict[tuple[str, str], list[_TeamEdition]] = defaultdict(list)
    for edition in editions:
        for team_edition in edition.teams.values():
            by_team_tournament[(team_edition.team, team_edition.tournament)].append(team_edition)

    pairs: list[_Pair] = []
    for edition in editions:
        for host in sorted(edition.hosts):
            host_row = edition.teams[host]
            comparisons = [
                row for row in by_team_tournament[(host, edition.tournament)]
                if not row.is_host and row.year != edition.year
            ]
            if not comparisons:
                continue
            non_host_perf = stats.mean([row.performance for row in comparisons])
            non_host_prog = stats.mean([row.progression for row in comparisons])
            pairs.append(
                _Pair(
                    tournament=edition.tournament,
                    year=edition.year,
                    host=host,
                    host_performance=host_row.performance,
                    non_host_performance=non_host_perf,
                    performance_diff=host_row.performance - non_host_perf,
                    host_progression=host_row.progression,
                    non_host_progression=non_host_prog,
                    progression_diff=host_row.progression - non_host_prog,
                )
            )
    return sorted(pairs, key=lambda p: (p.year, p.tournament, p.host))


def _counts(cache: dict[str, object]) -> tuple[list[_Edition], list[_Edition], list[_Pair], Counter[str]]:
    editions = cache["editions"]
    included = cache["included"]
    pairs = cache["pairs"]
    reasons = cache["excluded_reasons"]
    assert isinstance(editions, list)
    assert isinstance(included, list)
    assert isinstance(pairs, list)
    assert isinstance(reasons, Counter)
    return editions, included, pairs, reasons


def _insufficient(ctx: ToolContext, view: str, params: Params, n: int, required: int) -> ToolResult:
    return ToolResult(
        tool=TOOL_NAME,
        question=6,
        view=view,
        params=params.model_dump(),
        title="Hosting effect",
        headline=(
            f"Only {n} paired host editions are available, below the minimum of {required}, "
            "so no estimate is shown."
        ),
        facts=[
            Fact(id=f"q6.{view}.paired", label="Paired host editions", value=n, unit="paired editions"),
            Fact(id=f"q6.{view}.minimum", label="Minimum paired host editions", value=required, unit="paired editions"),
        ],
        method="Host editions are compared with the same team's non-host editions of the same tournament.",
        coverage=[f"{n} paired host editions available."],
        caveats=["Samples are small, formats vary across editions, and there is no stage column."],
        cannot_tell="Whether hosting causes better results, or how a future host will do.",
        method_version=f"q6-{view}-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"paired_host_editions": n},
    )


def _excluded_coverage(editions: list[_Edition], reasons: Counter[str]) -> list[str]:
    excluded = sum(1 for e in editions if e.excluded_reasons)
    if excluded == 0:
        return ["No editions were excluded by the neutral-venue, venue-count, or team-count filters."]
    reason_text = ", ".join(f"{reason.replace('_', ' ')}: {count}" for reason, count in sorted(reasons.items()))
    return [f"{excluded} editions were excluded by the filters ({reason_text})."]


def pooled(ctx: ToolContext, params: Params, min_pooled: int = MIN_POOLED) -> ToolResult:
    editions, included, pairs, reasons = _counts(_edition_cache(ctx))
    if len(pairs) < min_pooled:
        return _insufficient(ctx, "pooled", params, len(pairs), min_pooled)
    perf_mean, perf_lo, perf_hi = stats.bootstrap_mean([p.performance_diff for p in pairs])
    prog_mean, prog_lo, prog_hi = stats.bootstrap_mean([p.progression_diff for p in pairs])
    host_total = sum(len(e.hosts) for e in included)
    excluded = sum(1 for e in editions if e.excluded_reasons)
    facts = [
        Fact(
            id="q6.pooled.performance_diff",
            label="Host effect: points per match above expectation (win = 1, draw = 0.5)",
            value=_round(perf_mean),
            decimals=2,
        ),
        Fact(id="q6.pooled.performance_low", label="95% interval, lower", value=_round(perf_lo), decimals=2),
        Fact(id="q6.pooled.performance_high", label="95% interval, upper", value=_round(perf_hi), decimals=2),
        Fact(
            id="q6.pooled.progression_diff",
            label="Host effect on matches played, in multiples of the edition's median per team",
            value=_round(prog_mean),
            decimals=2,
        ),
        Fact(id="q6.pooled.paired", label="Paired host editions", value=len(pairs), unit="paired editions"),
        Fact(
            id="q6.pooled.host_total",
            label="Included host-team editions",
            value=host_total,
            unit="host-team editions",
        ),
        Fact(id="q6.pooled.excluded", label="Excluded editions", value=excluded, unit="editions"),
    ]
    recent = sorted(pairs, key=lambda p: (-p.year, p.tournament, p.host))[:15]
    table_rows: list[list[Cell]] = [
        [
            p.tournament,
            p.year,
            p.host,
            _round(p.host_performance),
            _round(p.non_host_performance),
            _round(p.performance_diff),
        ]
        for p in recent
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=6,
        view="pooled",
        params=params.model_dump(),
        title="Hosting effect in major tournaments",
        headline=(
            f"Across {len(pairs)} host editions, hosts scored {_round(perf_mean)} more points per match above rating "
            f"expectations than the same teams did as non-hosts (95% interval {_round(perf_lo)} to "
            f"{_round(perf_hi)}; a win counts 1 and a draw 0.5)."
        ),
        facts=facts,
        table=Table(
            columns=["Tournament", "Year", "Host", "Host performance", "Non-host mean", "Difference"],
            rows=table_rows,
        ),
        chart=Chart(
            kind="bar",
            title="Pooled host effect",
            x=["Performance", "Progression"],
            series=[
                Series(
                    name="Mean host-minus-non-host effect",
                    values=[_round(perf_mean), _round(prog_mean)],
                    lower=[_round(perf_lo), _round(prog_lo)],
                    upper=[_round(perf_hi), _round(prog_hi)],
                )
            ],
            y_label="Host minus non-host",
            summary=(
                f"Bar chart of the pooled host effects with 95% intervals: {_round(perf_mean)} points per match above "
                f"expectation, and {_round(prog_mean)} in matches played relative to the edition median."
            ),
        ),
        method="Each included host-team edition is compared with that team's non-host editions in the same tournament.",
        coverage=[
            f"{host_total} included host-team editions; {len(pairs)} have a non-host comparison.",
            *_excluded_coverage(editions, reasons),
        ],
        caveats=["Samples are small, formats vary across editions, and there is no stage column."],
        cannot_tell="Whether hosting causes better results, or how a future host will do.",
        method_version="q6-pooled-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"editions": len(editions), "included_editions": len(included), "paired_host_editions": len(pairs)},
    )


def by_tournament(ctx: ToolContext, params: Params, min_per_tournament: int = MIN_PER_TOURNAMENT) -> ToolResult:
    editions, included, pairs, reasons = _counts(_edition_cache(ctx))
    grouped: dict[str, list[_Pair]] = defaultdict(list)
    for pair in pairs:
        grouped[pair.tournament].append(pair)
    enough = {t: rows for t, rows in grouped.items() if len(rows) >= min_per_tournament}
    if not enough:
        return _insufficient(ctx, "by_tournament", params, len(pairs), min_per_tournament)

    table_rows: list[list[Cell]] = []
    chart_labels: list[str] = []
    chart_values: list[float] = []
    chart_lower: list[float] = []
    chart_upper: list[float] = []
    facts: list[Fact] = [
        Fact(id="q6.by_tournament.tournaments", label="Tournaments with enough paired hosts", value=len(enough)),
        Fact(id="q6.by_tournament.minimum", label="Minimum per tournament", value=min_per_tournament),
    ]
    for tournament, rows in sorted(enough.items()):
        mean, lo, hi = stats.bootstrap_mean([p.performance_diff for p in rows])
        prog_mean, _, _ = stats.bootstrap_mean([p.progression_diff for p in rows])
        table_rows.append([tournament, len(rows), _round(mean), _round(lo), _round(hi), _round(prog_mean)])
        chart_labels.append(tournament)
        chart_values.append(_round(mean))
        chart_lower.append(_round(lo))
        chart_upper.append(_round(hi))
    insufficient: list[tuple[str, int]] = [
        (tournament, len(grouped.get(tournament, [])))
        for tournament in ctx.reference.major_tournaments
        if len(grouped.get(tournament, [])) < min_per_tournament
    ]
    table_rows.extend([["Insufficient: " + str(row[0]), int(row[1]), None, None, None, None] for row in insufficient])
    high_i = max(range(len(chart_values)), key=lambda i: (chart_values[i], chart_labels[i]))
    low_i = min(range(len(chart_values)), key=lambda i: (chart_values[i], chart_labels[i]))
    facts.extend(
        [
            Fact(id="q6.by_tournament.high", label=f"Highest shown: {chart_labels[high_i]}", value=chart_values[high_i],
                 decimals=2),
            Fact(id="q6.by_tournament.low", label=f"Lowest shown: {chart_labels[low_i]}", value=chart_values[low_i],
                 decimals=2),
            Fact(id="q6.by_tournament.paired", label="Paired host editions", value=len(pairs), unit="paired editions"),
        ]
    )
    return ToolResult(
        tool=TOOL_NAME,
        question=6,
        view="by_tournament",
        params=params.model_dump(),
        title="Hosting effect by tournament",
        headline=(
            f"{len(enough)} tournaments meet the minimum of {min_per_tournament} paired host editions; "
            f"the shown effects range from {chart_values[low_i]} to {chart_values[high_i]}."
        ),
        facts=facts,
        table=Table(
            columns=["Tournament", "Paired hosts", "Performance diff", "Low", "High", "Progression diff"],
            rows=table_rows[:30],
        ),
        chart=Chart(
            kind="hbar",
            title="Mean host performance effect by tournament",
            x=chart_labels,
            series=[Series(name="Performance effect", values=chart_values, lower=chart_lower, upper=chart_upper)],
            x_label="Tournament",
            y_label="Host-minus-non-host effect",
            summary=(
                f"Horizontal bars show tournament means; the lowest shown is {chart_values[low_i]} and "
                f"the highest shown is {chart_values[high_i]}."
            ),
        ),
        method="Tournament means use included paired host editions only; smaller samples are listed as insufficient.",
        coverage=_excluded_coverage(editions, reasons),
        caveats=["Samples are small, formats vary across editions, and there is no stage column."],
        cannot_tell="Whether hosting causes better results, or how a future host will do.",
        method_version="q6-by-tournament-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"included_editions": len(included), "paired_host_editions": len(pairs)},
    )


def _select_edition(editions: list[_Edition], tournament: str | None, year: int | None) -> _Edition | None:
    selected_tournament = tournament or "FIFA World Cup"
    candidates = [e for e in editions if e.tournament == selected_tournament]
    if not candidates:
        return None
    if year is None:
        return max(candidates, key=lambda e: e.year)
    for edition in candidates:
        if edition.year == year:
            return edition
    return None


def edition(ctx: ToolContext, params: Params) -> ToolResult:
    editions, _included, pairs, _reasons = _counts(_edition_cache(ctx))
    selected = _select_edition(editions, params.tournament, params.year)
    requested_tournament = params.tournament or "FIFA World Cup"
    requested_year = params.year
    if selected is None:
        label = f"{requested_tournament}" if requested_year is None else f"{requested_tournament} {requested_year}"
        return ToolResult(
            tool=TOOL_NAME,
            question=6,
            view="edition",
            params=params.model_dump(),
            title="Host edition detail",
            headline=f"No matching edition was found for {label}.",
            facts=[],
            method="Edition detail uses the requested tournament and first-match year.",
            coverage=["No edition matched the requested filters."],
            caveats=["Samples are small, formats vary across editions, and there is no stage column."],
            cannot_tell="Whether hosting causes better results, or how a future host will do.",
            method_version="q6-edition-v2",
            dataset_version=ctx.dataset_version,
            row_counts={"editions": len(editions)},
        )

    pair_lookup = {(p.tournament, p.year, p.host): p for p in pairs}
    rows: list[list[Cell]] = []
    host_facts: list[Fact] = []
    labels: list[str] = []
    this_edition: list[float | None] = []
    non_host: list[float | None] = []
    diffs: list[tuple[float, str]] = []
    for host in sorted(selected.hosts):
        team = selected.teams[host]
        pair = pair_lookup.get((selected.tournament, selected.year, host))
        rows.append(
            [
                host,
                team.matches,
                f"{team.wins}-{team.draws}-{team.losses}",
                team.goals_for,
                team.goals_against,
                _round(team.performance),
                _round(team.progression),
                _round(pair.non_host_performance) if pair else None,
                _round(pair.performance_diff) if pair else None,
            ]
        )
        prefix = f"q6.edition.{slug(host)}"
        host_facts.extend([
            Fact(id=f"{prefix}.matches", label=f"{host}: matches played", value=team.matches, unit="matches"),
            Fact(id=f"{prefix}.wins", label=f"{host}: wins", value=team.wins),
            Fact(id=f"{prefix}.performance", label=f"{host}: points per match above rating expectations, this edition",
                 value=_round(team.performance), decimals=2),
        ])
        labels.append(host)
        this_edition.append(_round(team.performance))
        non_host.append(_round(pair.non_host_performance) if pair else None)
        if pair:
            host_facts.extend([
                Fact(id=f"{prefix}.non_host_mean",
                     label=f"{host}: points per match above rating expectations, own non-host editions",
                     value=_round(pair.non_host_performance), decimals=2),
                Fact(id=f"{prefix}.difference", label=f"{host}: host edition minus non-host editions",
                     value=_round(pair.performance_diff), decimals=2),
            ])
            diffs.append((_round(pair.performance_diff), host))
    host_count = len(selected.hosts)
    facts = [
        Fact(id="q6.edition.hosts", label="Hosts", value=host_count),
        Fact(id="q6.edition.teams", label="Teams in edition", value=len(selected.participants), unit="teams"),
        Fact(id="q6.edition.matches", label="Matches in edition", value=len(selected.matches), unit="matches"),
        Fact(id="q6.edition.neutral_share", label="Neutral-match share", value=_round(100 * selected.neutral_share, 1),
             unit="%", decimals=1),
        Fact(id="q6.edition.venues", label="Venue identities", value=selected.venue_count),
        *host_facts,
    ]
    headline = (f"{selected.tournament} {selected.year} has {host_count} host teams and "
                f"{len(selected.matches)} matches in this edition view.")
    chart = None
    if diffs:
        better = sum(1 for diff, _ in diffs if diff > 0)
        best_diff, best_host = max(diffs)
        facts.append(Fact(id="q6.edition.hosts_better", label="Hosts that beat their own non-host editions",
                          value=better))
        facts.append(Fact(id="q6.edition.hosts_compared", label="Hosts with non-host editions to compare",
                          value=len(diffs)))
        headline = (f"At {selected.tournament} {selected.year}, {better} of {len(diffs)} hosts did better against "
                    f"rating expectations than in their own non-host editions; {best_host} gained the most, "
                    f"{best_diff:.2f} points per match.")
        chart = Chart(
            kind="bar",
            title=f"Hosts at {selected.tournament} {selected.year} versus their non-host editions",
            x=labels,
            series=[Series(name="This edition", values=this_edition),
                    Series(name="Own non-host editions", values=non_host)],
            x_label="Host",
            y_label="Points per match above rating expectations",
            y_unit="points per match",
            summary=(f"Bar chart of each host's points per match above rating expectations in this edition next to "
                     f"its own non-host editions; {best_host} shows the largest gain, {best_diff:.2f}."),
        )
    excluded_text = "included" if not selected.excluded_reasons else "excluded"
    return ToolResult(
        tool=TOOL_NAME,
        question=6,
        view="edition",
        params=params.model_dump(),
        title=f"{selected.tournament} {selected.year} hosts",
        headline=headline,
        facts=facts,
        table=Table(
            columns=[
                "Host",
                "Matches",
                "W-D-L",
                "GF",
                "GA",
                "Performance",
                "Progression",
                "Non-host mean",
                "Difference",
            ],
            rows=rows,
        ),
        chart=chart,
        method=("Shows host-team records and rating-adjusted performance (actual points per match minus the "
                "expectation from pre-match ratings without the home bonus), compared with the same team's own "
                "non-host editions of the tournament where it has any."),
        coverage=[f"This edition is {excluded_text} by the hosting filters."],
        caveats=["Samples are small, formats vary across editions, and there is no stage column."],
        cannot_tell="Whether hosting causes better results, or how a future host will do.",
        method_version="q6-edition-v2",
        dataset_version=ctx.dataset_version,
        row_counts={"hosts": host_count, "matches": len(selected.matches)},
    )


def _pairs_with_gdp(ctx: ToolContext, pairs: list[_Pair]) -> tuple[list[_Pair], int]:
    rows = ctx.store.query(
        """
        select team, wdi_code, mapping, valid_from
        from teams
        where mapping in ('exact', 'alias') and wdi_code is not null
        """
    )
    team_map = {
        str(team): (str(code), int(valid_from) if valid_from is not None else None)
        for team, code, _mapping, valid_from in rows
    }
    indicator_rows = ctx.store.query(
        "select code, year, value from indicators where indicator = 'NY.GDP.PCAP.KD'"
    )
    indicators = {(str(code), int(year)): float(value) for code, year, value in indicator_rows}
    mapped: list[_Pair] = []
    unmapped = 0
    for pair in pairs:
        if pair.year < 1960:
            continue
        team_info = team_map.get(pair.host)
        if not team_info:
            unmapped += 1
            continue
        code, valid_from = team_info
        if valid_from is not None and pair.year < valid_from:
            unmapped += 1
            continue
        value = indicators.get((code, pair.year))
        if value is None:
            unmapped += 1
            continue
        mapped.append(
            _Pair(
                tournament=pair.tournament,
                year=pair.year,
                host=pair.host,
                host_performance=pair.host_performance,
                non_host_performance=pair.non_host_performance,
                performance_diff=pair.performance_diff,
                host_progression=pair.host_progression,
                non_host_progression=pair.non_host_progression,
                progression_diff=pair.progression_diff,
                gdp_per_capita=value,
            )
        )
    return mapped, unmapped


def gdp_split(ctx: ToolContext, params: Params) -> ToolResult:
    _editions, _included, pairs, _reasons = _counts(_edition_cache(ctx))
    mapped, unmapped = _pairs_with_gdp(ctx, pairs)
    if len(mapped) < 2:
        return _insufficient(ctx, "gdp_split", params, len(mapped), 2)
    ordered = sorted(mapped, key=lambda p: (p.gdp_per_capita or 0.0, p.year, p.tournament, p.host))
    cut = (len(ordered) + 1) // 2
    halves = [("Lower half", ordered[:cut]), ("Upper half", ordered[cut:])]
    table_rows: list[list[Cell]] = []
    labels: list[str] = []
    values: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    for label, rows in halves:
        mean, lo, hi = stats.bootstrap_mean([p.performance_diff for p in rows])
        table_rows.append([label, len(rows), _round(mean), _round(lo), _round(hi)])
        labels.append(label)
        values.append(_round(mean))
        lower.append(_round(lo))
        upper.append(_round(hi))
    unmapped_share = _round(100 * unmapped / (len(mapped) + unmapped), 1) if mapped or unmapped else 0.0
    facts = [
        Fact(id="q6.gdp_split.mapped", label="Mapped paired hosts", value=len(mapped), unit="paired hosts"),
        Fact(id="q6.gdp_split.unmapped_share", label="Unmapped paired-host share", value=unmapped_share, unit="%",
             decimals=1),
        Fact(id="q6.gdp_split.lower", label="Lower-half effect", value=values[0], decimals=2),
        Fact(id="q6.gdp_split.upper", label="Upper-half effect", value=values[1], decimals=2),
        Fact(id="q6.gdp_split.lower_n", label="Lower-half paired hosts", value=len(halves[0][1]),
             unit="paired hosts"),
        Fact(id="q6.gdp_split.upper_n", label="Upper-half paired hosts", value=len(halves[1][1]),
             unit="paired hosts"),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=6,
        view="gdp_split",
        params=params.model_dump(),
        title="Hosting effect by GDP per capita split",
        headline=(
            f"Among {len(mapped)} mapped paired hosts since 1960, the lower half averaged {values[0]} and "
            f"the upper half averaged {values[1]}."
        ),
        facts=facts,
        table=Table(columns=["GDP split", "Paired hosts", "Performance diff", "Low", "High"], rows=table_rows),
        chart=Chart(
            kind="bar",
            title="Descriptive GDP split of host effect",
            x=labels,
            series=[Series(name="Performance effect", values=values, lower=lower, upper=upper)],
            y_label="Host-minus-non-host effect",
            summary=f"Descriptive split: lower half {values[0]}, upper half {values[1]}.",
        ),
        method="Paired host editions since the indicator series begins are split by same-year GDP per capita.",
        coverage=[f"{unmapped_share}% of eligible paired hosts were not mapped to exact or alias GDP per capita."],
        caveats=["This is descriptive only; samples are small, formats vary, and there is no stage column."],
        cannot_tell=(
            "Whether GDP context explains hosting effects, whether hosting causes better results, or forecasts."
        ),
        method_version="q6-gdp-split-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"mapped_paired_hosts": len(mapped), "unmapped_paired_hosts": unmapped},
    )


def run(ctx: ToolContext, params: Params) -> ToolResult:
    if params.view == "pooled":
        return pooled(ctx, params)
    if params.view == "by_tournament":
        return by_tournament(ctx, params)
    if params.view == "edition":
        return edition(ctx, params)
    return gdp_split(ctx, params)
