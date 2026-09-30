"""Question 5: third-party hosts of international fixtures."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import Cell, Chart, Fact, Series, Table, ToolResult
from .context import ToolContext, pct
from .stats import wilson

TOOL_NAME = "neutral_hosts"
DESCRIPTION = (
    "Question 5, countries that host matches they are not playing in. Views: ranking = leading third-party host "
    "identities, trend = third-party hosted share by decade with Wilson intervals, cities = leading host cities, "
    "host_groups = WDI region and income context for third-party hosts."
)

MIN_DECADE_MATCHES = 100
MAX_TABLE_ROWS = 30

EraParam = Literal["all", "early", "interwar", "postwar", "expansion", "modern", "current"]
View = Literal["ranking", "trend", "cities", "host_groups"]


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    view: View = Field(description="Which deterministic view to return.")
    era: EraParam | None = Field(description="Era for ranking and cities; null means all time.")


CARD_ARGUMENTS = {"view": "ranking", "era": None}


def _decade_label(decade: int) -> str:
    return f"{decade}s"


def _era_label(ctx: ToolContext, era: str | None) -> str:
    if era is None or era == "all":
        return "all time"
    for item in ctx.reference.eras:
        if item.id == era:
            return item.label
    return era


def _era_phrase(ctx: ToolContext, era: str | None) -> str:
    label = _era_label(ctx, era)
    return "across all years" if label == "all time" else f"in {label}"


def _era_clause(era: str | None) -> tuple[str, list[str]]:
    if era is None or era == "all":
        return "", []
    return " and era = ?", [era]


def _disagreement_facts(ctx: ToolContext, view: str) -> list[Fact]:
    neutral_participant = int(ctx.store.query_one(
        "select count(*) from matches where neutral and venue_is_participant"
    )[0])
    nonneutral_third = int(ctx.store.query_one(
        "select count(*) from matches where not neutral and not venue_is_participant"
    )[0])
    return [
        Fact(id=f"q5.{view}.neutral_participant", label="Neutral flag but venue is a participant",
             value=neutral_participant, unit="matches"),
        Fact(id=f"q5.{view}.nonneutral_third_venue", label="Non-neutral flag but venue is neither team",
             value=nonneutral_third, unit="matches"),
        Fact(id=f"q5.{view}.venue_aliases", label="Reviewed venue aliases", value=len(ctx.reference.venue_aliases)),
    ]


def _caveats(ctx: ToolContext, view: str) -> list[str]:
    neutral_participant = next(f for f in _disagreement_facts(ctx, view) if f.id.endswith("neutral_participant")).value
    nonneutral_third = next(f for f in _disagreement_facts(ctx, view) if f.id.endswith("nonneutral_third_venue")).value
    aliases = len(ctx.reference.venue_aliases)
    return [
        f"Venues are reconciled with former names plus {aliases} reviewed aliases.",
        (
            f"The third-party rule counts neutral matches only when the reconciled venue identity is neither team; "
            f"{neutral_participant} neutral-flag matches at a participant venue and {nonneutral_third} non-neutral "
            "matches at another venue identity are disclosed but not reclassified."
        ),
    ]


def _cannot_tell() -> str:
    return "Why a country hosts, or anything about attendance or revenue."


def _insufficient(ctx: ToolContext, view: str, title: str, reason: str, counts: dict[str, int]) -> ToolResult:
    total = counts.get("matches", 0)
    return ToolResult(
        tool=TOOL_NAME,
        question=5,
        view=view,
        params={"view": view, "era": None},
        title=title,
        headline=f"The loaded data has {total} matches, so {reason}.",
        facts=[
            Fact(id=f"q5.{view}.matches", label="Matches checked", value=total, unit="matches"),
            *_disagreement_facts(ctx, view),
        ],
        method="The view returns an explanatory result when the minimum sample is not met.",
        coverage=[f"{total} matches checked."],
        caveats=_caveats(ctx, view),
        cannot_tell=_cannot_tell(),
        method_version=f"q5-{view}-v1",
        dataset_version=ctx.dataset_version,
        row_counts=counts,
    )


def ranking(ctx: ToolContext, era: EraParam | None) -> ToolResult:
    clause, args = _era_clause(era)
    rows = ctx.store.query(
        f"""
        select venue_team, count(*) as matches
        from matches
        where third_party and venue_team is not null{clause}
        group by venue_team
        order by matches desc, venue_team asc
        limit 10
        """,
        args,
    )
    totals = ctx.store.query_one(
        f"""
        select count(*), count(distinct venue_team)
        from matches
        where third_party and venue_team is not null{clause}
        """,
        args,
    )
    total_third_party = int(totals[0])
    distinct_hosts = int(totals[1])
    if not rows:
        return _insufficient(ctx, "ranking", f"Third-party hosts, {_era_label(ctx, era)}",
                             "no third-party host ranking is shown", {"matches": total_third_party})

    table_rows: list[list[Cell]] = [[str(host), int(count)] for host, count in rows]
    top_host = str(rows[0][0])
    top_count = int(rows[0][1])
    facts = [
        Fact(id="q5.ranking.top1", label=f"Top host: {top_host}", value=top_count, unit="matches"),
        Fact(id="q5.ranking.top2", label=f"Second host: {str(rows[1][0]) if len(rows) > 1 else 'None'}",
             value=int(rows[1][1]) if len(rows) > 1 else 0, unit="matches"),
        Fact(id="q5.ranking.top3", label=f"Third host: {str(rows[2][0]) if len(rows) > 2 else 'None'}",
             value=int(rows[2][1]) if len(rows) > 2 else 0, unit="matches"),
        Fact(id="q5.ranking.total_third_party", label="Third-party hosted matches", value=total_third_party,
             unit="matches"),
        Fact(id="q5.ranking.distinct_hosts", label="Distinct third-party host identities", value=distinct_hosts,
             unit="hosts"),
        *_disagreement_facts(ctx, "ranking"),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=5,
        view="ranking",
        params={"view": "ranking", "era": era},
        title=f"Leading third-party hosts, {_era_label(ctx, era)}",
        headline=(
            f"{top_host} hosted the most third-party matches {_era_phrase(ctx, era)}: {top_count} of "
            f"{total_third_party}, across {distinct_hosts} host identities."
        ),
        facts=facts,
        table=Table(columns=["Host identity", "Third-party matches"], rows=table_rows),
        chart=Chart(
            kind="hbar",
            title=f"Top third-party host identities, {_era_label(ctx, era)}",
            x=[str(r[0]) for r in rows],
            series=[Series(name="Matches", values=[int(r[1]) for r in rows])],
            x_label="Host identity",
            y_label="Third-party matches",
            summary=(
                f"Horizontal bar chart of {len(table_rows)} host identities; {top_host} is highest with "
                f"{top_count} third-party matches."
            ),
        ),
        method=(
            "Counts matches where third_party is true: the neutral flag is true and the reconciled venue identity is "
            "neither participant. Rankings break ties by host name ascending."
        ),
        coverage=[
            f"{total_third_party} third-party hosted matches across {distinct_hosts} host identities in "
            f"{_era_label(ctx, era)}.",
        ],
        caveats=_caveats(ctx, "ranking"),
        cannot_tell=_cannot_tell(),
        method_version="q5-ranking-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"third_party_matches": total_third_party, "hosts": distinct_hosts},
    )


def trend(ctx: ToolContext, min_matches: int = MIN_DECADE_MATCHES) -> ToolResult:
    rows = ctx.store.query("""
        select decade, count(*) as matches, count(*) filter (where third_party) as third_party
        from matches
        group by decade
        order by decade
    """)
    kept = [r for r in rows if int(r[1]) >= min_matches]
    if not kept:
        return _insufficient(ctx, "trend", "Third-party hosting trend",
                             f"no decade reached the minimum of {min_matches} matches",
                             {"matches": sum(int(r[1]) for r in rows)})

    labels: list[str] = []
    shares: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    table_rows: list[list[Cell]] = []
    for decade, matches, third_party in kept:
        share, lo, hi = wilson(int(third_party), int(matches))
        labels.append(_decade_label(int(decade)))
        shares.append(round(share, 1))
        lower.append(round(lo, 1))
        upper.append(round(hi, 1))
        table_rows.append([labels[-1], int(matches), int(third_party), shares[-1], lower[-1], upper[-1]])

    peak_i = max(range(len(shares)), key=lambda i: (shares[i], -i))
    low_i = min(range(len(shares)), key=lambda i: (shares[i], i))
    latest_i = len(labels) - 1
    facts = [
        Fact(id=f"q5.trend.{labels[0]}", label=f"Third-party share, {labels[0]}", value=shares[0], unit="%",
             decimals=1),
        Fact(id=f"q5.trend.{labels[latest_i]}", label=f"Third-party share, {labels[latest_i]}",
             value=shares[latest_i], unit="%", decimals=1),
        Fact(id=f"q5.trend.{labels[peak_i]}.peak", label=f"Highest decade: {labels[peak_i]}",
             value=shares[peak_i], unit="%", decimals=1),
        Fact(id=f"q5.trend.{labels[low_i]}.low", label=f"Lowest decade: {labels[low_i]}",
             value=shares[low_i], unit="%", decimals=1),
        Fact(id="q5.trend.matches", label="Matches in decades shown", value=sum(int(r[1]) for r in kept),
             unit="matches"),
        Fact(id="q5.trend.minimum_decade_matches", label="Minimum matches per decade", value=min_matches,
             unit="matches"),
        *_disagreement_facts(ctx, "trend"),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=5,
        view="trend",
        params={"view": "trend", "era": None},
        title="Third-party hosting share by decade",
        headline=(
            f"The third-party hosted share was {shares[0]}% in the {labels[0]} and {shares[latest_i]}% in the "
            f"{labels[latest_i]}."
        ),
        facts=facts,
        table=Table(
            columns=["Decade", "Matches", "Third-party matches", "Share %", "Wilson lower %", "Wilson upper %"],
            rows=table_rows,
        ),
        chart=Chart(
            kind="line",
            title="Share of matches hosted by a third party",
            x=labels,
            series=[Series(name="Third-party hosted %", values=shares, lower=lower, upper=upper)],
            x_label="Decade",
            y_label="Share of all matches",
            y_unit="%",
            y_min=0,
            y_max=100,
            summary=(
                f"Line chart from {labels[0]} to {labels[latest_i]}; the share peaks in the {labels[peak_i]} at "
                f"{shares[peak_i]}% and is lowest in the {labels[low_i]} at {shares[low_i]}%."
            ),
        ),
        method=(
            "For each decade with at least the minimum number of matches, computes the share of all matches where "
            "third_party is true, with 95% Wilson intervals."
        ),
        coverage=[f"Decades with fewer than {min_matches} matches are excluded."],
        caveats=_caveats(ctx, "trend"),
        cannot_tell=_cannot_tell(),
        method_version="q5-trend-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"matches": sum(int(r[1]) for r in kept), "decades": len(kept)},
    )


def cities(ctx: ToolContext, era: EraParam | None) -> ToolResult:
    clause, args = _era_clause(era)
    rows = ctx.store.query(
        f"""
        select city, venue_team, count(*) as matches
        from matches
        where third_party and city is not null and venue_team is not null{clause}
        group by city, venue_team
        order by matches desc, city asc, venue_team asc
        limit 10
        """,
        args,
    )
    totals = ctx.store.query_one(
        f"""
        select count(*), count(distinct city || '|' || venue_team)
        from matches
        where third_party and city is not null and venue_team is not null{clause}
        """,
        args,
    )
    total = int(totals[0])
    distinct = int(totals[1])
    if not rows:
        return _insufficient(ctx, "cities", f"Third-party host cities, {_era_label(ctx, era)}",
                             "no city ranking is shown", {"matches": total})

    table_rows: list[list[Cell]] = [[str(city), str(host), int(count)] for city, host, count in rows]
    top_city, top_host, top_count = str(rows[0][0]), str(rows[0][1]), int(rows[0][2])
    facts = [
        Fact(id="q5.cities.top1", label=f"Top city-host: {top_city}, {top_host}", value=top_count, unit="matches"),
        Fact(
            id="q5.cities.top2",
            label=f"Second city-host: {rows[1][0]!s}, {rows[1][1]!s}" if len(rows) > 1 else "Second city-host",
            value=int(rows[1][2]) if len(rows) > 1 else 0,
            unit="matches",
        ),
        Fact(
            id="q5.cities.top3",
            label=f"Third city-host: {rows[2][0]!s}, {rows[2][1]!s}" if len(rows) > 2 else "Third city-host",
            value=int(rows[2][2]) if len(rows) > 2 else 0,
            unit="matches",
        ),
        Fact(id="q5.cities.total_third_party_city", label="Third-party matches with city and host identity",
             value=total, unit="matches"),
        Fact(id="q5.cities.distinct_city_hosts", label="Distinct city-host pairs", value=distinct),
        *_disagreement_facts(ctx, "cities"),
    ]
    labels = [f"{city}, {host}" for city, host, _ in rows]
    return ToolResult(
        tool=TOOL_NAME,
        question=5,
        view="cities",
        params={"view": "cities", "era": era},
        title=f"Leading third-party host cities, {_era_label(ctx, era)}",
        headline=(
            f"{top_city}, {top_host} hosted the most third-party matches of any city {_era_phrase(ctx, era)}: "
            f"{top_count}."
        ),
        facts=facts,
        table=Table(columns=["City", "Host identity", "Third-party matches"], rows=table_rows),
        chart=Chart(
            kind="hbar",
            title=f"Top third-party host cities, {_era_label(ctx, era)}",
            x=labels,
            series=[Series(name="Matches", values=[int(r[2]) for r in rows])],
            x_label="City and host identity",
            y_label="Third-party matches",
            summary=(
                f"Horizontal bar chart of {len(table_rows)} city-host pairs; {top_city}, {top_host} is highest "
                f"with {top_count} matches."
            ),
        ),
        method=(
            "Counts third-party matches by city and reconciled host identity, sorted by count descending, then city "
            "and host name ascending."
        ),
        coverage=[f"{total} third-party matches with city and host identity across {distinct} city-host pairs."],
        caveats=_caveats(ctx, "cities"),
        cannot_tell=_cannot_tell(),
        method_version="q5-cities-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"third_party_matches": total, "city_hosts": distinct},
    )


def host_groups(ctx: ToolContext) -> ToolResult:
    total = int(ctx.store.query_one("select count(*) from matches where third_party and year >= 1960")[0])
    if total == 0:
        return _insufficient(ctx, "host_groups", "Third-party host groups",
                             "no third-party matches since 1960 are shown", {"matches": 0})

    region_rows = ctx.store.query("""
        select coalesce(t.region, 'Unmapped') as region, count(*) as matches
        from matches m
        left join teams t on t.team = m.venue_team
          and (t.valid_from is null or m.year >= t.valid_from)
        where m.third_party and m.year >= 1960
        group by region
        order by matches desc, region asc
    """)
    income_rows = ctx.store.query("""
        select coalesce(t.income_group, 'Unmapped') as income_group, count(*) as matches
        from matches m
        left join teams t on t.team = m.venue_team
          and (t.valid_from is null or m.year >= t.valid_from)
        where m.third_party and m.year >= 1960
        group by income_group
        order by matches desc, income_group asc
    """)
    top_hosts = ctx.store.query("""
        select m.venue_team, count(*) as matches, any_value(t.region), any_value(t.income_group)
        from matches m
        left join teams t on t.team = m.venue_team
          and (t.valid_from is null or m.year >= t.valid_from)
        where m.third_party and m.year >= 1960 and m.venue_team is not null
        group by m.venue_team
        order by matches desc, m.venue_team asc
        limit 20
    """)
    unmapped = sum(int(n) for group, n in region_rows if str(group) == "Unmapped")
    top_region, top_region_count = str(region_rows[0][0]), int(region_rows[0][1])
    top_income, top_income_count = str(income_rows[0][0]), int(income_rows[0][1])
    unmapped_share = pct(unmapped, total)

    table_rows: list[list[Cell]] = [
        [str(host), int(count), str(region) if region is not None else "Unmapped",
         str(income) if income is not None else "Unmapped"]
        for host, count, region, income in top_hosts
    ]
    facts = [
        Fact(id="q5.host_groups.matches", label="Third-party matches since 1960", value=total, unit="matches"),
        Fact(id="q5.host_groups.start_year", label="Start year", value=1960),
        Fact(id="q5.host_groups.top_region", label=f"Most common host WDI region: {top_region}",
             value=top_region_count, unit="matches"),
        Fact(id="q5.host_groups.top_income", label=f"Most common host income group: {top_income}",
             value=top_income_count, unit="matches"),
        Fact(id="q5.host_groups.unmapped_share", label="Unmapped host share", value=unmapped_share, unit="%",
             decimals=1),
        Fact(id="q5.host_groups.top_hosts", label="Frequent hosts shown", value=len(table_rows), unit="hosts"),
        *_disagreement_facts(ctx, "host_groups"),
    ]
    region_chart_rows = [(str(region), int(n)) for region, n in region_rows if str(region) != "Unmapped"]
    return ToolResult(
        tool=TOOL_NAME,
        question=5,
        view="host_groups",
        params={"view": "host_groups", "era": None},
        title="Third-party hosts by WDI region and income group",
        headline=(
            f"Since 1960, {top_region} is the largest mapped host region with {top_region_count} third-party "
            f"matches; the unmapped host share is {unmapped_share}%."
        ),
        facts=facts,
        table=Table(
            columns=["Host identity", "Third-party matches", "WDI region", "Current income group"],
            rows=table_rows[:MAX_TABLE_ROWS],
        ),
        chart=Chart(
            kind="bar",
            title="Third-party matches by host WDI region since 1960",
            x=[r[0] for r in region_chart_rows],
            series=[Series(name="Matches", values=[r[1] for r in region_chart_rows])],
            x_label="Host WDI region",
            y_label="Third-party matches",
            summary=(
                f"Bar chart of mapped host regions since 1960; {top_region} is highest with "
                f"{top_region_count} matches."
            ),
        ),
        method=(
            "For third-party matches since 1960, joins the reconciled host identity to team WDI region and current "
            "income group when the mapping is valid for the match year."
        ),
        coverage=[
            f"Unmapped hosts account for {unmapped_share}% of {total} third-party matches since 1960.",
            f"The table shows the {len(table_rows)} most frequent host identities and their mapped region and "
            "income group.",
        ],
        caveats=_caveats(ctx, "host_groups"),
        cannot_tell=_cannot_tell(),
        method_version="q5-host-groups-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"third_party_matches": total, "top_hosts": len(table_rows),
                    "regions": len(region_rows), "income_groups": len(income_rows)},
    )


def run(ctx: ToolContext, params: Params) -> ToolResult:
    if params.view == "ranking":
        return ranking(ctx, params.era)
    if params.view == "trend":
        return trend(ctx)
    if params.view == "cities":
        return cities(ctx, params.era)
    return host_groups(ctx)
