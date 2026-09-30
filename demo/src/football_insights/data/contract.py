"""The data contract: the files, columns, types, and ranges this demo expects.

Schema drift (a missing file or column, an unparseable value, rows outside the
sanity range) fails verification. Checksum drift only warns: attendees may
download a newer dataset version than the one this demo was verified against.
"""

from __future__ import annotations

from dataclasses import dataclass, field

README_HINT = "See data/README.md for how to download the datasets and the expected layout."


@dataclass(frozen=True)
class Dataset:
    key: str
    title: str
    kaggle_slug: str
    verified_version: int
    verified_updated: str
    license: str
    folder: str


@dataclass(frozen=True)
class FileSpec:
    dataset: str
    path: str
    columns: tuple[str, ...]
    min_rows: int
    max_rows: int
    verified_sha256: str
    verified_rows: int
    # Column checks: name -> kind ("date", "int", "bool", "int_or_na", "number_or_empty", "text")
    kinds: dict[str, str] = field(default_factory=dict)
    # Columns present in the verified version that the app does not need; not warned about.
    known_unused: tuple[str, ...] = ()
    # For the match file: the first match must be on or before the first date, the last on or after the second.
    date_bounds: tuple[str, str] | None = None
    notes: str = ""


DATASETS: dict[str, Dataset] = {
    "football": Dataset(
        key="football",
        title="International football results from 1872 to 2026",
        kaggle_slug="martj42/international-football-results-from-1872-to-2017",
        verified_version=137,
        verified_updated="2026-08-26",
        license="CC0: Public Domain",
        folder="football_stats",
    ),
    "wdi": Dataset(
        key="wdi",
        title="Global Development Data (1960-2025), from the World Bank World Development Indicators",
        kaggle_slug="yogeshm01/global-development-data-19602025",
        verified_version=1,
        verified_updated="2026-07-14",
        license="CC BY 4.0",
        folder="global_development_data",
    ),
}

WDI_YEARS = tuple(str(year) for year in range(1960, 2026))

FILES: tuple[FileSpec, ...] = (
    FileSpec(
        dataset="football",
        path="football_stats/results.csv",
        columns=("date", "home_team", "away_team", "home_score", "away_score", "tournament", "city", "country",
                 "neutral"),
        min_rows=45_000, max_rows=90_000,
        verified_sha256="df35268f8fc341ff7fb93d448b4e40356676ac35300a6b4461fd199a99ac1514",
        verified_rows=49_547,
        kinds={"date": "date", "home_score": "int", "away_score": "int", "neutral": "bool",
               "home_team": "text", "away_team": "text", "tournament": "text"},
        date_bounds=("1873-12-31", "2020-01-01"),
    ),
    FileSpec(
        dataset="football",
        path="football_stats/goalscorers.csv",
        columns=("date", "home_team", "away_team", "team", "scorer", "minute", "own_goal", "penalty"),
        min_rows=40_000, max_rows=100_000,
        verified_sha256="38cbc8007fb4aef7dd9f57e354623dca2abaf03a859530565ccf368e86a9f614",
        verified_rows=47_914,
        kinds={"date": "date", "minute": "int_or_na", "own_goal": "bool", "penalty": "bool", "team": "text"},
    ),
    FileSpec(
        dataset="football",
        path="football_stats/shootouts.csv",
        columns=("date", "home_team", "away_team", "winner", "first_shooter"),
        min_rows=500, max_rows=2_000,
        verified_sha256="2acdc95fdad14f5f17200150a1a4a5fa6c2ccf57d31c8b4f61a2c7d9c0493113",
        verified_rows=683,
        kinds={"date": "date", "winner": "text"},
    ),
    FileSpec(
        dataset="football",
        path="football_stats/former_names.csv",
        columns=("current", "former", "start_date", "end_date"),
        min_rows=20, max_rows=200,
        verified_sha256="2d57f59a3ac13b24c2fcf208ced5a38710529d122da38929838d0980b002677e",
        verified_rows=36,
        kinds={"start_date": "date", "end_date": "date", "current": "text", "former": "text"},
    ),
    FileSpec(
        dataset="wdi",
        path="global_development_data/WDICSV.csv",
        columns=("Country Name", "Country Code", "Indicator Name", "Indicator Code", *WDI_YEARS),
        min_rows=300_000, max_rows=700_000,
        verified_sha256="4d9b205c8441052eeec655027a1eea08145587eaa889239844657f914799631b",
        verified_rows=398_468,
        kinds={"Country Code": "text", "Indicator Code": "text", "1960": "number_or_empty",
               "2000": "number_or_empty", "2024": "number_or_empty"},
    ),
    FileSpec(
        dataset="wdi",
        path="global_development_data/WDICountry_Cleaned.csv",
        columns=("Country Code", "Short Name", "Table Name", "Long Name", "Region", "Income Group"),
        min_rows=200, max_rows=400,
        verified_sha256="672fd88be2c9a6bf37d3b96d7881b3f2b85877271c3f6f68ea3c4fe85f3af887",
        verified_rows=265,
        kinds={"Country Code": "text", "Table Name": "text"},
        known_unused=("2-alpha code", "Currency Unit", "Special Notes", "WB-2 code", "National accounts base year",
                      "National accounts reference year", "SNA price valuation", "Lending category", "Other groups",
                      "System of National Accounts", "Balance of Payments Manual in use",
                      "External debt Reporting status", "System of trade", "Government Accounting concept",
                      "IMF data dissemination standard", "Latest population census", "Latest household survey",
                      "Source of most recent Income and expenditure data", "Vital registration complete",
                      "Latest agricultural census", "Latest industrial data", "Latest trade data"),
    ),
    FileSpec(
        dataset="wdi",
        path="global_development_data/WDISeries_Cleaned.csv",
        columns=("Series Code", "Topic", "Indicator Name"),
        min_rows=1_000, max_rows=3_000,
        verified_sha256="b4a7f4800e6ca6591c6f6b2a280de2f1992d56989b1929d8c2699448bda1490f",
        verified_rows=1_498,
        kinds={"Series Code": "text"},
        known_unused=("Long definition", "Unit of measure", "Periodicity", "Other notes", "Aggregation method",
                      "Limitations and exceptions", "Source", "Statistical concept and methodology",
                      "Development relevance", "License Type"),
    ),
    FileSpec(
        dataset="wdi",
        path="global_development_data/Data_Dictionary.csv",
        columns=("Column", "Dtype", "Description"),
        min_rows=10, max_rows=200,
        verified_sha256="facbefa79b8b4dfe4a8e282d1ba3691cb374a38d6da555a586037e377e5dea5c",
        verified_rows=45,
        notes=("Also describes the author's long-format working table: its Year, Value, and YoY_Growth rows "
               "match no shipped file and are ignored."),
    ),
)

# The WDI indicators the app uses (names and codes only; values stay in the data).
WDI_INDICATORS: dict[str, str] = {
    "SP.POP.TOTL": "Population, total",
    "NY.GDP.PCAP.KD": "GDP per capita (constant 2015 US$)",
    "SP.URB.TOTL.IN.ZS": "Urban population (% of total population)",
}
