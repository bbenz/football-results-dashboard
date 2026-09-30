"""ingest: verify the raw files, build the curated store, publish a version.

The curated version ID is derived from the input checksums, this module's
version, the reference data, and the development-indicator shortlist, so
re-running ingest on the same inputs reproduces the same version and the same
file checksums on any platform. Change INGEST_VERSION whenever you change how
ingest builds its tables, so the new output gets a new version. Files are
written first; the manifest last; the ACTIVE pointer after that.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..data.contract import DATASETS, FILES, WDI_INDICATORS, FileSpec
from ..data.verify import VerifyReport, verify
from ..reference import Reference, get_reference
from .storage import MANIFEST, CuratedStorage, RawSource

INGEST_VERSION = "ingest-v1"
OUTPUTS = (
    "matches.parquet",
    "goals.parquet",
    "teams.parquet",
    "economies.parquet",
    "indicators.parquet",
    "former_names.parquet",
    "data_quality.json",
)


class IngestError(RuntimeError):
    pass


@dataclass
class IngestResult:
    version: str
    reused: bool
    storage: str
    manifest: dict[str, Any]
    data_quality: dict[str, Any]
    duration_s: float


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def version_id(report: VerifyReport, reference: Reference) -> str:
    digest = hashlib.sha256(INGEST_VERSION.encode())
    for path in sorted(report.files):
        digest.update(f"{path}={report.files[path].sha256}\n".encode())
    digest.update(reference.digest.encode())
    digest.update(json.dumps(sorted(WDI_INDICATORS)).encode())
    return "cv-" + digest.hexdigest()[:12]


def _q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _load_reference_tables(con: Any, ref: Reference) -> None:
    con.execute("create table ref_tournament (tournament varchar, category varchar, k integer, "
                "competitive boolean, friendly_like boolean, major boolean)")
    rows = []
    for name, cat in sorted(ref.tournament_category.items()):
        c = ref.categories[cat]
        rows.append((name, cat, c.k, c.competitive, c.friendly_like, name in ref.major_tournaments))
    con.executemany("insert into ref_tournament values (?, ?, ?, ?, ?, ?)", rows)
    con.execute("create table ref_era (era varchar, start_year integer, end_year integer)")
    con.executemany("insert into ref_era values (?, ?, ?)", [(e.id, e.start, e.end) for e in ref.eras])
    con.execute("create table ref_alias (venue varchar, team varchar)")
    con.executemany("insert into ref_alias values (?, ?)", sorted(ref.venue_aliases.items()))
    con.execute("create table ref_crosswalk (team varchar, wdi varchar, mapping varchar, valid_from integer, "
                "reason varchar, note varchar)")
    con.executemany("insert into ref_crosswalk values (?, ?, ?, ?, ?, ?)", [
        (m.team, m.wdi, m.match, m.valid_from, m.reason, m.note) for m in sorted(ref.crosswalk.values(),
                                                                                  key=lambda m: m.team)])


def _build(con: Any, raw: Path, out: Path, ref: Reference, report: VerifyReport) -> dict[str, Any]:
    fs = (raw / "football_stats").as_posix()
    wd = (raw / "global_development_data").as_posix()
    con.execute("set threads = 1")
    con.execute("set preserve_insertion_order = true")
    _load_reference_tables(con, ref)

    con.execute(f"""
        create table raw_results as
        select row_number() over () as match_id, * from read_csv('{fs}/results.csv', header=true,
          columns={{'date': 'DATE', 'home_team': 'VARCHAR', 'away_team': 'VARCHAR', 'home_score': 'INTEGER',
                   'away_score': 'INTEGER', 'tournament': 'VARCHAR', 'city': 'VARCHAR', 'country': 'VARCHAR',
                   'neutral': 'BOOLEAN'}})""")
    con.execute(f"""
        create table raw_goals as select * from read_csv('{fs}/goalscorers.csv', header=true, nullstr='NA',
          columns={{'date': 'DATE', 'home_team': 'VARCHAR', 'away_team': 'VARCHAR', 'team': 'VARCHAR',
                   'scorer': 'VARCHAR', 'minute': 'INTEGER', 'own_goal': 'BOOLEAN', 'penalty': 'BOOLEAN'}})""")
    con.execute(f"""
        create table raw_shootouts as select * from read_csv('{fs}/shootouts.csv', header=true, nullstr='NA',
          columns={{'date': 'DATE', 'home_team': 'VARCHAR', 'away_team': 'VARCHAR', 'winner': 'VARCHAR',
                   'first_shooter': 'VARCHAR'}})""")
    con.execute(f"""
        create table former_names as select * from read_csv('{fs}/former_names.csv', header=true,
          columns={{'current': 'VARCHAR', 'former': 'VARCHAR', 'start_date': 'DATE', 'end_date': 'DATE'}})""")

    unclassified = [r[0] for r in con.execute(
        "select distinct tournament from raw_results where tournament not in (select tournament from ref_tournament)"
        " order by 1").fetchall()]
    if unclassified:
        raise IngestError("tournaments not classified in reference/tournaments.yaml: " + ", ".join(unclassified))

    # Match keys that are not unique cannot be joined to goals or shootouts safely.
    con.execute("""create table dup_keys as select date, home_team, away_team from raw_results
                   group by all having count(*) > 1""")
    con.execute("""
        create table goal_counts as
        select g.date, g.home_team, g.away_team, count(*) as n
        from raw_goals g anti join dup_keys d on d.date = g.date and d.home_team = g.home_team
          and d.away_team = g.away_team
        group by all""")
    con.execute("""
        create table venue_map as
        select r.match_id,
          coalesce(a.team, fd.current, fa.current, r.country) as venue_team,
          a.team is not null as via_alias,
          a.team is null and coalesce(fd.current, fa.current) is not null as via_former
        from raw_results r
        left join ref_alias a on a.venue = r.country
        left join former_names fd on fd.former = r.country and r.date between fd.start_date and fd.end_date
        left join (select former, arg_min(current, start_date) as current from former_names group by former) fa
          on fa.former = r.country
        qualify row_number() over (partition by r.match_id order by fd.start_date nulls last) = 1""")
    con.execute("""
        create table matches as
        select r.match_id, r.date, year(r.date)::smallint as year, (year(r.date) // 10 * 10)::smallint as decade,
          r.home_team, r.away_team, r.home_score::smallint as home_score, r.away_score::smallint as away_score,
          (r.home_score + r.away_score)::smallint as goals,
          r.tournament, t.category, t.k::tinyint as k, t.competitive, t.friendly_like, t.major,
          r.city, r.country as venue_country, v.venue_team, v.via_alias, v.via_former,
          r.neutral,
          v.venue_team in (r.home_team, r.away_team) as venue_is_participant,
          r.neutral and v.venue_team not in (r.home_team, r.away_team) as third_party,
          e.era,
          s.winner as shootout_winner,
          coalesce(gc.n = r.home_score + r.away_score, false) as has_timeline
        from raw_results r
        join venue_map v using (match_id)
        join ref_tournament t on t.tournament = r.tournament
        join ref_era e on year(r.date) between e.start_year and e.end_year
        left join goal_counts gc on gc.date = r.date and gc.home_team = r.home_team and gc.away_team = r.away_team
        left join (select s.* from raw_shootouts s anti join dup_keys d
                   on d.date = s.date and d.home_team = s.home_team and d.away_team = s.away_team) s
          on s.date = r.date and s.home_team = r.home_team and s.away_team = r.away_team
        order by r.match_id""")
    con.execute("""
        create table goals as
        select m.match_id, g.team, g.minute::smallint as minute, g.own_goal, g.penalty
        from (select g.* from raw_goals g anti join dup_keys d
              on d.date = g.date and d.home_team = g.home_team and d.away_team = g.away_team) g
        join matches m on m.date = g.date and m.home_team = g.home_team and m.away_team = g.away_team
        order by m.match_id, g.minute nulls last, g.team""")

    con.execute(f"""
        create table economies as
        select "Country Code" as code, "Table Name" as name, "Region" as region, "Income Group" as income_group
        from read_csv('{wd}/WDICountry_Cleaned.csv', header=true, all_varchar=true)
        where coalesce("Region", '') <> '' order by code""")
    con.execute("""
        create table teams as
        with appearances as (
          select home_team as team, date from matches union all select away_team, date from matches)
        select a.team, min(a.date) as first_date, max(a.date) as last_date, count(*)::integer as matches,
          c.wdi as wdi_code, coalesce(c.mapping, 'unreviewed') as mapping, c.valid_from, c.reason, c.note,
          e.region, e.income_group
        from appearances a left join ref_crosswalk c on c.team = a.team left join economies e on e.code = c.wdi
        group by all order by a.team""")
    indicator_list = ", ".join(_q(code) for code in sorted(WDI_INDICATORS))
    con.execute(f"""
        create table indicators as
        with wide as (
          select * exclude ("Country Name", "Indicator Name")
          from read_csv('{wd}/WDICSV.csv', header=true, all_varchar=true)
          where "Indicator Code" in ({indicator_list}) and "Country Code" in (select code from economies))
        select "Country Code" as code, "Indicator Code" as indicator, year::smallint as year,
          value::double as value
        from (unpivot wide on columns(* exclude ("Country Code", "Indicator Code")) into name year value value)
        where value is not null and value <> ''
        order by code, indicator, year""")

    for table in ("matches", "goals", "teams", "economies", "indicators", "former_names"):
        order = {"former_names": "current, former"}.get(table, "all")
        con.execute(f"copy (select * from {table} order by {order}) to '{(out / (table + '.parquet')).as_posix()}' "
                    "(format parquet, compression zstd)")

    return _data_quality(con, report, ref)


def _pct(numerator: float, denominator: float) -> float:
    return round(100.0 * numerator / denominator, 1) if denominator else 0.0


def _data_quality(con: Any, report: VerifyReport, ref: Reference) -> dict[str, Any]:
    one = lambda sql: con.execute(sql).fetchone()  # noqa: E731
    all_rows = lambda sql: con.execute(sql).fetchall()  # noqa: E731

    n_matches, first, last, total_goals = one("select count(*), min(date), max(date), sum(goals) from matches")
    goal_rows = one("select count(*) from raw_goals")[0]
    scoring = one("select count(*) from matches where goals > 0")[0]
    timelines = one("select count(*) from matches where has_timeline")[0]
    with_rows = one("select count(*) from goal_counts")[0]
    orphan_goals = one("""select count(*) from raw_goals g where not exists (select 1 from raw_results r
                          where r.date = g.date and r.home_team = g.home_team and r.away_team = g.away_team)""")[0]
    since_1990 = one("select count(*) filter (where has_timeline), count(*) from matches "
                     "where goals > 0 and year >= 1990")
    per_decade = [
        {"decade": int(d), "scoring_matches": int(s), "with_timeline": int(t), "coverage_pct": _pct(t, s)}
        for d, s, t in all_rows("select decade, count(*) filter (where goals > 0), "
                                "count(*) filter (where has_timeline and goals > 0) from matches group by 1 order by 1")
    ]
    shootouts = one("select count(*) from raw_shootouts")[0]
    shootouts_joined = one("select count(*) from matches where shootout_winner is not null")[0]
    shootouts_nondraw = one("select count(*) from matches where shootout_winner is not null "
                            "and home_score <> away_score")[0]
    dup_keys = one("select count(*) from dup_keys")[0]
    dup_matches = one("""select count(*) from raw_results r join dup_keys d on d.date = r.date
                         and d.home_team = r.home_team and d.away_team = r.away_team""")[0]
    venue = one("""select count(*) filter (where via_former), count(*) filter (where via_alias),
                   count(*) filter (where not neutral and venue_is_participant),
                   count(*) filter (where neutral and not venue_is_participant),
                   count(*) filter (where neutral and venue_is_participant),
                   count(*) filter (where not neutral and not venue_is_participant) from matches""")
    categories = {c: int(n) for c, n in all_rows("select category, count(*) from matches group by 1 order by 1")}

    both, either, both_1990, n_1990 = one("""
        with m2 as (
          select m.year,
            coalesce(ch.wdi is not null and (ch.valid_from is null or m.year >= ch.valid_from), false) as h,
            coalesce(ca.wdi is not null and (ca.valid_from is null or m.year >= ca.valid_from), false) as a
          from matches m left join ref_crosswalk ch on ch.team = m.home_team
          left join ref_crosswalk ca on ca.team = m.away_team)
        select count(*) filter (where h and a), count(*) filter (where h or a),
          count(*) filter (where h and a and year >= 1990), count(*) filter (where year >= 1990) from m2""")
    by_mapping = {k: int(v) for k, v in all_rows("select mapping, count(*) from teams group by 1 order by 1")}
    by_reason = {k: int(v) for k, v in all_rows("select reason, count(*) from teams where mapping = 'none' "
                                                 "group by 1 order by 1")}
    unreviewed = [r[0] for r in all_rows("select team from teams where mapping = 'unreviewed' order by 1")]
    largest_unmapped = [{"team": t, "matches": int(n)} for t, n in all_rows(
        "select team, matches from teams where wdi_code is null order by matches desc, team limit 10")]
    soviet_era = one("""select count(*) from matches m join ref_crosswalk c on c.team in (m.home_team, m.away_team)
                        where c.valid_from is not null and m.year < c.valid_from""")[0]
    wdi_entities = one("select count(distinct \"Country Code\") from read_csv('" +
                       (Path(report.data_dir) / "global_development_data/WDICSV.csv").as_posix() +
                       "', header=true, all_varchar=true)")[0]
    economies = one("select count(*) from economies")[0]
    indicator_rows = one("select count(*), min(year), max(year) from indicators")

    return {
        "dataset_versions": report.dataset_versions(),
        "files": {p: {"rows": f.rows, "bytes": f.bytes, "sha256": f.sha256, "matches_verified": f.matches_verified}
                  for p, f in sorted(report.files.items())},
        "warnings": [f"{c.file}: {c.detail}" for c in report.warnings],
        "matches": {"rows": int(n_matches), "first_date": str(first), "last_date": str(last),
                    "teams": one("select count(*) from teams")[0],
                    "tournaments": one("select count(distinct tournament) from matches")[0],
                    "neutral": one("select count(*) from matches where neutral")[0],
                    "goals": int(total_goals), "by_category": categories},
        "goalscorers": {"rows": int(goal_rows), "share_of_goals_pct": _pct(goal_rows, total_goals),
                        "matches_with_rows": int(with_rows), "complete_timelines": int(timelines),
                        "coverage_of_scoring_matches_pct": _pct(timelines, scoring),
                        "coverage_since_1990_pct": _pct(since_1990[0], since_1990[1]),
                        "minute_missing": one("select count(*) from raw_goals where minute is null")[0],
                        "rows_without_match": int(orphan_goals), "per_decade": per_decade,
                        "scorer_names": "not stored: the questions need goal counts, timing, and type only"},
        "shootouts": {"rows": int(shootouts), "joined": int(shootouts_joined),
                      "excluded_without_match": int(shootouts - shootouts_joined),
                      "after_non_drawn_match": int(shootouts_nondraw)},
        "duplicate_match_keys": {"keys": int(dup_keys), "matches": int(dup_matches),
                                 "handling": "kept as separate matches; not joined to goals or shootouts"},
        "venues": {"reconciled_via_former_names": int(venue[0]), "reconciled_via_aliases": int(venue[1]),
                   "home_matches_agreeing": int(venue[2]), "third_party_hosted": int(venue[3]),
                   "neutral_flag_but_venue_is_participant": int(venue[4]),
                   "home_flag_but_venue_is_neither_team": int(venue[5]),
                   "rule": "third-party hosted = neutral flag AND reconciled venue is neither team"},
        "crosswalk": {"teams": int(one("select count(*) from teams")[0]), "by_mapping": by_mapping,
                      "unmapped_by_reason": by_reason, "unreviewed_teams": unreviewed,
                      "both_teams_mapped_pct": _pct(both, n_matches), "either_team_mapped_pct": _pct(either, n_matches),
                      "both_teams_mapped_since_1990_pct": _pct(both_1990, n_1990),
                      "matches_before_mapping_start": int(soviet_era),
                      "largest_unmapped": largest_unmapped},
        "wdi": {"entities_in_file": int(wdi_entities), "economies": int(economies),
                "excluded_aggregates_or_unclassified": int(wdi_entities - economies),
                "indicators": sorted(WDI_INDICATORS), "rows_long_format": int(indicator_rows[0]),
                "years": [int(indicator_rows[1]), int(indicator_rows[2])],
                "income_group_note": "current World Bank classification only; no history"},
        "reference": {"tournament_categories": len(ref.categories), "eras": [e.label for e in ref.eras],
                      "digest": ref.digest[:16]},
    }


def run(raw: RawSource, storage: CuratedStorage, platform: str, work_dir: Path | None = None,
        files: tuple[FileSpec, ...] = FILES, reference: Reference | None = None) -> IngestResult:
    import duckdb

    started = time.perf_counter()
    started_at = datetime.now(UTC)
    ref = reference or get_reference()
    scratch = Path(tempfile.mkdtemp(prefix="ingest-", dir=work_dir))
    try:
        raw_dir = raw.materialize([spec.path for spec in files], scratch / "raw")
        report = verify(raw_dir, files)
        if not report.ok:
            failures = "; ".join(f"{c.file} {c.name}: {c.detail}" for c in report.checks if c.status == "fail")
            raise IngestError("verify-data failed: " + failures)
        version = version_id(report, ref)
        out = scratch / "out"
        out.mkdir()
        con = duckdb.connect()
        try:
            dq = _build(con, raw_dir, out, ref, report)
        finally:
            con.close()
        dq["version"] = version
        (out / "data_quality.json").write_text(json.dumps(dq, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
        outputs = {name: {"sha256": _sha256(out / name), "bytes": (out / name).stat().st_size} for name in OUTPUTS}
        manifest = {
            "version": version,
            "ingest_version": INGEST_VERSION,
            "reference_digest": ref.digest,
            "inputs": {p: f.sha256 for p, f in sorted(report.files.items())},
            "datasets": {k: {"kaggle": v.kaggle_slug, "verified_version": v.verified_version}
                         for k, v in DATASETS.items()},
            "dataset_label": dataset_label(report),
            "outputs": outputs,
        }
        (out / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8", newline="\n")

        existing = storage.read_manifest(version)
        reused = existing is not None
        if reused and existing is not None and existing.get("outputs") != outputs:
            raise IngestError(f"version {version} already exists with different checksums; ingest is not "
                              "deterministic on this platform, so the active version was left unchanged")
        if not reused:
            storage.publish(version, out)
        storage.write_pointer({"version": version, "dataset_label": manifest["dataset_label"]})
        duration = time.perf_counter() - started
        storage.write_run(
            f"{started_at:%Y%m%dT%H%M%SZ}-{platform.lower()}",
            {"version": version, "platform": platform, "started_at": started_at.isoformat(),
             "duration_s": round(duration, 2), "reused_existing_version": reused, "outputs": outputs},
        )
        return IngestResult(version, reused, storage.description, manifest, dq, duration)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def dataset_label(report: VerifyReport) -> str:
    parts = []
    for key, info in report.dataset_versions().items():
        name = "results" if key == "football" else "WDI"
        parts.append(f"{name} {info['version_label']}")
    return ", ".join(parts)
