"""Question 4: descriptive fixture patterns with geopolitical context."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import Cell, Chart, Fact, Series, Table, ToolResult
from .context import ToolContext, pct

TOOL_NAME = "geopolitics"
DESCRIPTION = (
    "Question 4, descriptive geopolitics from fixtures. Views: team_counts = teams active by year, "
    "frequent_pairings = most repeated unordered pairings with W-D-L records, communities = recent fixture-network "
    "communities, region_mixing = same-region and same-income fixture shares by decade."
)

MIN_NODE_MATCHES = 10
MIN_COMMUNITY_MEMBERS = 3
MAX_TABLE_ROWS = 30

EraParam = Literal["early", "interwar", "postwar", "expansion", "modern", "current"]
View = Literal["team_counts", "frequent_pairings", "communities", "region_mixing"]


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    view: View = Field(description="Which deterministic view to return.")
    era: EraParam | None = Field(description="Era for frequent_pairings only; null means all time.")


CARD_ARGUMENTS = {"view": "team_counts", "era": None}


def _decade_label(decade: int) -> str:
    return f"{decade}s"


def _era_label(ctx: ToolContext, era: str | None) -> str:
    if era is None:
        return "all time"
    for item in ctx.reference.eras:
        if item.id == era:
            return item.label
    return era


def _caveats() -> list[str]:
    return [
        "This is observational: fixtures describe scheduled football matches, not political relations.",
        "A team is not always a sovereign state; the dataset includes UK associations, territories, and historical "
        "teams.",
        "Historical teams often have no WDI entity.",
        "Scheduling reflects confederation rules and travel as well as politics.",
    ]


def _cannot_tell() -> str:
    return "Anything about relations between governments or peoples, or the causes of any fixture pattern."


def _insufficient(ctx: ToolContext, view: str, title: str, reason: str, counts: dict[str, int]) -> ToolResult:
    total = counts.get("matches", 0)
    return ToolResult(
        tool=TOOL_NAME,
        question=4,
        view=view,
        params={"view": view, "era": None},
        title=title,
        headline=f"The loaded data has {total} matches, so {reason}.",
        facts=[Fact(id=f"q4.{view}.matches", label="Matches checked", value=total, unit="matches")],
        method="The view returns an explanatory result when the minimum sample is not met.",
        coverage=[f"{total} matches checked."],
        caveats=_caveats(),
        cannot_tell=_cannot_tell(),
        method_version=f"q4-{view}-v1",
        dataset_version=ctx.dataset_version,
        row_counts=counts,
    )


def team_counts(ctx: ToolContext) -> ToolResult:
    rows = ctx.store.query("""
        select year, count(distinct team) as teams
        from (
          select year, home_team as team from matches
          union all
          select year, away_team as team from matches
        )
        group by year
        order by year
    """)
    if not rows:
        return _insufficient(
            ctx,
            "team_counts",
            "Teams playing by year",
            "no yearly team count is shown",
            {"matches": 0},
        )

    labels = [str(int(r[0])) for r in rows]
    counts = [int(r[1]) for r in rows]
    year_to_count = {int(r[0]): int(r[1]) for r in rows}
    peak_year, peak_count = max(year_to_count.items(), key=lambda item: (item[1], -item[0]))
    latest = ctx.store.query_one("select strftime(max(date), '%Y-%m-%d'), max(year), count(*) from matches")
    latest_date = str(latest[0])
    latest_year = int(latest[1])
    latest_full_year = latest_year if latest_date.endswith("12-31") else latest_year - 1
    latest_full_count = year_to_count.get(latest_full_year, 0)

    first_rows = ctx.store.query("""
        select (first_year / 10)::int * 10 as decade, count(*) as teams
        from (
          select team, min(year) as first_year
          from (
            select home_team as team, year from matches
            union all
            select away_team as team, year from matches
          )
          group by team
        )
        group by decade
        order by decade
    """)
    table_rows: list[list[Cell]] = [
        ["First appearances", _decade_label(int(decade)), int(decade), int(n), "Teams whose first match falls here"]
        for decade, n in first_rows
    ]

    for succession in ctx.reference.successions:
        team = str(succession["team"])
        last = ctx.store.query("select max(year) from matches where home_team = ? or away_team = ?", [team, team])
        if last and last[0][0] is not None:
            successors = ", ".join(str(s) for s in succession["successors"]) or "No listed successor"
            table_rows.append(["Exit", team, int(last[0][0]), len(succession["successors"]), successors])

    post_soviet_count = 0
    for team in ctx.reference.post_soviet_states:
        first = ctx.store.query("select min(year) from matches where home_team = ? or away_team = ?", [team, team])
        if first and first[0][0] is not None and int(first[0][0]) > 1991:
            post_soviet_count += 1
    table_rows.append([
        "Post-Soviet states",
        "First match after Soviet dissolution",
        1991,
        post_soviet_count,
        "Russia contains Soviet Union-era records in this dataset",
    ])
    table_rows.append(["Latest date", "Latest match date", latest_year, int(latest_date[5:7]), latest_date])
    omitted_rows = max(0, len(table_rows) - MAX_TABLE_ROWS)
    table_rows = table_rows[:MAX_TABLE_ROWS]

    anchor_facts = [
        Fact(id=f"q4.team_counts.{year}", label=f"Teams playing in {year}", value=year_to_count[year], unit="teams")
        for year in (1900, 1950, 1990, 2000)
        if year in year_to_count
    ]
    facts = [
        *anchor_facts,
        Fact(id="q4.team_counts.peak_year", label="Peak year", value=peak_year),
        Fact(id="q4.team_counts.peak_count", label=f"Teams playing in peak year {peak_year}", value=peak_count,
             unit="teams"),
        Fact(id="q4.team_counts.latest_full_year", label="Latest full year", value=latest_full_year),
        Fact(id="q4.team_counts.latest_full_count", label=f"Teams playing in {latest_full_year}",
             value=latest_full_count, unit="teams"),
        Fact(id="q4.team_counts.latest_match_year", label="Latest match year", value=latest_year),
        Fact(id="q4.team_counts.post_soviet_after_1991", label="Post-Soviet states first appearing after 1991",
             value=post_soviet_count, unit="teams"),
    ]
    headline = (
        f"The busiest year had {peak_count} teams in {peak_year}; the latest full year, {latest_full_year}, "
        f"had {latest_full_count} teams."
    )
    chart = Chart(
        kind="line",
        title="Distinct teams with at least one match by year",
        x=labels,
        series=[Series(name="Teams", values=counts)],
        x_label="Year",
        y_label="Distinct teams",
        y_min=0,
        summary=(
            f"Line chart of teams per year from {labels[0]} to {labels[-1]}; the highest point is {peak_count} "
            f"teams in {peak_year}, and the latest full year is {latest_full_year} with {latest_full_count} teams."
        ),
    )
    coverage = [
        f"The latest year, {latest_year}, is partial; the latest match date is included in the table.",
        "The succession and first-appearance table is clipped when needed.",
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=4,
        view="team_counts",
        params={"view": "team_counts", "era": None},
        title="Teams playing by year",
        headline=headline,
        facts=facts,
        table=Table(columns=["Section", "Item", "Year", "Count", "Details"], rows=table_rows),
        chart=chart,
        method=(
            "Counts distinct teams with at least one match in each year, first appearances by decade, listed "
            "successions with last match years from the data, and post-Soviet teams first appearing after 1991."
        ),
        coverage=coverage,
        caveats=_caveats(),
        cannot_tell=_cannot_tell(),
        method_version="q4-team-counts-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"years": len(rows), "table_rows": len(table_rows), "omitted_table_rows": omitted_rows},
    )


def frequent_pairings(ctx: ToolContext, era: EraParam | None) -> ToolResult:
    if era is None:
        rows = ctx.store.query("select home_team, away_team, home_score, away_score from matches")
    else:
        rows = ctx.store.query(
            "select home_team, away_team, home_score, away_score from matches where era = ?",
            [era],
        )
    if not rows:
        title = f"Frequent pairings, {_era_label(ctx, era)}"
        return _insufficient(ctx, "frequent_pairings", title, "no pair ranking is shown", {"matches": 0})

    counts: Counter[tuple[str, str]] = Counter()
    records: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for home, away, home_score, away_score in rows:
        a, b = sorted((str(home), str(away)))
        pair = (a, b)
        counts[pair] += 1
        a_score = int(home_score) if home == a else int(away_score)
        b_score = int(away_score) if home == a else int(home_score)
        if a_score > b_score:
            records[pair][0] += 1
        elif a_score == b_score:
            records[pair][1] += 1
        else:
            records[pair][2] += 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))[:10]
    table_rows: list[list[Cell]] = [
        [f"{a} v {b}", n, records[(a, b)][0], records[(a, b)][1], records[(a, b)][2]]
        for (a, b), n in ranked
    ]
    if not ranked:
        return _insufficient(ctx, "frequent_pairings", "Frequent pairings", "no pair ranking is shown", {"matches": 0})

    top_pair, top_count = ranked[0]
    top_record = records[top_pair]
    facts = [
        Fact(id="q4.pairings.matches", label=f"Matches in {_era_label(ctx, era)}", value=len(rows), unit="matches"),
        Fact(id="q4.pairings.distinct_pairs", label="Distinct unordered pairs", value=len(counts), unit="pairs"),
        Fact(id="q4.pairings.top.matches", label=f"Most frequent pair: {top_pair[0]} v {top_pair[1]}",
             value=top_count, unit="matches"),
        Fact(id="q4.pairings.top.wins", label=f"{top_pair[0]} wins against {top_pair[1]}", value=top_record[0]),
        Fact(id="q4.pairings.top.draws", label=f"{top_pair[0]} draws against {top_pair[1]}", value=top_record[1]),
        Fact(id="q4.pairings.top.losses", label=f"{top_pair[0]} losses against {top_pair[1]}", value=top_record[2]),
    ]
    labels = [f"{a} v {b}" for (a, b), _ in ranked]
    values = [n for _, n in ranked]
    return ToolResult(
        tool=TOOL_NAME,
        question=4,
        view="frequent_pairings",
        params={"view": "frequent_pairings", "era": era},
        title=f"Most frequent pairings, {_era_label(ctx, era)}",
        headline=(
            f"{top_pair[0]} v {top_pair[1]} is the most frequent pairing in {_era_label(ctx, era)}, "
            f"with {top_count} matches."
        ),
        facts=facts,
        table=Table(columns=["Pair", "Matches", "First-team wins", "Draws", "First-team losses"], rows=table_rows),
        chart=Chart(
            kind="hbar",
            title=f"Top repeated pairings, {_era_label(ctx, era)}",
            x=labels,
            series=[Series(name="Matches", values=values)],
            x_label="Pair",
            y_label="Matches",
            summary=(
                f"Horizontal bar chart of the {len(labels)} most frequent pairings; {top_pair[0]} v {top_pair[1]} "
                f"is highest with {top_count} matches."
            ),
        ),
        method=(
            "Counts unordered pairs of teams, sorted by match count descending and team names ascending; W-D-L is "
            "reported from the alphabetically first team's side."
        ),
        coverage=[f"{len(rows)} matches and {len(counts)} distinct unordered pairs in {_era_label(ctx, era)}."],
        caveats=_caveats(),
        cannot_tell=_cannot_tell(),
        method_version="q4-frequent-pairings-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"matches": len(rows), "pairs": len(counts)},
    )


def _community_data(ctx: ToolContext, min_node_matches: int) -> dict[str, Any]:
    current = next(era for era in ctx.reference.eras if era.id == "current")
    key = f"q4.communities.{ctx.dataset_version}.{current.start}.{current.end}.{min_node_matches}"
    cached = ctx.cache.get(key)
    if cached is not None:
        return cached

    import networkx as nx

    rows = ctx.store.query(
        "select home_team, away_team from matches where year between ? and ?",
        [current.start, current.end],
    )
    appearances: Counter[str] = Counter()
    edges: Counter[tuple[str, str]] = Counter()
    for home, away in rows:
        h, a = str(home), str(away)
        appearances[h] += 1
        appearances[a] += 1
        first, second = sorted((h, a))
        edges[(first, second)] += 1

    kept = {team for team, n in appearances.items() if n >= min_node_matches}
    graph = nx.Graph()
    for team in sorted(kept):
        graph.add_node(team)
    for (a, b), weight in sorted(edges.items()):
        if a in kept and b in kept:
            graph.add_edge(a, b, weight=weight)
    communities = [tuple(sorted(c)) for c in nx.community.louvain_communities(graph, weight="weight", seed=42)]
    communities.sort(key=lambda c: (-len(c), c[0] if c else ""))
    result: dict[str, Any] = {
        "start": current.start,
        "end": current.end,
        "matches": len(rows),
        "appearances": appearances,
        "graph": graph,
        "communities": communities,
    }
    ctx.cache[key] = result
    return result


def communities(ctx: ToolContext, min_node_matches: int = MIN_NODE_MATCHES) -> ToolResult:
    data = _community_data(ctx, min_node_matches)
    graph = data["graph"]
    communities_found: list[tuple[str, ...]] = data["communities"]
    if len(graph) == 0 or not communities_found:
        return _insufficient(
            ctx,
            "communities",
            "Fixture-network communities",
            f"no team reached the minimum of {min_node_matches} matches",
            {"matches": int(data["matches"]), "nodes": 0},
        )

    team_rows = ctx.store.query("select team, region, valid_from from teams")
    end_year = int(data["end"])
    team_region = {
        str(team): str(region)
        for team, region, valid_from in team_rows
        if region is not None and (valid_from is None or int(valid_from) <= end_year)
    }
    appearances: Counter[str] = data["appearances"]
    agreement_n = 0
    mapped_n = 0
    table_rows: list[list[Cell]] = []
    omitted = 0
    for index, community in enumerate(communities_found, start=1):
        region_counts = Counter(team_region[t] for t in community if t in team_region)
        mapped = sum(region_counts.values())
        top_region = ""
        share = 0.0
        if region_counts:
            top_region, top_region_count = sorted(region_counts.items(), key=lambda item: (-item[1], item[0]))[0]
            share = pct(top_region_count, mapped)
            agreement_n += top_region_count
            mapped_n += mapped
        if len(community) >= MIN_COMMUNITY_MEMBERS and len(table_rows) < MAX_TABLE_ROWS:
            leaders = sorted(community, key=lambda team: (-appearances[team], team))[:3]
            table_rows.append([index, len(community), ", ".join(leaders), top_region or "Unmapped", share, mapped])
        elif len(community) >= MIN_COMMUNITY_MEMBERS:
            omitted += 1

    agreement = pct(agreement_n, mapped_n)
    tabled = len(table_rows)
    facts = [
        Fact(id="q4.communities.start_year", label="Window start year", value=int(data["start"])),
        Fact(id="q4.communities.end_year", label="Window end year", value=int(data["end"])),
        Fact(id="q4.communities.matches", label="Matches in window", value=int(data["matches"]), unit="matches"),
        Fact(id="q4.communities.nodes", label="Nodes with minimum matches", value=len(graph), unit="teams"),
        Fact(id="q4.communities.edges", label="Weighted fixture links", value=graph.number_of_edges()),
        Fact(id="q4.communities.count", label="Louvain communities", value=len(communities_found)),
        Fact(id="q4.communities.mapped_nodes", label="Mapped nodes used for region agreement", value=mapped_n,
             unit="teams"),
        Fact(id="q4.communities.region_agreement", label="Mapped nodes in their community's common region",
             value=agreement, unit="%", decimals=1),
        Fact(id="q4.communities.table_rows", label="Communities shown in table", value=tabled),
        Fact(id="q4.communities.omitted", label="Communities omitted from table", value=omitted),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=4,
        view="communities",
        params={"view": "communities", "era": None},
        title="Fixture-network communities, current era",
        headline=(
            f"Louvain found {len(communities_found)} fixture communities; {agreement}% of mapped teams matched "
            "their community's most common WDI region."
        ),
        facts=facts,
        table=Table(
            columns=["Community", "Teams", "Most active teams", "Most common WDI region", "Region share %",
                     "Mapped teams"],
            rows=table_rows,
        ),
        chart=Chart(
            kind="bar",
            title="Fixture-network community sizes",
            x=[str(i) for i in range(1, len(communities_found) + 1)],
            series=[Series(name="Teams", values=[len(c) for c in communities_found])],
            x_label="Community",
            y_label="Teams",
            summary=(
                f"Bar chart of {len(communities_found)} community sizes; the largest has "
                f"{len(communities_found[0])} teams and {tabled} communities are shown in the table."
            ),
        ),
        method=(
            "Builds the 2010-2026 fixture network for teams with at least the minimum number of matches, weights "
            "edges by match count, then runs NetworkX Louvain communities with weight='weight' and seed=42."
        ),
        coverage=[
            f"{int(data['matches'])} matches from {int(data['start'])} to {int(data['end'])}; "
            f"{len(graph)} teams met the node threshold.",
            f"Only communities meeting the member threshold are tabled; {omitted} were omitted.",
        ],
        caveats=_caveats(),
        cannot_tell=_cannot_tell(),
        method_version="q4-communities-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"matches": int(data["matches"]), "nodes": len(graph), "communities": len(communities_found)},
    )


def region_mixing(ctx: ToolContext) -> ToolResult:
    rows = ctx.store.query("""
        select m.decade, count(*) as matches,
          count(*) filter (
            where ht.region is not null and awt.region is not null
              and (ht.valid_from is null or m.year >= ht.valid_from)
              and (awt.valid_from is null or m.year >= awt.valid_from)
          ) as mapped,
          count(*) filter (
            where ht.region is not null and awt.region is not null
              and (ht.valid_from is null or m.year >= ht.valid_from)
              and (awt.valid_from is null or m.year >= awt.valid_from)
              and ht.region = awt.region
          ) as same_region,
          count(*) filter (
            where ht.region is not null and awt.region is not null
              and (ht.valid_from is null or m.year >= ht.valid_from)
              and (awt.valid_from is null or m.year >= awt.valid_from)
              and ht.income_group = awt.income_group
          ) as same_income
        from matches m
        left join teams ht on ht.team = m.home_team
        left join teams awt on awt.team = m.away_team
        where m.year >= 1960
        group by m.decade
        order by m.decade
    """)
    kept = [r for r in rows if int(r[2]) > 0]
    if not kept:
        return _insufficient(ctx, "region_mixing", "Region and income mixing by decade",
                             "no mapped decade is shown", {"matches": sum(int(r[1]) for r in rows)})

    table_rows: list[list[Cell]] = []
    labels: list[str] = []
    same_region_values: list[float] = []
    same_income_values: list[float] = []
    coverage_values: list[float] = []
    for decade, matches, mapped, same_region, same_income in kept:
        labels.append(_decade_label(int(decade)))
        region_share = pct(int(same_region), int(mapped))
        income_share = pct(int(same_income), int(mapped))
        coverage = pct(int(mapped), int(matches))
        same_region_values.append(region_share)
        same_income_values.append(income_share)
        coverage_values.append(coverage)
        table_rows.append([labels[-1], int(matches), int(mapped), coverage, region_share, income_share])

    peak_i = max(range(len(same_region_values)), key=lambda i: (same_region_values[i], -i))
    latest_i = len(labels) - 1
    facts = [
        Fact(id=f"q4.region_mixing.{labels[0]}.same_region", label=f"Same-region share, {labels[0]}",
             value=same_region_values[0], unit="%", decimals=1),
        Fact(id=f"q4.region_mixing.{labels[latest_i]}.same_region",
             label=f"Same-region share, {labels[latest_i]}", value=same_region_values[latest_i], unit="%",
             decimals=1),
        Fact(id=f"q4.region_mixing.{labels[latest_i]}.same_income",
             label=f"Same-income share, {labels[latest_i]}", value=same_income_values[latest_i], unit="%",
             decimals=1),
        Fact(id=f"q4.region_mixing.{labels[peak_i]}.peak",
             label=f"Highest same-region decade: {labels[peak_i]}", value=same_region_values[peak_i], unit="%",
             decimals=1),
        Fact(id=f"q4.region_mixing.{labels[latest_i]}.coverage",
             label=f"Both-team WDI-region coverage, {labels[latest_i]}", value=coverage_values[latest_i], unit="%",
             decimals=1),
        Fact(id="q4.region_mixing.matches", label="Matches since 1960", value=sum(int(r[1]) for r in rows),
             unit="matches"),
    ]
    return ToolResult(
        tool=TOOL_NAME,
        question=4,
        view="region_mixing",
        params={"view": "region_mixing", "era": None},
        title="Intra-region and intra-income fixtures by decade",
        headline=(
            f"Among mapped matches, the same-region share was {same_region_values[0]}% in the {labels[0]} and "
            f"{same_region_values[latest_i]}% in the {labels[latest_i]}."
        ),
        facts=facts,
        table=Table(
            columns=["Decade", "Matches", "Both teams mapped", "Coverage %", "Same region %", "Same income %"],
            rows=table_rows[:MAX_TABLE_ROWS],
        ),
        chart=Chart(
            kind="line",
            title="Same-region and same-income fixture shares",
            x=labels,
            series=[
                Series(name="Same WDI region %", values=same_region_values),
                Series(name="Same income group %", values=same_income_values),
            ],
            x_label="Decade",
            y_label="Share among mapped matches",
            y_unit="%",
            y_min=0,
            y_max=100,
            summary=(
                f"Line chart from {labels[0]} to {labels[latest_i]}; same-region fixtures peak in the "
                f"{labels[peak_i]} at {same_region_values[peak_i]}%, while the latest same-income share is "
                f"{same_income_values[latest_i]}%."
            ),
        ),
        method=(
            "For each decade since 1960, among matches where both teams have WDI regions valid for that match year, "
            "computes shares where the teams share a WDI region or current WDI income group."
        ),
        coverage=[
            f"Coverage is the share of all matches in a decade where both teams have a valid WDI-region mapping; "
            f"the latest shown coverage is {coverage_values[latest_i]}%.",
        ],
        caveats=[*_caveats(), "Income groups use the current WDI classification."],
        cannot_tell=_cannot_tell(),
        method_version="q4-region-mixing-v1",
        dataset_version=ctx.dataset_version,
        row_counts={"matches": sum(int(r[1]) for r in rows), "decades": len(kept)},
    )


def run(ctx: ToolContext, params: Params) -> ToolResult:
    if params.view == "team_counts":
        return team_counts(ctx)
    if params.view == "frequent_pairings":
        return frequent_pairings(ctx, params.era)
    if params.view == "communities":
        return communities(ctx)
    return region_mixing(ctx)
