"""Question 3: trends in international football throughout the ages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import Cell, Chart, Fact, Series, Table, ToolResult
from . import ratings
from .context import ToolContext, pct, slug
from .stats import mean, percentile, stdev, wilson

TOOL_NAME = "trends"
DESCRIPTION = (
    "Question 3, trends throughout the ages. Metrics: home_advantage = home win, draw, and away win shares per decade "
    "in non-neutral matches; goals_per_match = average goals per match per decade, overall, competitive, and "
    "friendly-like; strength_spread = how spread out team ratings are among active teams each year (distribution of "
    "teams' strength); goal_timing = shares of penalties, own goals, and late goals from goalscorer data (partial "
    "coverage); strength_by_region and strength_by_income = mean team rating by World Bank region or income group "
    "per decade since 1960 (development lens)."
)
MIN_DECADE_MATCHES = 100
MIN_ACTIVE_TEAMS = 10
MIN_DECADE_GOALS = 200
MIN_GROUP_TEAM_YEARS = 20
LATE_MINUTE = 75
DEVELOPMENT_FROM = 1960
Metric = Literal["home_advantage", "goals_per_match", "strength_spread", "goal_timing", "strength_by_region",
                 "strength_by_income"]
INCOME_ORDER = ("High income", "Upper middle income", "Lower middle income", "Low income")
CARD_ARGUMENTS = {"metric": "home_advantage"}


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Metric = Field(description="Which trend to return; see the tool description.")


def _decade_label(decade: int) -> str:
    return f"{decade}s"


def _insufficient(ctx: ToolContext, metric: str, title: str, matches: int, min_matches: int) -> ToolResult:
    return ToolResult(
        tool="trends", question=3, view=metric, params={"metric": metric}, title=title,
        headline=f"No decade has the minimum of {min_matches} matches in the loaded data, so no trend is shown.",
        facts=[Fact(id=f"q3.{metric}.minimum", label="Minimum sample per decade", value=min_matches),
               Fact(id=f"q3.{metric}.available", label="Matches available", value=matches, unit="matches")],
        method="Per-decade aggregates need a minimum sample; none was met.",
        coverage=[f"{matches:,} matches in total."],
        cannot_tell="A trend from this little data.",
        method_version=f"q3-{metric}-v1", dataset_version=ctx.dataset_version, row_counts={"matches": matches},
    )


def home_advantage(ctx: ToolContext, min_matches: int = MIN_DECADE_MATCHES) -> ToolResult:
    rows = ctx.store.query("""
        select decade, count(*),
          count(*) filter (where home_score > away_score),
          count(*) filter (where home_score = away_score),
          count(*) filter (where home_score < away_score),
          avg(home_score - away_score)
        from matches where not neutral group by decade order by decade""")
    total_non_neutral = sum(int(r[1]) for r in rows)
    kept = [r for r in rows if int(r[1]) >= min_matches]
    dropped = [_decade_label(int(r[0])) for r in rows if int(r[1]) < min_matches]
    if not kept:
        return _insufficient(ctx, "home_advantage", "Home advantage over time", total_non_neutral, min_matches)
    table_rows: list[list[Cell]] = []
    home_pct: list[float] = []
    draw_pct: list[float] = []
    away_pct: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    labels: list[str] = []
    for decade, n, wins, draws, losses, gd in kept:
        share, lo, hi = wilson(int(wins), int(n))
        labels.append(_decade_label(int(decade)))
        home_pct.append(round(share, 1))
        lower.append(round(lo, 1))
        upper.append(round(hi, 1))
        draw_pct.append(pct(int(draws), int(n)))
        away_pct.append(pct(int(losses), int(n)))
        table_rows.append([labels[-1], int(n), home_pct[-1], draw_pct[-1], away_pct[-1],
                           f"{lower[-1]}-{upper[-1]}", round(float(gd), 2)])
    all_n = sum(int(r[1]) for r in kept)
    all_wins = sum(int(r[2]) for r in kept)
    first_share, last_share = home_pct[0], home_pct[-1]
    change = round(last_share - first_share, 1)
    peak_i = max(range(len(home_pct)), key=lambda i: home_pct[i])
    low_i = min(range(len(home_pct)), key=lambda i: home_pct[i])
    facts = [
        Fact(id=f"q3.home.{labels[0]}.home_win_pct", label=f"Home win share, {labels[0]}", value=first_share,
             unit="%", decimals=1),
        Fact(id=f"q3.home.{labels[-1]}.home_win_pct", label=f"Home win share, {labels[-1]}", value=last_share,
             unit="%", decimals=1),
        Fact(id="q3.home.change_pts", label=f"Change from {labels[0]} to {labels[-1]}", value=change,
             unit="percentage points", decimals=1),
        Fact(id=f"q3.home.{labels[peak_i]}.peak", label=f"Highest decade: {labels[peak_i]}",
             value=home_pct[peak_i], unit="%", decimals=1),
        Fact(id=f"q3.home.{labels[low_i]}.low", label=f"Lowest decade: {labels[low_i]}",
             value=home_pct[low_i], unit="%", decimals=1),
        Fact(id="q3.home.all.home_win_pct", label="Home win share, all decades shown",
             value=pct(all_wins, all_n), unit="%", decimals=1),
        Fact(id=f"q3.home.{labels[-1]}.away_win_pct", label=f"Away win share, {labels[-1]}", value=away_pct[-1],
             unit="%", decimals=1),
        Fact(id="q3.home.matches", label="Non-neutral matches analysed", value=all_n, unit="matches"),
    ]
    direction = "fell" if change < 0 else "rose"
    headline = (f"Home teams won {first_share}% of non-neutral matches in the {labels[0]} and "
                f"{last_share}% in the {labels[-1]}: the share {direction} by {abs(change)} percentage points.")
    chart = Chart(
        kind="line", title="Home advantage by decade (non-neutral matches)", x=labels,
        series=[Series(name="Home win %", values=home_pct, lower=lower, upper=upper),
                Series(name="Draw %", values=draw_pct), Series(name="Away win %", values=away_pct)],
        x_label="Decade", y_label="Share of matches", y_unit="%", y_min=0, y_max=100,
        summary=(f"Line chart of results in non-neutral matches by decade from {labels[0]} to {labels[-1]}. "
                 f"The home win share goes from {first_share}% to {last_share}%, peaking at {home_pct[peak_i]}% "
                 f"in the {labels[peak_i]}; the away win share ends at {away_pct[-1]}%."),
    )
    coverage = [f"{all_n:,} non-neutral matches of {total_non_neutral:,}; neutral-venue matches are excluded."]
    if dropped:
        coverage.append(f"Decades with fewer than {min_matches} non-neutral matches are not shown: "
                        + ", ".join(dropped) + ".")
    return ToolResult(
        tool="trends", question=3, view="home_advantage", params={"metric": "home_advantage"},
        title="Home advantage over time", headline=headline, facts=facts,
        table=Table(columns=["Decade", "Matches", "Home win %", "Draw %", "Away win %", "Home win 95% CI",
                             "Mean home goal difference"], rows=table_rows),
        chart=chart,
        method=("Share of non-neutral matches won, drawn, and lost by the home team per decade, with 95% Wilson "
                "intervals for the home win share, and the mean home goal difference."),
        coverage=coverage,
        caveats=["The mix of matches changes over time: many more teams and many more friendlies play in later "
                 "decades, which moves the averages.",
                 "The neutral flag comes from the data; 51 matches flagged neutral were played in a participant's "
                 "own country."],
        cannot_tell="Why home advantage changed: travel, refereeing, and crowds are not in the data.",
        method_version="q3-home-v1", dataset_version=ctx.dataset_version,
        row_counts={"matches": all_n, "decades": len(kept)},
    )


def goals_per_match(ctx: ToolContext, min_matches: int = MIN_DECADE_MATCHES, split_min: int = 30) -> ToolResult:
    rows = ctx.store.query("""
        select decade, count(*), avg(goals),
          count(*) filter (where competitive), avg(goals) filter (where competitive),
          count(*) filter (where friendly_like), avg(goals) filter (where friendly_like)
        from matches group by decade order by decade""")
    kept = [r for r in rows if int(r[1]) >= min_matches]
    dropped = [_decade_label(int(r[0])) for r in rows if int(r[1]) < min_matches]
    if not kept:
        return _insufficient(ctx, "goals_per_match", "Total goals per match over time",
                             sum(int(r[1]) for r in rows), min_matches)
    labels = [_decade_label(int(r[0])) for r in kept]
    overall = [round(float(r[2]), 2) for r in kept]
    competitive = [round(float(r[4]), 2) if r[4] is not None and int(r[3]) >= split_min else None for r in kept]
    friendly = [round(float(r[6]), 2) if r[6] is not None and int(r[5]) >= split_min else None for r in kept]
    peak_i = max(range(len(overall)), key=lambda i: overall[i])
    low_i = min(range(len(overall)), key=lambda i: overall[i])
    total = ctx.store.query_one("select count(*), avg(goals) from matches")
    facts = [
        Fact(id=f"q3.goals.{labels[0]}", label=f"Goals per match, {labels[0]}", value=overall[0], decimals=2),
        Fact(id=f"q3.goals.{labels[-1]}", label=f"Goals per match, {labels[-1]}", value=overall[-1], decimals=2),
        Fact(id=f"q3.goals.{labels[peak_i]}.peak", label=f"Highest decade: {labels[peak_i]}",
             value=overall[peak_i], decimals=2),
        Fact(id=f"q3.goals.{labels[low_i]}.low", label=f"Lowest decade: {labels[low_i]}",
             value=overall[low_i], decimals=2),
        Fact(id="q3.goals.all", label="Goals per match, all matches", value=round(float(total[1]), 2), decimals=2),
        Fact(id="q3.goals.matches", label="Matches analysed", value=int(total[0]), unit="matches"),
    ]
    table_rows: list[list[Cell]] = [[labels[i], int(r[1]), overall[i], competitive[i], friendly[i]]
                                    for i, r in enumerate(kept)]
    return ToolResult(
        tool="trends", question=3, view="goals_per_match", params={"metric": "goals_per_match"},
        title="Total goals per match over time",
        headline=(f"Matches averaged {overall[0]} goals in the {labels[0]} and {overall[-1]} in the {labels[-1]}; "
                  f"the lowest decade was the {labels[low_i]} at {overall[low_i]}."),
        facts=facts,
        table=Table(columns=["Decade", "Matches", "Goals per match", "Competitive", "Friendly-like"],
                    rows=table_rows),
        chart=Chart(kind="line", title="Goals per match by decade", x=labels,
                    series=[Series(name="All matches", values=overall), Series(name="Competitive", values=competitive),
                            Series(name="Friendly-like", values=friendly)],
                    x_label="Decade", y_label="Goals per match", y_min=0,
                    summary=(f"Line chart of average goals per match by decade from {labels[0]} ({overall[0]}) to "
                             f"{labels[-1]} ({overall[-1]}), with separate lines for competitive and friendly-like "
                             f"matches; the lowest decade is the {labels[low_i]} ({overall[low_i]}).")),
        method=("Average of home plus away goals per match (after extra time, excluding shootouts) per decade, "
                "overall and split into competitive and friendly-like matches (splits need 30 matches)."),
        coverage=[f"All {int(total[0]):,} matches."] + (
            [f"Decades with fewer than {min_matches} matches are not shown: {', '.join(dropped)}."]
            if dropped else []),
        caveats=["More teams of very different strength play each other in later decades, and friendlies make up "
                 "a changing share of matches, so averages mix different kinds of games."],
        cannot_tell="Why scoring fell: tactics, rules, and player data are not in this dataset.",
        method_version="q3-goals-v1", dataset_version=ctx.dataset_version,
        row_counts={"matches": int(total[0]), "decades": len(kept)},
    )


def strength_spread(ctx: ToolContext, min_teams: int = MIN_ACTIVE_TEAMS) -> ToolResult:
    """Distribution of team strength: rating spread among active teams at each year end."""
    history = ctx.ratings()
    years = sorted({m.year for m in history.matches})
    last_date = history.matches[-1].date if history.matches else ""
    rows = []
    for year in years:
        active = sorted(ratings.active_teams(history, year).values())
        if len(active) < min_teams:
            continue
        top10 = mean(active[-10:])
        median = percentile(active, 50)
        rows.append((year, len(active), round(stdev(active), 1), round(percentile(active, 10)),
                     round(median), round(percentile(active, 90)), round(top10 - median)))
    if not rows:
        return _insufficient(ctx, "strength_spread", "Distribution of teams' strength", len(history.matches), min_teams)
    first, last = rows[0], rows[-1]
    peak = max(rows, key=lambda r: (r[2], -r[0]))
    step = max(1, len(rows) // 28)
    sampled = [r for i, r in enumerate(rows) if i % step == 0 or r is last][-30:]
    facts = [
        Fact(id=f"q3.spread.{first[0]}.sd", label=f"Rating spread (SD), {first[0]}", value=first[2], unit="points",
             decimals=1),
        Fact(id=f"q3.spread.{last[0]}.sd", label=f"Rating spread (SD), {last[0]}", value=last[2], unit="points",
             decimals=1),
        Fact(id=f"q3.spread.{peak[0]}.max_sd", label=f"Widest spread: {peak[0]}", value=peak[2], unit="points",
             decimals=1),
        Fact(id=f"q3.spread.{first[0]}.teams", label=f"Active teams, {first[0]}", value=first[1], unit="teams"),
        Fact(id=f"q3.spread.{last[0]}.teams", label=f"Active teams, {last[0]}", value=last[1], unit="teams"),
        Fact(id=f"q3.spread.{last[0]}.p90_p10", label=f"Gap between 90th and 10th percentile, {last[0]}",
             value=last[5] - last[3], unit="points"),
        Fact(id=f"q3.spread.{last[0]}.top10_gap", label=f"Top-ten mean minus median, {last[0]}", value=last[6],
             unit="points"),
    ]
    return ToolResult(
        tool="trends", question=3, view="strength_spread", params={"metric": "strength_spread"},
        title="Distribution of teams' strength over time",
        headline=(f"The spread of ratings among active teams was {first[2]} points in {first[0]} with {first[1]} "
                  f"teams and {last[2]} points in {last[0]} with {last[1]} teams; it was widest in {peak[0]} at "
                  f"{peak[2]}."),
        facts=facts,
        table=Table(columns=["Year", "Active teams", "Spread (SD)", "10th percentile", "Median", "90th percentile",
                             "Top-ten mean minus median"],
                    rows=[list(r) for r in sampled]),
        chart=Chart(kind="line", title="Spread of team ratings at each year end", x=[str(r[0]) for r in rows],
                    series=[Series(name="Spread (SD)", values=[r[2] for r in rows]),
                            Series(name="Top-ten mean minus median", values=[r[6] for r in rows])],
                    x_label="Year", y_label="Rating points", y_min=0,
                    summary=(f"Line chart by year from {first[0]} to {last[0]} of the standard deviation of active "
                             f"teams' ratings ({first[2]} to {last[2]} points, highest {peak[2]} in {peak[0]}) and "
                             f"of the gap between the top-ten mean and the median ({last[6]} points in {last[0]}).")),
        method=("For each year end, teams active in that year or the three before it are ranked by their latest "
                "rating (method ratings-v1); the tool reports how spread out those ratings are."),
        coverage=[f"Years with at least {min_teams} active teams: {first[0]} to {last[0]}. The data ends on "
                  f"{last_date}, so the last year is partial."],
        caveats=["The number of active teams grows from a handful to more than 200, and ratings are relative within "
                 "the pool, so a wider spread partly reflects many new, weaker-rated teams joining.",
                 "The table shows a sample of years; the chart shows every year."],
        cannot_tell="Whether football became more or less competitive in any absolute sense.",
        method_version="q3-spread-v1", dataset_version=ctx.dataset_version,
        row_counts={"years": len(rows), "matches": len(history.matches)},
    )


def goal_timing(ctx: ToolContext, min_goals: int = MIN_DECADE_GOALS) -> ToolResult:
    """Penalty, own-goal, and late-goal shares, from matches with complete goal timelines only."""
    rows = ctx.store.query(f"""
        select m.decade, count(*) as goals,
          count(*) filter (where g.penalty), count(*) filter (where g.own_goal),
          count(*) filter (where g.minute is not null), count(*) filter (where g.minute > {LATE_MINUTE})
        from goals g join matches m using (match_id)
        where m.has_timeline group by m.decade order by m.decade""")
    coverage_rows = {int(d): (int(s), int(t)) for d, s, t in ctx.store.query(
        "select decade, count(*) filter (where goals > 0), count(*) filter (where has_timeline and goals > 0) "
        "from matches group by decade")}
    kept = [r for r in rows if int(r[1]) >= min_goals]
    if not kept:
        total = sum(int(r[1]) for r in rows)
        return _insufficient(ctx, "goal_timing", "Goal timing and penalties", total, min_goals)
    labels = [_decade_label(int(r[0])) for r in kept]
    pen = [pct(int(r[2]), int(r[1])) for r in kept]
    own = [pct(int(r[3]), int(r[1])) for r in kept]
    late = [pct(int(r[5]), int(r[4])) for r in kept]
    cov = [pct(coverage_rows[int(r[0])][1], coverage_rows[int(r[0])][0]) for r in kept]
    total_goals = sum(int(r[1]) for r in kept)
    table_rows: list[list[Cell]] = [[labels[i], int(r[1]), pen[i], own[i], late[i], cov[i]] for i, r in enumerate(kept)]
    facts = [
        Fact(id=f"q3.timing.{labels[0]}.penalty_pct", label=f"Goals from penalties, {labels[0]}", value=pen[0],
             unit="%", decimals=1),
        Fact(id=f"q3.timing.{labels[-1]}.penalty_pct", label=f"Goals from penalties, {labels[-1]}", value=pen[-1],
             unit="%", decimals=1),
        Fact(id=f"q3.timing.{labels[0]}.late_pct", label=f"Goals after minute {LATE_MINUTE}, {labels[0]}",
             value=late[0], unit="%", decimals=1),
        Fact(id=f"q3.timing.{labels[-1]}.late_pct", label=f"Goals after minute {LATE_MINUTE}, {labels[-1]}",
             value=late[-1], unit="%", decimals=1),
        Fact(id=f"q3.timing.{labels[-1]}.own_goal_pct", label=f"Own goals, {labels[-1]}", value=own[-1], unit="%",
             decimals=1),
        Fact(id=f"q3.timing.{labels[-1]}.coverage_pct", label=f"Scoring matches with a goal timeline, {labels[-1]}",
             value=cov[-1], unit="%", decimals=1),
        Fact(id="q3.timing.goals", label="Goals with timelines analysed", value=total_goals, unit="goals"),
        Fact(id="q3.timing.late_minute", label="Late-goal threshold (minute)", value=LATE_MINUTE),
    ]
    return ToolResult(
        tool="trends", question=3, view="goal_timing", params={"metric": "goal_timing"},
        title="Goal timing and penalties over time (goalscorer data)",
        headline=(f"In matches with goal timelines, penalties were {pen[0]}% of goals in the {labels[0]} and "
                  f"{pen[-1]}% in the {labels[-1]}; goals after minute {LATE_MINUTE} went from {late[0]}% to "
                  f"{late[-1]}%."),
        facts=facts,
        table=Table(columns=["Decade", "Goals", "Penalty %", "Own goal %", f"After minute {LATE_MINUTE} %",
                             "Timeline coverage %"], rows=table_rows),
        chart=Chart(kind="line", title="Share of goals by type and timing, by decade", x=labels,
                    series=[Series(name="Penalties %", values=pen), Series(name=f"After minute {LATE_MINUTE} %",
                                                                            values=late),
                            Series(name="Own goals %", values=own)],
                    x_label="Decade", y_label="Share of goals", y_unit="%", y_min=0,
                    summary=(f"Line chart by decade from {labels[0]} to {labels[-1]}: penalties {pen[0]}% to "
                             f"{pen[-1]}%, goals after minute {LATE_MINUTE} {late[0]}% to {late[-1]}%, own goals "
                             f"ending at {own[-1]}%.")),
        method=(f"Only matches whose scorer records add up to the final score are used. Shares are of all their "
                f"goals; the late-goal share uses goals with a recorded minute, counting minute {LATE_MINUTE + 1} "
                f"onward, including extra time."),
        coverage=[f"{total_goals:,} goals in matches with complete timelines; decades with fewer than {min_goals} "
                  f"such goals are not shown.",
                  f"Timeline coverage of scoring matches reaches {cov[-1]}% in the {labels[-1]}."],
        caveats=["Goalscorer records cover about a third of all goals, more for recent decades and major "
                 "tournaments, so these shares describe the covered matches, not all matches."],
        cannot_tell="Anything about players beyond goals, or why penalty and late-goal shares changed.",
        method_version="q3-timing-v1", dataset_version=ctx.dataset_version,
        row_counts={"goals": total_goals, "decades": len(kept)},
    )


def _strength_by_group(ctx: ToolContext, column: str, min_team_years: int) -> ToolResult:
    metric = "strength_by_region" if column == "region" else "strength_by_income"
    noun = "WDI region" if column == "region" else "WDI income group"

    def who(group: str) -> str:
        return group if column == "region" else f"{group.lower()} economies"
    history = ctx.ratings()
    mapping = {team: (group, valid_from) for team, group, valid_from in ctx.store.query(
        f"select team, {column}, valid_from from teams where {column} is not null and {column} <> ''")}
    cells: dict[tuple[str, int], list[float]] = {}
    teams_in: dict[tuple[str, int], set[str]] = {}
    total = unmapped = 0
    for team, years in history.year_end.items():
        for year, rating in years.items():
            if year < DEVELOPMENT_FROM:
                continue
            total += 1
            group = mapping.get(team)
            if not group or (group[1] is not None and year < group[1]):
                unmapped += 1
                continue
            key = (group[0], year // 10 * 10)
            cells.setdefault(key, []).append(rating)
            teams_in.setdefault(key, set()).add(team)
    decades = sorted({d for _, d in cells})
    groups = sorted({g for g, _ in cells}, key=lambda g: (INCOME_ORDER.index(g) if g in INCOME_ORDER else 99, g))
    if not decades:
        return _insufficient(ctx, metric, f"Team strength by {noun}", total, min_team_years)
    values = {k: round(mean(v)) for k, v in cells.items() if len(v) >= min_team_years}
    last = decades[-1]
    latest = sorted(((values[(g, last)], g) for g in groups if (g, last) in values), key=lambda x: (-x[0], x[1]))
    if not latest:
        return _insufficient(ctx, metric, f"Team strength by {noun}", total, min_team_years)
    table_rows: list[list[Cell]] = [
        [g, *[values.get((g, d)) for d in decades], len(teams_in.get((g, last), ()))] for g in groups]
    facts = [Fact(id=f"q3.{metric}.{last}s.{slug(g)}", label=f"Mean rating, {g}, {_decade_label(last)}",
                  value=v, unit="points") for v, g in latest]
    facts.append(Fact(id=f"q3.{metric}.unmapped_pct", label="Team-years without a WDI mapping (excluded)",
                      value=pct(unmapped, total), unit="%", decimals=1))
    top, bottom = latest[0], latest[-1]
    top_n, bottom_n = len(teams_in[(top[1], last)]), len(teams_in[(bottom[1], last)])
    facts += [Fact(id=f"q3.{metric}.{last}s.{slug(top[1])}.teams", label=f"Teams, {top[1]}, {_decade_label(last)}",
                   value=top_n, unit="teams"),
              Fact(id=f"q3.{metric}.{last}s.{slug(bottom[1])}.teams",
                   label=f"Teams, {bottom[1]}, {_decade_label(last)}", value=bottom_n, unit="teams")]
    return ToolResult(
        tool="trends", question=3, view=metric, params={"metric": metric},
        title=f"Team strength by {noun} since {DEVELOPMENT_FROM} (development lens)",
        headline=(f"In the {_decade_label(last)}, the {top_n} teams from {who(top[1])} averaged {top[0]} rating "
                  f"points and the {bottom_n} teams from {who(bottom[1])} averaged {bottom[0]}."),
        facts=facts[-12:],
        table=Table(columns=[noun, *[_decade_label(d) for d in decades],
                             f"Teams, {_decade_label(last)}"], rows=table_rows),
        chart=Chart(kind="line", title=f"Mean year-end rating by {noun}", x=[_decade_label(d) for d in decades],
                    series=[Series(name=g, values=[values.get((g, d)) for d in decades]) for g in groups],
                    x_label="Decade", y_label="Mean rating",
                    summary=(f"Line chart of mean year-end ratings per {noun} by decade since {DEVELOPMENT_FROM}; in "
                             f"the {_decade_label(last)} the highest is {top[1]} at {top[0]} and the lowest "
                             f"{bottom[1]} at {bottom[0]}.")),
        method=(f"Year-end ratings (method ratings-v1) of teams mapped to a {noun}, averaged per decade from "
                f"{DEVELOPMENT_FROM}; groups need {min_team_years} team-years in a decade."),
        coverage=[f"{pct(unmapped, total)}% of team-years since {DEVELOPMENT_FROM} have no WDI mapping and are "
                  "excluded (historical teams, territories, non-FIFA teams)."],
        caveats=["Development groupings are context, not explanations: they describe where teams are, not why they "
                 "are strong or weak.",
                 "Income groups are the World Bank's current classification applied to every decade.",
                 "Ratings are relative within the pool of teams, and groups differ in how many teams they contain."],
        cannot_tell="Whether development causes football strength, or the reverse.",
        method_version=f"q3-{metric}-v1", dataset_version=ctx.dataset_version,
        row_counts={"team_years": total - unmapped, "unmapped_team_years": unmapped},
    )


def strength_by_region(ctx: ToolContext, min_team_years: int = MIN_GROUP_TEAM_YEARS) -> ToolResult:
    return _strength_by_group(ctx, "region", min_team_years)


def strength_by_income(ctx: ToolContext, min_team_years: int = MIN_GROUP_TEAM_YEARS) -> ToolResult:
    return _strength_by_group(ctx, "income_group", min_team_years)


def run(ctx: ToolContext, params: Params) -> ToolResult:
    views = {"home_advantage": home_advantage, "goals_per_match": goals_per_match, "strength_spread": strength_spread,
             "goal_timing": goal_timing, "strength_by_region": strength_by_region,
             "strength_by_income": strength_by_income}
    return views[params.metric](ctx)
