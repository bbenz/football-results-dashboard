# Hackathon guide

This repository is meant to be taken apart. This guide shows how to extend it without breaking its two promises: **deterministic, tested code owns every number**, and **no data enters the repository**. Start by running it locally ([SETUP.md](SETUP.md)), and read [ARCHITECTURE.md](ARCHITECTURE.md) for how the pieces fit.

## Add a question and its tool

Every insight follows one pattern: a typed, read-only tool computes the numbers; a card shows them; a test proves them; the agent can call the tool; the grounding check keeps the model honest. The livestream's GitHub Copilot moment adds one this way: **the biggest upsets of each era**, based on the existing rating model.

1. **Write the tool.** Add a module under `demo/src/football_insights/analytics/`, following `q2_eras.py`. A tool module defines:
   - `TOOL_NAME` and `DESCRIPTION`: the description is what the model reads when it chooses tools, so say what the tool answers and what its parameters mean.
   - `Params`: a pydantic model with `extra="forbid"`, using `Literal` types for choices, such as an era ID. The registry turns it into a strict JSON schema.
   - `CARD_ARGUMENTS`: the parameters the insight card uses.
   - `run(ctx, params) -> ToolResult`: deterministic Python and SQL over `ctx.store` (DuckDB) and `ctx.ratings()` (every match with its pre-match ratings and expected score). Return aggregates only: facts with evidence IDs such as `q8.early.top_upset_expected`, an optional small table and chart, the method, coverage, caveats, and what the data can't tell you.
2. **Register it.** In `analytics/registry.py`, add the module to `QUESTION_MODULES` and its question text to `QUESTIONS`.
3. **Describe its card.** In `cards.py`, add the card text: what is asked, the data and method, what the result looks like, and why it matters.
4. **Test it.** Add a test under `demo/tests/` that runs the tool on the synthetic fixtures (`demo/tests/fixtures/synthetic/`, fictional teams only) and checks values you worked out by hand. The contract test (`test_tool_contract.py`) then runs every parameter combination of your tool automatically. It checks the result shape and time budget, and that every number in its headline and chart summary passes the grounding validator.
5. **Document it.** Add a section to [METHODS.md](METHODS.md) with the definition, minimum sample, caveats, and what it can't tell you, and add at least three phrasings to `demo/src/football_insights/evaluation/cases.yaml`.
6. **Run it.** `demo test`, then `demo up` and ask a question that needs your tool.

A good tool is small, answers one question, states its sample size, and returns numbers the narrative can quote exactly.

## Add a development-indicator lens

The curated store holds three World Bank indicators for every economy from 1960: population (`SP.POP.TOTL`), GDP per capita in constant 2015 US dollars (`NY.GDP.PCAP.KD`), and urban population share (`SP.URB.TOTL.IN.ZS`). It also holds each economy's World Bank region and income group, and a reviewed crosswalk from football teams to economies.

- **Use what's there.** Join a team to its economy through the `teams` table (`teams.wdi_code`, with the crosswalk's mapping kind), then to `indicators` by code and year. Report crosswalk coverage for every view, and never drop unmapped teams silently. Shared mappings (the four UK teams share one economy) support region and income views only, not per-capita values.
- **Add an indicator.** Put its code and name in `WDI_INDICATORS` in `demo/src/football_insights/data/contract.py` and run `demo ingest`. The indicator list is part of the curated version's hash, so ingest publishes a new version instead of reusing the old one.
- **Frame it responsibly.** Development indicators are context, never explanations or rankings of worth. Describe patterns; don't claim that wealth or population causes results.

## Bring your own dataset

The same pattern works for other tabular data you're allowed to use:

1. **Keep it out of git.** Put the files under `data/<your_dataset>/`, which is ignored. The no-data guard (`demo guard`, and the pre-commit hook from `demo install-hook`) fails if a data file is ever staged.
2. **Write a schema contract.** Add a `FileSpec` for each file in `data/contract.py`: expected columns, types, encoding, row-count range, date range, and the SHA-256 you verified against. `demo verify` then fails on schema drift and warns on a newer version.
3. **Reconcile names with a reviewed crosswalk.** If your data names teams or countries differently, map them in YAML under `demo/src/football_insights/reference/`, like `crosswalk.yaml`: names and codes only, never values. Record why each unmapped name can't be mapped.
4. **Extend ingest.** Load the files in `ingest/pipeline.py`, add the tables to the curated store, and add their row counts and exclusions to the data-quality report. Change `INGEST_VERSION` whenever ingest's output changes.
5. **Test without the data.** Add a few synthetic rows with fictional names under `demo/tests/fixtures/synthetic/`, and write tests whose expected values you computed by hand.
6. **Document where to get it.** Add download steps, the expected layout, the version you used, and the license and attribution to `data/README.md`.

## Swap the model

- **Switch between the two deployments.** Which deployment serves answers is one setting, `AI_MODEL_DEPLOYMENT`. Locally, set it in `.env`. In Azure, run `demo switch-model gpt-6-sol`; it updates both platforms without rebuilding images.
- **Add another deployment.** Add it to `demo/infra/foundation.bicep` with a pinned version and `versionUpgradeOption: 'NoAutoUpgrade'`. Add its name to `AI_ALLOWED_DEPLOYMENTS` and its token prices to `demo/src/football_insights/agent/pricing.py`, then compare it with `demo eval` before switching.
- **What a replacement needs.** Tool calling with strict JSON schemas and structured output, through the Responses API. The grounding check doesn't change: whatever the model writes, a number it didn't get from a tool never reaches the page as fact.

## Deploy to your own subscription

1. Copy `.env.example` to `.env` and fill in your subscription, region, resource group, and resource names. Registry and storage names must be globally unique. Set `ALLOWED_CIDRS` to your public address, for example `203.0.113.7/32`: the web endpoints accept only these addresses.
2. Follow [DEPLOYMENT.md](DEPLOYMENT.md). You can deploy one platform or both:
   - **ACA only:** `azure-foundation`, `azure-platform`, `upload-data`, `build-push`, then `aca-deploy`.
   - **AKS only:** the same, with `aks-deploy` instead of `aca-deploy`.
3. When your address changes, `demo allow-ip` updates `ALLOWED_CIDRS` and both platforms' allow-lists.

[AKS-VS-ACA.md](AKS-VS-ACA.md) helps you choose.

## Cost and teardown

- [AKS-VS-ACA.md](AKS-VS-ACA.md#estimated-daily-cost-at-demo-scale) estimates the daily cost of each platform at demo scale. In short, ACA at one idle replica per service costs cents per day, while an AKS Automatic cluster costs dollars per day, even when idle, for its control plane and node.
- Model tokens are billed per answer. The app shows the tokens and estimated cost of every answer, and its limit of 6 questions per minute per client caps what any one visitor can spend.
- `azure-foundation` creates a monthly budget with alerts sent to `BUDGET_CONTACT_EMAIL`.
- When you're done, run `demo teardown -DryRun` (bash: `--dry-run`) to list everything in the resource group, then `demo teardown`, which deletes the whole resource group after you type its name.

## Ideas to build on

All of these use only the two datasets:

- **Giant killers:** which teams most often beat much stronger opponents, per era. This extends the upsets tool.
- **Penalty shootouts:** which teams win shootouts more often than their pre-match ratings suggest, and does kicking first help? `shootouts.csv` records the winner of every shootout and, for about two in five, which team kicked first.
- **Head-to-head explorer:** one pair of teams across 150 years, with their rating trajectories and every era's record.
- **Top scorers by era:** `goalscorers.csv` names each scorer for about a third of all goals. Add scorers to the curated store and state the coverage alongside every ranking.
- **Late drama:** how the share of goals after the 75th minute changed, split by competitive and friendly matches.
- **Tournament debutants:** how teams do in their first appearance at a major tournament, compared with rating-based expectations.
- **Calendar:** the months when friendlies and competitive matches are played, and how the international calendar changed.
- **Development context:** urban population share alongside team strength by region since 1960, described as context and not as cause.

Club football, women's internationals, tactics, and player tracking need other data. The pattern above still applies, but check the license of any dataset before you use it, and keep it out of your repository.
