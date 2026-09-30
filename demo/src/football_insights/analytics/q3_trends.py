"""Question 3: trends in international football throughout the ages."""

from __future__ import annotations

from typing import Literal

from ..schemas import Cell, Chart, Fact, Series, Table, ToolResult
from .context import ToolContext, pct
from .stats import wilson

MIN_DECADE_MATCHES = 100
Metric = Literal["home_advantage", "goals_per_match"]


def _decade_label(decade: int) -> str:
    return f"{decade}s"


def _insufficient(ctx: ToolContext, metric: str, title: str, matches: int, min_matches: int) -> ToolResult:
    return ToolResult(
        tool="trends", question=3, view=metric, params={"metric": metric}, title=title,
        headline=f"No decade has the minimum of {min_matches} matches in the loaded data, so no trend is shown.",
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


def run(ctx: ToolContext, metric: Metric) -> ToolResult:
    views = {"home_advantage": home_advantage, "goals_per_match": goals_per_match}
    return views[metric](ctx)
