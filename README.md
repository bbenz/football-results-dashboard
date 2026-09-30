# Football insights: 150 years of international football, on AKS and ACA

What can more than 150 years of international football tell us, and what does it take to ship those insights as an AI app on Azure Kubernetes Service (AKS) and on Azure Container Apps (ACA)?

This repository is the companion to the Microsoft Reactor livestream **Build AI-powered soccer insights apps with AKS and ACA**. (The title says soccer; the app and the data say football.) It answers seven questions about men's international football since 1872:

1. Who is the best team of all time?
2. Which teams dominated different eras of football?
3. What trends have there been in international football throughout the ages: home advantage, total goals scored, distribution of teams' strength?
4. Can we say anything about geopolitics from football fixtures: how has the number of countries changed, which teams like to play each other?
5. Which countries host the most matches in which they themselves are not participating?
6. How much, if at all, does hosting a major tournament help a country's chances in the tournament?
7. Which teams are the most active in playing friendlies and friendly tournaments, and does it help or hurt them?

## How it works

- **Deterministic analytics own every number.** Tested Python and SQL over a curated copy of the data compute every figure, chart, and table.
- **AI explains.** A Microsoft Foundry model reads a question, calls the analytics tools, and explains their results. A grounding check rejects any number the model writes that the tools didn't return.
- **One set of images, two platforms.** The same container images run locally with Docker Compose, on AKS, and on ACA.

```mermaid
flowchart LR
  viewer([Browser]) --> web[web<br/>public UI]
  web --> insights[insights<br/>internal: tools + agent]
  insights --> store[(Curated store<br/>DuckDB over Parquet)]
  insights -. keyless .-> foundry[Microsoft Foundry<br/>model deployments]
  ingest[ingest job] --> store
  data[(Your downloaded<br/>Kaggle data)] --> ingest
```

Methods, coverage, and caveats for every question: [docs/METHODS.md](docs/METHODS.md).

## Quick start

1. Install Python 3.12, Docker Desktop, and Git.
2. Clone this repository.
3. Download the data yourself: [data/README.md](data/README.md). The repository contains no data.
4. From the repository root:

   ```powershell
   ./demo/scripts/demo.ps1 bootstrap
   ./demo/scripts/demo.ps1 verify
   ./demo/scripts/demo.ps1 up
   ```

   In bash, use `./demo/scripts/demo.sh` with the same commands.

5. Open <http://127.0.0.1:8080>.

Details: [docs/SETUP.md](docs/SETUP.md).

## Data attribution

- **International football results from 1872 to 2026** by Mart Jürisoo, on [Kaggle](https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017), CC0: Public Domain.
- **Global Development Data (1960–2025)** by Yogesh Mishra, on [Kaggle](https://www.kaggle.com/datasets/yogeshm01/global-development-data-19602025), from the World Bank's World Development Indicators, CC BY 4.0. This app reshapes and filters the data.

The data is not redistributed here. See [data/README.md](data/README.md) for versions and licenses.
