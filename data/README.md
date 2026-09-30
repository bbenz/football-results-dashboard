# Data

This repository contains **no data**. You download two public Kaggle datasets yourself and place them here. Everything in this folder except this file and `data sources.md` is ignored by git, and a guard (`demo/scripts/check_no_data.py`) fails if any data file is ever committed.

## What you need

- A free Kaggle account. Kaggle's terms require one to download datasets.
- About 210 MB of free disk space. The World Development Indicators file alone is about 200 MB.

## Option 1 (baseline): download in your browser

1. Sign in at [kaggle.com](https://www.kaggle.com).
2. Open [International football results from 1872 to 2026](https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017), select **Download**, and extract `results.csv`, `goalscorers.csv`, `shootouts.csv`, and `former_names.csv` into `data/football_stats/`. The archive is about 1.2 MB.
3. Open [Global Development Data (1960–2025)](https://www.kaggle.com/datasets/yogeshm01/global-development-data-19602025), select **Download**, and extract `WDICSV.csv`, `WDICountry_Cleaned.csv`, `WDISeries_Cleaned.csv`, and `Data_Dictionary.csv` into `data/global_development_data/`. The archive is about 69 MB.

The second dataset's description on Kaggle mentions `WDIData.csv`, `WDICountry.csv`, and `WDISeries.csv`. The download actually contains the four files listed above (checked 2026-09-29), and this demo expects those.

## Option 2 (optional): the download helper

From the repository root, after `demo bootstrap` (see [docs/SETUP.md](../docs/SETUP.md) for the `demo` command):

```powershell
./demo/scripts/demo.ps1 download
```

```bash
./demo/scripts/demo.sh download
```

The helper calls Kaggle's dataset download API, asks for the exact version this demo was verified against, and extracts only the eight expected files into the layout below. Add `--latest` to take Kaggle's current version instead.

- Authentication: create an API token in your Kaggle account settings and set it as the `KAGGLE_API_TOKEN` environment variable, or save it in `~/.kaggle/access_token`. The helper sends it and never prints it. Never commit a token.
- Tested on 2026-09-30: the football dataset came back byte-identical to the verified files. At that time Kaggle also served the current versions without a token and answered HTTP 404 for older versions without one; that behavior may change.

## Option 3 (optional): the Kaggle CLI

```bash
pip install kaggle
kaggle auth login
kaggle datasets download martj42/international-football-results-from-1872-to-2017 -p data/football_stats --unzip
kaggle datasets download yogeshm01/global-development-data-19602025 -p data/global_development_data --unzip
```

The Kaggle CLI (2.2.4, Python 3.11 or later) also accepts `KAGGLE_API_TOKEN` or `~/.kaggle/access_token`; `~/.kaggle/kaggle.json` is its legacy format. It downloads the current version and does not document a way to request an older one. These commands follow Kaggle's documentation as checked on 2026-09-29 and were not run for this repository.

## Expected layout

```text
data/
  README.md
  data sources.md
  football_stats/
    results.csv
    goalscorers.csv
    shootouts.csv
    former_names.csv
  global_development_data/
    WDICSV.csv
    WDICountry_Cleaned.csv
    WDISeries_Cleaned.csv
    Data_Dictionary.csv
```

To keep the data somewhere else, for example when you work in a git worktree, set `FOOTBALL_DATA_DIR` in `.env` to that folder instead of copying the files.

## Verify

```powershell
./demo/scripts/demo.ps1 verify
```

```bash
./demo/scripts/demo.sh verify
```

With the verified versions, the last line reads `verify-data PASSED: 0 failure(s), 0 warning(s).`

- **Failures** mean the files don't match the schema this demo needs: a missing file or column, text that isn't UTF-8, a value that doesn't parse, or a row count or date outside the expected range. Each message points back here.
- **Warnings** mean checksum drift: your copy is a different (usually newer) Kaggle version than the one verified below. Everything still runs; counts and results will differ.

## Versions this demo was verified against

| Dataset | Kaggle version | Updated | License |
| --- | --- | --- | --- |
| International football results from 1872 to 2026, by Mart Jürisoo | 137 | 2026-08-26 | CC0: Public Domain |
| Global Development Data (1960–2025), by Yogesh Mishra, from the World Bank's World Development Indicators | 1 | 2026-07-14 | CC BY 4.0 |

| File | SHA-256 |
| --- | --- |
| `football_stats/results.csv` | `df35268f8fc341ff7fb93d448b4e40356676ac35300a6b4461fd199a99ac1514` |
| `football_stats/goalscorers.csv` | `38cbc8007fb4aef7dd9f57e354623dca2abaf03a859530565ccf368e86a9f614` |
| `football_stats/shootouts.csv` | `2acdc95fdad14f5f17200150a1a4a5fa6c2ccf57d31c8b4f61a2c7d9c0493113` |
| `football_stats/former_names.csv` | `2d57f59a3ac13b24c2fcf208ced5a38710529d122da38929838d0980b002677e` |
| `global_development_data/WDICSV.csv` | `4d9b205c8441052eeec655027a1eea08145587eaa889239844657f914799631b` |
| `global_development_data/WDICountry_Cleaned.csv` | `672fd88be2c9a6bf37d3b96d7881b3f2b85877271c3f6f68ea3c4fe85f3af887` |
| `global_development_data/WDISeries_Cleaned.csv` | `b4a7f4800e6ca6591c6f6b2a280de2f1992d56989b1929d8c2699448bda1490f` |
| `global_development_data/Data_Dictionary.csv` | `facbefa79b8b4dfe4a8e282d1ba3691cb374a38d6da555a586037e377e5dea5c` |

## If you have a newer version

The football dataset is updated often. With a newer version:

- `verify` warns for each file whose checksum differs, and ingest still runs.
- Match counts, dates, and results change; the methods in [docs/METHODS.md](../docs/METHODS.md) still apply.
- If the new version adds a tournament name, ingest stops and names it. Add it to `demo/src/football_insights/reference/tournaments.yaml` under the right category.
- New team names appear as "unreviewed" on the app's Data page. Add them to `demo/src/football_insights/reference/crosswalk.yaml` to use them with development data; until then they are counted as unmapped, never dropped.

## Licenses and attribution

- **International football results from 1872 to 2026** by Mart Jürisoo, on Kaggle, is dedicated to the public domain under CC0. It is credited here as a courtesy.
- **Global Development Data (1960–2025)** by Yogesh Mishra, on Kaggle, is derived from the World Bank's [World Development Indicators](https://datacatalog.worldbank.org/public-licenses) and licensed CC BY 4.0. This app reshapes the data from wide to long format and filters it to three indicators (population, GDP per capita in constant 2015 US dollars, and urban population share) for economies only.
