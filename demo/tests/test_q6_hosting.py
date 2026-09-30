"""Synthetic tests for question 6 hosting effects."""

from __future__ import annotations

from football_insights.analytics import q6_hosting
from football_insights.analytics.context import ToolContext
from helpers import Economy, M, make_store


def test_edition_clustering_keeps_new_year_gap_and_splits_at_90_days() -> None:
    # Two matches one day apart across New Year stay in one edition; a gap of exactly ninety days starts a new one.
    store = make_store(
        [
            M("2020-12-31", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("2021-01-01", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Borealis", neutral=True),
            M("2021-04-01", "Avalon", "Cascadia", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("2021-04-02", "Borealis", "Dunmore", 0, 0, "FIFA World Cup", venue="Cascadia", neutral=True),
        ]
    )
    editions = q6_hosting._edition_cache(ToolContext(store))["editions"]
    world_cups = [e for e in editions if e.tournament == "FIFA World Cup"]

    assert [e.year for e in world_cups] == [2020, 2021]
    assert [len(e.matches) for e in world_cups] == [2, 2]


def test_host_detection_cohosts_and_exclusion_reasons() -> None:
    store = make_store(
        [
            M("2000-01-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("2000-01-02", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Borealis", neutral=True),
            M("2000-05-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Avalon", neutral=False),
            M("2000-05-02", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Borealis", neutral=False),
            M("2000-09-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("2001-01-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("2001-01-02", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Borealis", neutral=True),
            M("2001-01-03", "Elbaria", "Fenwick", 0, 0, "FIFA World Cup", venue="Cascadia", neutral=True),
            M("2001-01-04", "Glenmoor", "Harrowgate", 0, 0, "FIFA World Cup", venue="Dunmore", neutral=True),
        ]
    )
    editions = [
        e for e in q6_hosting._edition_cache(ToolContext(store))["editions"] if e.tournament == "FIFA World Cup"
    ]

    assert editions[0].hosts == {"Avalon", "Borealis"}
    assert editions[0].excluded_reasons == ()
    assert "low_neutral_share" in editions[1].excluded_reasons
    assert "too_few_teams" in editions[2].excluded_reasons
    assert "too_many_venues" in editions[3].excluded_reasons


def test_pairing_logic_uses_same_team_non_host_editions() -> None:
    # All matches are draws between equal-rated teams, so actual-minus-neutral-expected is hand-computed as zero.
    store = make_store(
        [
            M("2000-01-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("2000-01-02", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("2004-01-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Borealis", neutral=True),
            M("2004-01-02", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Borealis", neutral=True),
        ]
    )
    cache = q6_hosting._edition_cache(ToolContext(store))
    pairs = cache["pairs"]

    avalon = next(p for p in pairs if p.host == "Avalon")
    assert avalon.year == 2000
    assert avalon.non_host_performance == 0
    assert avalon.performance_diff == 0
    assert avalon.progression_diff == 0


def test_pooled_and_edition_results_have_stable_evidence_ids() -> None:
    store = make_store(
        [
            M("2000-01-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("2000-01-02", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("2004-01-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Borealis", neutral=True),
            M("2004-01-02", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Borealis", neutral=True),
        ]
    )
    ctx = ToolContext(store)
    params = q6_hosting.Params(view="pooled", tournament=None, year=None)
    pooled = q6_hosting.pooled(ctx, params, min_pooled=1)
    edition = q6_hosting.edition(ctx, q6_hosting.Params(view="edition", tournament="FIFA World Cup", year=2000))

    assert pooled.evidence_ids[:3] == [
        "q6.pooled.performance_diff",
        "q6.pooled.performance_low",
        "q6.pooled.performance_high",
    ]
    assert "Across 2 host editions" in pooled.headline
    assert edition.table is not None
    assert edition.table.rows[0][0] == "Avalon"


def test_gdp_split_uses_exact_or_alias_mapping_and_valid_from() -> None:
    store = make_store(
        [
            M("1960-01-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("1960-01-02", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Avalon", neutral=True),
            M("1964-01-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Borealis", neutral=True),
            M("1964-01-02", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Borealis", neutral=True),
            M("1968-01-01", "Avalon", "Borealis", 0, 0, "FIFA World Cup", venue="Cascadia", neutral=True),
            M("1968-01-02", "Cascadia", "Dunmore", 0, 0, "FIFA World Cup", venue="Cascadia", neutral=True),
        ],
        economies={
            "Avalon": Economy("XAV", "North", "High income", indicators={("NY.GDP.PCAP.KD", 1960): 1000}),
            "Borealis": Economy(
                "XBO",
                "North",
                "High income",
                indicators={("NY.GDP.PCAP.KD", 1964): 5000},
            ),
            "Cascadia": Economy(
                "XCA",
                "North",
                "High income",
                valid_from=1970,
                indicators={("NY.GDP.PCAP.KD", 1968): 9000},
            ),
        },
    )
    result = q6_hosting.gdp_split(ToolContext(store), q6_hosting.Params(view="gdp_split", tournament=None, year=None))

    assert result.facts[0].id == "q6.gdp_split.mapped"
    assert result.facts[0].value == 2
    assert result.facts[1].value == 33.3
