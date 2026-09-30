"""The in-memory store builder mirrors the curated schema and derives flags from reference data."""

from __future__ import annotations

from football_insights.analytics import q3_trends
from football_insights.analytics.context import ToolContext
from helpers import Economy, M, make_store


def test_make_store_derives_categories_eras_and_venues() -> None:
    store = make_store(
        [M("1950-06-01", "Avalon", "Borealis", 2, 1, "FIFA World Cup", venue="Cascadia", neutral=True),
         M("1951-03-01", "Borealis", "Avalon", 0, 0)],
        goals=[(1, "Avalon", 10, False, False), (1, "Avalon", 50, False, True), (1, "Borealis", 70, True, False)],
        economies={"Avalon": Economy("XAV", "North Region", "High income", indicators={("SP.POP.TOTL", 2020): 5e6})},
    )
    first = store.query("select category, k, major, era, third_party, has_timeline from matches where match_id = 1")[0]
    assert first == ("world_cup", 60, True, "postwar", True, True)
    second = store.query("select friendly_like, third_party, has_timeline from matches where match_id = 2")[0]
    assert second == (True, False, False)
    assert store.query("select wdi_code, region from teams where team = 'Avalon'")[0] == ("XAV", "North Region")
    assert store.query("select mapping from teams where team = 'Borealis'")[0] == ("unreviewed",)
    assert store.query("select value from indicators")[0] == (5e6,)


def test_tools_run_on_a_built_store() -> None:
    store = make_store([M(f"19{50 + i}-01-01", "Avalon", "Borealis", i % 3, 1) for i in range(6)])
    result = q3_trends.home_advantage(ToolContext(store), min_matches=1)
    assert result.table is not None and result.table.rows[0][0] == "1950s"
