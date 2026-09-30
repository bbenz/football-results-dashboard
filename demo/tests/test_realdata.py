"""Real-data checks. Skipped when the raw data has not been downloaded.

Expectations are computed through the deterministic layer or with independent
SQL at run time; no value from the real datasets is hardcoded here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import REAL_DATA, requires_real_data
from football_insights.data.verify import verify

pytestmark = [pytest.mark.realdata, requires_real_data]


def test_real_data_passes_verification() -> None:
    report = verify(REAL_DATA)
    assert report.ok, [c for c in report.checks if c.status == "fail"]


def test_real_ingest_is_deterministic_and_tools_match_independent_sql(tmp_path: Path) -> None:
    import duckdb

    from conftest import test_settings
    from football_insights.analytics import q3_trends
    from football_insights.analytics.context import ToolContext
    from football_insights.ingest.pipeline import run
    from football_insights.ingest.storage import LocalCuratedStorage, LocalRawSource
    from football_insights.store import load

    first = run(LocalRawSource(REAL_DATA), LocalCuratedStorage(tmp_path / "a"), platform="Test")
    second = run(LocalRawSource(REAL_DATA), LocalCuratedStorage(tmp_path / "b"), platform="Test")
    assert first.version == second.version
    assert first.manifest["outputs"] == second.manifest["outputs"]

    store = load(test_settings(curated_dir=tmp_path / "a"), cache_dir=tmp_path / "cache")
    result = q3_trends.home_advantage(ToolContext(store))
    last = result.table.rows[-1]
    decade = int(str(last[0])[:4])
    raw = (REAL_DATA / "football_stats" / "results.csv").as_posix()
    n, wins = duckdb.sql(
        f"select count(*), count(*) filter (where home_score > away_score) from read_csv('{raw}', header=true) "
        f"where not neutral and year(date) // 10 * 10 = {decade}").fetchone()
    assert last[1] == n
    assert last[2] == round(100 * wins / n, 1)
