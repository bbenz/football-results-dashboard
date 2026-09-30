"""Build small in-memory curated stores for analytics tests, without running ingest.

Tables mirror the curated Parquet schemas exactly. Match rows derive their
category, K, era, and flags from the real reference data, so a test states only
what matters to it: date, teams, score, tournament, and venue.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import duckdb

from football_insights.reference import Reference, get_reference
from football_insights.store import CuratedStore

SCHEMAS = {
    "matches": ("match_id BIGINT, date DATE, year SMALLINT, decade SMALLINT, home_team VARCHAR, away_team VARCHAR, "
                "home_score SMALLINT, away_score SMALLINT, goals SMALLINT, tournament VARCHAR, category VARCHAR, "
                "k TINYINT, competitive BOOLEAN, friendly_like BOOLEAN, major BOOLEAN, city VARCHAR, "
                "venue_country VARCHAR, venue_team VARCHAR, via_alias BOOLEAN, via_former BOOLEAN, neutral BOOLEAN, "
                "venue_is_participant BOOLEAN, third_party BOOLEAN, era VARCHAR, shootout_winner VARCHAR, "
                "has_timeline BOOLEAN"),
    "goals": "match_id BIGINT, team VARCHAR, minute SMALLINT, own_goal BOOLEAN, penalty BOOLEAN",
    "teams": ("team VARCHAR, first_date DATE, last_date DATE, matches INTEGER, wdi_code VARCHAR, mapping VARCHAR, "
              "valid_from INTEGER, reason VARCHAR, note VARCHAR, region VARCHAR, income_group VARCHAR"),
    "economies": "code VARCHAR, name VARCHAR, region VARCHAR, income_group VARCHAR",
    "indicators": "code VARCHAR, indicator VARCHAR, year SMALLINT, value DOUBLE",
    "former_names": "current VARCHAR, former VARCHAR, start_date DATE, end_date DATE",
}


@dataclass
class M:
    """One synthetic match. venue defaults to the home team's country; neutral defaults to False."""

    date: str
    home: str
    away: str
    home_score: int
    away_score: int
    tournament: str = "Friendly"
    venue: str | None = None
    neutral: bool = False
    city: str = "Synthetic City"
    shootout_winner: str | None = None


@dataclass
class Economy:
    code: str
    region: str
    income_group: str
    mapping: str = "exact"
    valid_from: int | None = None
    indicators: dict[tuple[str, int], float] = field(default_factory=dict)


def make_store(matches: list[M], goals: list[tuple[int, str, int | None, bool, bool]] | None = None,
               economies: dict[str, Economy] | None = None, reference: Reference | None = None,
               version: str = "cv-test") -> CuratedStore:
    """matches in date order; goals as (match_id, team, minute, own_goal, penalty) with 1-based match_id;
    economies maps team name -> Economy (teams not listed are unmapped)."""
    ref = reference or get_reference()
    economies = economies or {}
    con = duckdb.connect(":memory:")
    for table, schema in SCHEMAS.items():
        con.execute(f"create table {table} ({schema})")
    goal_counts: dict[int, int] = {}
    for g in goals or []:
        goal_counts[g[0]] = goal_counts.get(g[0], 0) + 1
    rows: list[tuple[Any, ...]] = []
    for i, m in enumerate(matches, start=1):
        year = int(m.date[:4])
        cat = ref.category_of(m.tournament)
        venue = m.venue or m.home
        total = m.home_score + m.away_score
        participant = venue in (m.home, m.away)
        rows.append((i, m.date, year, year // 10 * 10, m.home, m.away, m.home_score, m.away_score, total,
                     m.tournament, cat.name, cat.k, cat.competitive, cat.friendly_like,
                     m.tournament in ref.major_tournaments, m.city, venue, venue, False, False, m.neutral,
                     participant, m.neutral and not participant, ref.era_for_year(year).id, m.shootout_winner,
                     goal_counts.get(i, -1) == total))
    con.executemany(f"insert into matches values ({', '.join('?' * 26)})", rows)
    if goals:
        con.executemany("insert into goals values (?, ?, ?, ?, ?)", goals)
    for team, eco in economies.items():
        con.execute("insert into economies values (?, ?, ?, ?)", [eco.code, team, eco.region, eco.income_group])
        for (indicator, year), value in eco.indicators.items():
            con.execute("insert into indicators values (?, ?, ?, ?)", [eco.code, indicator, year, value])
    con.execute("""
        insert into teams
        select t.team, min(t.date), max(t.date), count(*)::integer, null, 'unreviewed', null, null, null, null, null
        from (select home_team as team, date from matches union all select away_team, date from matches) t
        group by t.team""")
    for team, eco in economies.items():
        con.execute("update teams set wdi_code = ?, mapping = ?, valid_from = ?, region = ?, income_group = ? "
                    "where team = ?", [eco.code, eco.mapping, eco.valid_from, eco.region, eco.income_group, team])
    return CuratedStore(version=version, dataset_label="synthetic", manifest={}, data_quality={}, con=con,
                        source="in-memory test store", _lock=threading.Lock())
