# Demo Generation Prompt v1: Build AI-Powered Soccer Insights Apps With AKS And ACA

Use this prompt with a coding agent to generate the complete demo project in the session's companion repository, prove it on Azure as a proof of concept (POC), and verify it before the event. This is a generation prompt, not the on-stage script; the on-stage script is a separate generated deliverable. Slides are out of scope here; they will be generated later from the finished repository.

## Non-Negotiables

Read this list first. Everything else in this document elaborates on it.

1. The session description and the seven inspiration questions, both inlined below and narrowed by the presenter's scope decisions, are the requirements document. Cover every promise; add nothing beyond it. The published abstract's Premier League-inspired scenarios are deliberately out of scope.
2. Ship running code, not a plan. Never claim a command, deployment, model call, or integration succeeded without evidence you actually produced.
3. Verify AKS, Azure Container Apps (ACA), Microsoft Foundry, SDK, Kaggle, and GitHub Copilot behavior against current documentation and real execution before designing around it. Do not assume a preview feature, SKU, or add-on is available or still recommended.
4. Deterministic, tested analytics own every number. The model selects tools and explains their results; it never computes, invents, or overrides a statistic. Every number in an AI answer must trace to a tool result, and an automated check must prove it.
5. The datasets never enter the public GitHub repository: not raw files, derived files, extracts, samples, notebook outputs, test snapshots, container images, CI artifacts, or git history. Attendees download the data themselves from the linked sources. Local copies and private Azure storage are fine for the proof of concept.
6. POC notes, working notes, evidence, and every other POC or presenter-private document live in the POC folder outside the repository, never in the repository, not even in an ignored folder. The repository holds only public, shareable material, and you refine its documentation throughout the POC so it matches verified behavior.
7. One set of container images runs unchanged locally, on AKS, and on ACA. Platform differences live only in deployment configuration, and the AKS-versus-ACA comparison rests on measured evidence, not marketing claims.
8. Use keyless access to Azure resources wherever supported. Never log, print, screenshot, or commit secrets, including Kaggle API tokens, keys, and connection strings.
9. The session is a 60-minute Microsoft Reactor livestream including introduction and Q&A, and the recording is permanent. Design for the time budget, and treat everything on screen as public.
10. Stop and report at each phase gate below. The presenter has approved an Azure POC in the resource group `bbenz-football-results-dashboard`, within the limits in Azure Proof Of Concept. Ask before anything outside that approval, including other resource groups, public access beyond the operator's IP address, deleting anything, exceeding the budget, and pushing or publishing the repository.
11. Resolve routine engineering choices yourself. Do not ask for permission to write code.

## Mission And Source Of Truth

You are a senior Python engineer, data analyst, Azure cloud-native architect for AKS and ACA, and technical demo author. Build a runnable, reproducible demonstration for Brian Benz's Microsoft Reactor livestream:

**Build AI-powered soccer insights apps with AKS and ACA**

The session is on October 14, 2026, from 9:00 to 10:00 AM Pacific Time (UTC-07:00), as a Microsoft Reactor livestream in English under the topic "AI Applications": https://developer.microsoft.com/en-us/reactor/events/27536/. The entire session is **60 minutes, including introduction and Q&A**.

The published description reads:

> Learn how to build and deploy AI-powered applications that analyze football match and player data using AKS and ACA. Using Premier League-inspired scenarios such as identifying team play styles, analyzing counterattacks, or uncovering player performance patterns, we'll walk through a reference architecture for developing, deploying, and operating AI applications and agents on Azure. Attendees will leave with practical guidance and ideas they can extend into their hackathon projects.

The presenter has made these scope decisions. Where they narrow the published wording, they are authoritative:

1. **The app answers the seven inspiration questions below.** They are the "Inspiration" list published with the international football results dataset, and they are the app's target outcomes.
2. **Premier League-inspired scenarios are out of scope.** Team play styles, counterattacks, and player performance patterns need club or event-level data that these datasets do not contain. Do not build or imply them. Prepare one Q&A answer for viewers who ask, because the published abstract mentions them.
3. **"Match and player data"** means the match results, shootouts, former team names, and goalscorer records, used where they serve the seven questions, with coverage disclosed.
4. **The same containerized app runs on AKS and on ACA side by side, and the talk compares the platforms.** That comparison is the platform story of the session.
5. **The "reference architecture for developing, deploying, and operating AI applications and agents"** is this app: develop locally with Docker Compose and GitHub Copilot, deploy to both platforms, and operate with telemetry, evaluation, scaling, rollout, rollback, and cost visibility.
6. **The app's web UI is the main on-stage surface.** GitHub Copilot appears in one short, prepared "extend the app" moment.
7. **"Practical guidance and ideas for hackathon projects"** means the repository, the AKS-versus-ACA decision guide, and a hackathon guide attendees can build on.

The seven questions, verbatim:

1. Who is the best team of all time
2. Which teams dominated different eras of football
3. What trends have there been in international football throughout the ages - home advantage, total goals scored, distribution of teams' strength etc
4. Can we say anything about geopolitics from football fixtures - how has the number of countries changed, which teams like to play each other
5. Which countries host the most matches where they themselves are not participating in
6. How much, if at all, does hosting a major tournament help a country's chances in the tournament
7. Which teams are the most active in playing friendlies and friendly tournaments - does it help or hurt them

"AI-powered" means a Microsoft Foundry model (GPT-6 Astra by default, with GPT-6 Sol deployed alongside) interprets the viewer's question, selects deterministic analytics tools, and writes a grounded explanation of their results. It does not mean the model is the source of the numbers.

The audience is Reactor livestream viewers: developers with mixed experience, many preparing hackathon projects. Assume Python, containers, and REST APIs. Do not assume Kubernetes, Azure, or statistics expertise; explain AKS and ACA concepts and every statistical method in plain language. The title says "soccer" and the data says "football"; use "football" in the app and docs, and acknowledge both terms once in the opening.

Produce working code, infrastructure as code, setup automation, tests, and presenter materials. Do not stop at a plan or pseudocode.

**Presenter-local inputs.** The session information and the inspiration-list screenshot live outside this repository, in the presenter's event folder: `C:\Users\bbenz\OneDrive - Microsoft\Documents\advocacy\events\20261014 - Reactor - Build AI-powered soccer insights apps with AKS and ACA\` (`sessioninfo.md` and `image (2).png`). Everything needed from them is inlined above, so this prompt runs without them. Do not copy them into the repository. The folder's `POC` subfolder holds every POC and presenter-private document; see the output contract.

## Repository Starting State And Output Contract

At the time this prompt was written the repository contained only:

```
data/data sources.md             links to the two Kaggle datasets
data/football_stats/             results.csv, goalscorers.csv, shootouts.csv, former_names.csv                        (local copy; never commit)
data/global_development_data/    WDICSV.csv, WDICountry_Cleaned.csv, WDISeries_Cleaned.csv, Data_Dictionary.csv       (local copy; never commit)
prompts/demopromptv1.md          (this file)
```

There is no README, no agent instructions file, no dependency manifest, no existing source, and **no initialized git repository**. Re-check this before you start; if files have been added since, inspect them, preserve user changes, and follow any conventions they establish.

**The companion repository.** `C:\githublocal\football-results-dashboard` is the session's companion repository: the public, shareable repository attendees will clone after the event. Create it in place in Phase 0, and generate the whole project there, not in another folder or split across repositories. Don't create a GitHub remote or push until the presenter approves publication. Read the raw data location from a setting that defaults to `data/`; if you work in a git worktree, where ignored files such as the data don't exist, point the setting at the companion repository's `data/` folder instead of copying the data.

Adopt these conventions unless you find a documented reason to deviate and say so:

- Put all generated code and infrastructure under `demo/` (for example `demo/src/`, `demo/tests/`, `demo/docker/`, `demo/infra/`, `demo/k8s/`, `demo/aca/`, and `demo/scripts/`). Keep `prompts/` untouched except for additions you are explicitly asked for, and do not stage or commit it until the presenter decides, during publication readiness, which prompts belong in the public repository.
- Put public attendee materials under `docs/`, plus the root `README.md` and `data/README.md`.
- Put every POC and presenter-private document in the POC folder described below, never inside the repository. Public documents never link to it; POC documents may link to public ones.
- Initialize a git repository before generating code. The first commit contains only `.gitignore` and the no-data guard described in the Data Handling Contract. `.gitignore` must cover at minimum: everything under `data/` except `data/README.md` and `data/data sources.md`; tabular and derived data formats anywhere (`*.csv`, `*.parquet`, `*.duckdb*`, `*.sqlite*`, `*.feather`, `*.arrow`, `*.zip`), with a narrow exception for the synthetic test-fixture directory; the local curated-store directory; `.env*` except `.env.example`; `kaggle.json` and `.kaggle/`; `*.pem`, `*.pfx`, and `*.key`; `.azure/` and copied kubeconfig files; `__pycache__/` and `.venv/`; and trace, replay, and evaluation output. Verify the rules with `git check-ignore -v`, because a directory-level ignore silently defeats file-level exceptions. Store hand-authored reference data, such as the team-to-country crosswalk, in a non-ignored format such as YAML.
- Every secret-bearing value lives in an ignored local file or approved secret storage, with a committed `.env.example` containing names and descriptions only. Presenter-specific values, such as the resource group and Foundry names, also live only in the ignored local configuration.

Name these deliverable files explicitly so the presenter can find them under pressure.

Public:

- `README.md` — what the app does, the architecture at a glance, a quick start (get the data, verify it, run Docker Compose), deployment to AKS and ACA, data attribution, and links.
- `data/README.md` — how to download each dataset yourself, the expected layout, the verify command, the dataset versions this demo was verified against, and licenses and attribution.
- `docs/ARCHITECTURE.md` — the reference architecture with diagrams, request and data flows, the deterministic-versus-AI boundary, identity, and telemetry.
- `docs/AKS-VS-ACA.md` — the attendee takeaway: an evidence-backed side-by-side comparison and a "which should my hackathon team choose" guide.
- `docs/METHODS.md` — definitions, method, coverage, and caveats for each of the seven questions; the crosswalk; and how grounding and evaluation work.
- `docs/SETUP.md` and `docs/DEPLOYMENT.md` — local setup; Azure CLI deployment to both platforms, and teardown.
- `docs/HACKATHON-GUIDE.md` — how to extend the app, and ideas to build on.
- `docs/RUNBOOK.md` — the timed run of show with exact presenter actions. It must be self-sufficient: inline each segment's fallback instead of pointing to POC documents, which attendees can't see.
- `docs/ONSTAGE-SCRIPT.md` — the literal questions typed into the app, the GitHub Copilot prompt, and the narration, separate from the runbook.
- `docs/APPENDIX.md` — deeper topics and dated sources.

POC and presenter-private documents live outside the repository, in the POC folder:

`C:\Users\bbenz\OneDrive - Microsoft\Documents\advocacy\events\20261014 - Reactor - Build AI-powered soccer insights apps with AKS and ACA\POC`

Create it in Phase 0 if it doesn't exist, and write to it as you work rather than at the end, so an interrupted session loses nothing. If you can't write to it, stop and report; never fall back to writing POC documents inside the repository. Scripts that write evidence take an output-folder setting that defaults to an ignored local directory, and the presenter's local configuration points it at the POC folder. The folder syncs to OneDrive, so never write secrets, tokens, keys, kubeconfig files, connection strings, or dataset copies there, and sanitize subscription IDs, tenant IDs, and email addresses in evidence. At minimum, it contains:

- `README.md` — an index of the folder.
- `POC-NOTES.md` — the dated POC log: what was done, commands and their outcomes, results, and links to evidence.
- `WORKING-NOTES.md` — open questions, hypotheses, and in-progress findings, pruned as items resolve.
- `DECISIONS.md` — each significant decision with the options, the evidence, and who decided, such as the platform configuration, the ingress option, the local credential path, and the livestream model.
- `COMPATIBILITY-RECORD.md` — dated findings from the Phase 0 gate.
- `COVERAGE-MATRIX.md` — requirement to implementation to evidence to stream moment.
- `POC-VALIDATION-REPORT.md` — results of every Azure POC check on both platforms, cost to date, and security-review findings.
- `RISKS-AND-FALLBACKS.md` — failure modes, detection, and the prepared fallback for each.
- `EVENT-REGISTER.md` — actual resource names, endpoints, model deployments and versions, pinned tool versions, the frozen dataset version, and the teardown date.
- `REHEARSAL-LOG.md` — planned versus actual timing per segment for each rehearsal.
- `evidence/` — sanitized command output and screenshots behind the validation report.
- `replay/` — captured artifacts for livestream fallbacks.

## Data Handling Contract

The two sources are listed in `data/data sources.md`:

| Dataset | Source | License (re-verify) | Notes |
| --- | --- | --- | --- |
| International football results from 1872 to 2026, by Mart Jürisoo | https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017 | CC0: Public Domain | `results.csv`, `goalscorers.csv`, `shootouts.csv`, and `former_names.csv`. Updated often: version 137, last updated 2026-08-26, when this prompt was written. |
| Global Development Data (1960–2025), by Yogesh Mishra, from the World Bank's World Development Indicators (WDI) | https://www.kaggle.com/datasets/yogeshm01/global-development-data-19602025 | CC BY 4.0; the description also points to the World Bank's terms of use | About 200 MB. Attribution required. |

Rules:

- **No data in the public repository** (non-negotiable 5). Hand-authored reference data, such as the team-to-country crosswalk, the major and friendly tournament lists, and era definitions, is code rather than dataset content and is committed: names, codes, and definitions only, never match records or indicator values.
- **Attendees download the data themselves.** `data/README.md` states that Kaggle requires an account; gives manual browser download as the baseline path; offers an optional Kaggle CLI path after you verify its current authentication method and whether a specific dataset version can be requested; shows the exact target layout under `data/`; and explains what to expect if a newer dataset version changes counts. Never commit or print a Kaggle token. Test the instructions by following them literally from a fresh clone.
- **Schema contract and verification.** Commit the expected files, columns, and types as code under `demo/`. A `verify-data` command checks presence, columns, encoding, row-count sanity ranges, and date ranges; fails with a message that points to `data/README.md`; and compares SHA-256 hashes against the files this demo was verified against. Checksum drift produces a warning, not a failure, because attendees may download newer versions; schema drift fails.
- **Resolve the file-name discrepancy.** The WDI Kaggle description lists `WDIData.csv`, `WDICountry.csv`, and `WDISeries.csv`, but the local copy contains `WDICSV.csv`, `WDICountry_Cleaned.csv`, `WDISeries_Cleaned.csv`, and `Data_Dictionary.csv`. Determine what a fresh download actually contains, and make the contract and the instructions match reality.
- **Freeze the event dataset.** After Phase 0, do not re-download before the livestream unless you do it deliberately and re-verify. Record the frozen version in the POC folder's `EVENT-REGISTER.md` and the verified-against version in `data/README.md`.
- **Tests without data.** Unit tests and CI use small, clearly synthetic fixtures with fictional team names and hand-computed expectations. Real-data tests compute their expectations through the deterministic layer at run time and skip when data is absent; do not hardcode real-data values in committed tests.
- **Data-free images.** Never bake data into container images; images must stay safe to publish. Docker Compose mounts the raw `data/` directory read-only, and `ingest` writes the curated store to a separate git-ignored directory or volume. In Azure, services load the curated store from private storage at startup.
- **Private Azure storage.** Use a storage account with public blob access disabled and Microsoft Entra authorization, and disable shared-key access where every consumer supports it. An operator script uploads the raw files from the presenter machine; the ingestion job writes a versioned curated dataset and data-quality report; both platforms read the same curated version.
- **CI.** If you add GitHub Actions, it uses synthetic fixtures only, with no Kaggle credentials and no data artifacts.
- **Guard.** An automated check (a test, an optional pre-commit hook, and a CI step) fails if a tracked file is a data file outside the fixture directory, exceeds a size threshold such as 1 MB, or sits under `data/` other than the allowed files. Run it with `git ls-files` at every gate, and scan the full history before publication.
- **Attribution.** Credit both datasets in `README.md`, `data/README.md`, and the app footer. For CC BY 4.0, credit the World Bank WDI and the Kaggle dataset, and state that the data was reshaped and filtered. Credit the football dataset's author as a courtesy even though it is CC0.

Known data realities, measured on the local copy when this prompt was written. Re-verify them in Phase 0.

- `results.csv`: 49,547 men's full internationals from 1872-11-30 to 2026-08-26; 337 team names; 202 tournament names; 13,158 neutral-venue matches. Scores include extra time but not penalty shootouts, which are in `shootouts.csv` (683 rows). There is no stage or round column. Women's internationals and Olympic, B-team, U-23, and league-select matches are excluded.
- Team names use each team's current name, while `country` uses the venue country's name at the time of the match (for example, a 1950s Ghana home match played in Gold Coast). Use `former_names.csv` (36 rows) and the `neutral` flag; never compare `country` with team names naively.
- `goalscorers.csv`: 47,914 goals, about 33% of the 145,661 goals in `results.csv`. Matches that have scorer rows appear to have complete goal timelines, covering about 34% of scoring matches overall and about 40% since 1990; 254 rows lack a minute. Any goal-level analysis must state its coverage.
- The 2026 FIFA World Cup (104 matches, co-hosted by Canada, Mexico, and the United States) is in the local copy, which makes question 6 timely.
- WDI is wide, with one column per year from 1960 to 2025: 398,468 rows, 1,498 indicators, and 266 entities, including about 48 regional and income-group aggregates that must be excluded from country joins. The main CSV is about 200 MB, over GitHub's 100 MB file limit. Reshape to long format and keep a curated, documented indicator shortlist.
- Joining teams to WDI needs an explicit, reviewed crosswalk. England, Scotland, Wales, and Northern Ireland are separate teams, but WDI has only the United Kingdom. Many names differ: South Korea and "Korea, Rep."; Ivory Coast and "Côte d'Ivoire"; Czech Republic and "Czechia"; Turkey and "Türkiye"; Iran and "Iran, Islamic Rep."; Russia and "Russian Federation"; DR Congo and "Congo, Dem. Rep."; Republic of Ireland and "Ireland"; Hong Kong and "Hong Kong SAR, China"; Palestine and "West Bank and Gaza". Historical teams such as Yugoslavia, Czechoslovakia, and German DR, non-FIFA teams such as Catalonia, Tibet, and Zanzibar, and Taiwan have no WDI entity. The Soviet Union has no separate team name: the 391 matches recorded under Russia before 1992, starting in 1910, include the Soviet era, so decide and document how that affects any development join. WDI starts in 1960. Report crosswalk coverage, and never drop unmapped teams silently.
- The files are UTF-8 with non-ASCII names such as Curaçao, Côte d'Ivoire, and Copa América. Read them with explicit encoding; Windows console code pages mangle them.

## Confirmed Constraints

- Use **Python** for the services, data pipeline, and tests, on a currently supported Python version, with pinned dependencies and a lock file. Use **FastAPI** with a server-rendered web UI and minimal JavaScript. Vendor any static assets so nothing loads from a CDN at runtime, and do not add a single-page-app build toolchain.
- Run locally with **Docker Compose**, and deploy to Azure with the **Azure CLI and Bicep**, as the presenter prefers; do not introduce the Azure Developer CLI. Provide PowerShell scripts first and bash equivalents second; the presenter works in PowerShell on Windows.
- The same image digests run in Docker Compose, on AKS, and on ACA. Configure everything through environment variables. The only platform awareness in code is reading deployment-injected values for the environment badge.
- Use **Microsoft Foundry** as the model backend, in the Foundry project `bbenz-football-results-dashboard` (see Azure Proof Of Concept). Deploy two models side by side: **GPT-6 Astra** (`gpt-6-astra`, version 2026-09-03 when this prompt was written) as the default, and **GPT-6 Sol** (`gpt-6-sol`, version 2026-09-22) as the faster, cheaper alternative. Use Global Standard deployments unless Phase 0 finds a reason not to, pin both versions, and turn off automatic version upgrades for the event window. The Phase 3 evaluation decides which deployment serves the livestream; switching is a configuration change, never a code change. Don't adopt a newer model, such as `gpt-6.1-sol` (released 2026-09-29), without an evaluation and the presenter's approval. Confirm the current product name and documentation URL at implementation time and use them consistently. Keep Foundry content filtering enabled and present it as a platform guardrail layer.
- Model facts verified when this prompt was written; re-verify them: both models are generally available in Foundry without registration, and both support tool calling, parallel tool calls, structured outputs, streaming, and the Responses and Chat Completions APIs. Astra's lowest reasoning effort is `low`, while Sol also accepts `none`. Third-party benchmarks put Astra at about 8.5 s to first token versus about 1.7 s for Sol, and Astra's Global Standard price is five times Sol's ($10 versus $2 per million input tokens, and $50 versus $10 per million output tokens). Default Global Standard quota was at least 1,000,000 tokens per minute for each model. Microsoft notes that Astra may apply enhanced safety controls when its safety systems detect elevated risk. Measure latency, cost, and behavior yourself rather than designing around third-party numbers.
- Authenticate keylessly everywhere: workload identity on AKS, managed identity on ACA, and the operator's own Microsoft Entra sign-in for local development, with key-based (local) authentication disabled on the Foundry resource. Docker Compose containers can't reuse the host's Azure CLI sign-in, so design and document a local path that never needs API keys, such as running `insights` on the host when it must call the live models, or passing in a short-lived token from a helper script that is never logged or committed. Record the choice in `DECISIONS.md`.
- Build one insights agent with tool calling. Use the Microsoft Agent Framework if Phase 0 shows it adds visible value, such as tool orchestration and tracing; otherwise use a direct tool-calling loop with the official SDK. Use exactly one approach. Do not add retrieval-augmented generation, a vector database, text-to-SQL over raw tables, or multiple agents: the data is tabular, and answers must come from deterministic computation.
- Configure everything locally and in Azure **before** the livestream. No package installation, resource provisioning, data download, or substantial code generation on stream, except the single rehearsed GitHub Copilot moment, which must have a prepared fallback commit.
- **Pin the presenter's tools.** Record the exact versions of the GitHub Copilot surface, Docker Desktop, Azure CLI, kubectl, and the browser used in rehearsal; defer auto-updates during the demo window; and re-verify the demo if anything updates.
- Operate prepared demos through the app's web UI and a small number of short terminal aliases. Keep the Azure portal to a minimum.
- Reserve time for the Reactor producer's introduction and for Q&A, and include recovery time within the demo segments.

## Phase Plan And Gates

Work in this order. At each gate, stop, report concisely, and wait only where the gate says to wait. Do not start a later phase to "unblock" an unresolved earlier gate; report the blocker instead.

### Phase 0 — Ground truth, data, and platform gate (stop and report)

1. Re-inspect the repository, preserve user changes, and confirm the starting state above. Create the companion repository in place: initialize git, commit only `.gitignore` and the no-data guard, and prove with `git status` and `git ls-files` that no data file is tracked or staged. Create the POC folder with its `README.md` index, and start `POC-NOTES.md` and `WORKING-NOTES.md`.
2. Record every environmental input. Settings the code or scripts read go into `.env.example` as names and descriptions, with the presenter's values in the ignored local configuration; event facts go into `EVENT-REGISTER.md`. The inputs include the subscription, region, the resource group and Foundry names from Azure Proof Of Concept, AKS options, ACA environment, registry, storage account, both model deployments, Log Analytics workspace, presenter tool versions, the Reactor streaming setup and tech-check time, and the speaker lineup. Never request secrets in chat or commit them.
3. Check the presenter machine rather than assuming: Python on `PATH`, Docker Desktop with Compose, Azure CLI with Bicep, kubectl and kubelogin, Git, and network access to PyPI, container registries, Kaggle, and Azure endpoints. A previous demo on this machine found Python missing from `PATH` and a package host blocked.
4. Consult current official documentation for AKS, ACA, Microsoft Foundry, Azure Monitor OpenTelemetry, the Python SDKs you select, the Kaggle CLI, and the GitHub Copilot surface. Record SDK, API, and CLI versions, source links, the verification date, and any preview dependencies.
5. Establish data ground truth under the Data Handling Contract: dataset versions, licenses, file names, sizes, SHA-256 hashes, row counts, and date ranges. Resolve the WDI file-name discrepancy, and confirm what a fresh Kaggle download contains and how attendees authenticate.
6. Profile the data and draft `docs/METHODS.md`: definitions for each of the seven questions, the crosswalk with measured coverage, the major and friendly tournament lists, era boundaries, minimum sample sizes, and what each question cannot answer.
7. Choose the platform configuration and record why: AKS Automatic or AKS Standard, for a fair comparison with ACA; the AKS ingress option (the NGINX-based application routing add-on receives only critical security patches through November 2026, and AKS recommends Gateway API going forward, so verify the currently recommended option before choosing); the ACA plan or workload profile; keyless identity paths to Foundry, storage, and the registry on both platforms; minimum replicas for the show; and region availability and quota for both platforms and both models.
8. Confirm GPT-6 Astra and GPT-6 Sol availability, versions, deployment types, and quota in the chosen subscription and region, and escalate any gap as a blocker. Make the serving deployment configurable. Confirm which API surface, Responses or Chat Completions, the chosen SDK supports with keyless authentication and tool calling for both models. Choose between the Microsoft Agent Framework and a direct tool-calling loop, and record why.
9. Verify the GitHub Copilot surface, the desktop app or VS Code, for the "extend the app" moment on the presenter machine, and record and pin its version.
10. Confirm event logistics with the presenter: speaker lineup, streaming platform, tech-check time, how Q&A is relayed, and whether viewers will get a public URL.

**Gate 0 output:** `COMPATIBILITY-RECORD.md` and `DECISIONS.md` in the POC folder, a data profile with crosswalk coverage, the `docs/METHODS.md` draft, the proposed architecture and platform choices, and any true blockers. Ask the presenter to confirm the subscription, the region, the estimated POC cost, and a proposed budget; that is the single provisioning confirmation for the POC. Wait for the answer, then continue to Phase 1 unless a blocker requires a decision from the presenter.

### Phase 1 — Local vertical slice

Build the smallest end-to-end path that actually runs locally under Docker Compose: `verify-data`; `ingest` into the curated store with its data-quality report; one deterministic tool, such as question 3's home-advantage trend, with unit tests on synthetic fixtures; the `insights` endpoint; and the `web` page with its chart, expanders, and environment badge, emitting structured logs and a local trace.

**Gate 1:** show the commands and output for `verify-data` passing on the real data and failing clearly when a file is missing; the question 3 view rendered from Docker Compose; unit tests green on synthetic fixtures; and `git ls-files` plus the guard proving no data is tracked.

### Phase 2 — Seven questions and the grounded insights agent

First provision the POC foundation described in Azure Proof Of Concept, so development calls the real models. Then add deterministic analytics for all seven questions, including the crosswalk and the development lens, each exposed as a typed tool; the insights agent calling both Foundry deployments through configuration; the grounded answer format and validator; insight cards for all seven questions; the free-form question box; and limitation handling.

**Gate 2:** all seven questions answered through live calls to both model deployments, with deterministic evidence; the grounding check passing on every answer; one out-of-scope question producing an honest limitation; and repeated runs proving the numbers are identical while the narrative may vary.

### Phase 3 — Evaluation, safety, and observability

Add the evaluation suite, content-filter and responsible-framing cases, bounded inputs and outputs, rate limiting, end-to-end OpenTelemetry tracing with token usage, the local trace view, and the KQL queries. Run the evaluation against both model deployments, and choose the livestream deployment with a decision rule agreed with the presenter that weighs grounding pass rate, tool-selection accuracy, p95 latency per answer, and cost per answer. Record the numbers and the decision in `DECISIONS.md`.

**Gate 3:** evaluation results for both models against agreed thresholds, as actual values from repeated runs, and the chosen livestream deployment; one local trace linking the UI request through `web`, `insights`, a tool, and the Foundry call; and the no-data guard green.

### Phase 4 — Azure POC on AKS and ACA side by side

Generate the complete Bicep, Kubernetes manifests, ACA definitions, and Azure CLI scripts, then run the Azure POC as specified in Azure Proof Of Concept: deploy to both platforms in `bbenz-football-results-dashboard` by following the public docs literally, validate that the code works on Azure, run the completeness-and-coherence review, collect the comparison measurements, and refine the public docs from what the POC proved. If environment access is unavailable, generate the artifacts anyway and list precisely which cloud checks remain unverified.

**Gate 4:** `POC-VALIDATION-REPORT.md` in the POC folder, with every check passed or explicitly accepted by the presenter; both endpoints healthy with truthful badges; the same image digests on both; live calls to the serving model from each platform through keyless identity, with sanitized evidence; identical deterministic results from both; and the comparison measurements recorded.

### Phase 5 — Presenter materials, publication readiness, and rehearsal

Produce the named deliverables, the prepared Copilot moment with its fallback commit, the prebuilt v2 image, the fallback tiers, the replay capture commands, and the rehearsal checklist. Run the publication-readiness review. Time a full dry run and record actual versus planned timing per segment.

**Gate 5:** the handoff report described in the completion contract.

## One Story: 150 Years Of International Football, One App, Two Platforms

Use one coherent story throughout: **What can more than 150 years of international football tell us, and what does it take to ship those insights as an AI app on AKS and on ACA?**

Implement a minimal architecture:

- **`web`:** a FastAPI service that serves the server-rendered UI and a small JSON API. It is the only publicly reachable service.
- **`insights`:** an internal FastAPI service that hosts the deterministic analytics tools over the curated store and the insights agent that calls Foundry. It is never publicly exposed.
- **`ingest`:** a batch job that verifies the raw files, builds the curated store and data-quality report, and publishes a versioned curated dataset idempotently.
- **Curated store:** an embedded analytical engine, preferably DuckDB over Parquet, loaded at startup from the git-ignored local curated directory or from private Azure storage. Do not add a managed database unless Phase 0 finds a concrete need; it adds cost and setup without demonstrating a session requirement.
- **Microsoft Foundry:** the project `bbenz-football-results-dashboard` with two model deployments, GPT-6 Astra (the default) and GPT-6 Sol, shared by both platforms and reached through keyless identity. Which deployment serves answers is configuration.
- **Telemetry:** OpenTelemetry to one Application Insights resource for both platforms, with the platform as a dimension, plus structured local logs available immediately when cloud ingestion lags.
- **Platforms:** the same image digests on AKS (Deployments, Services, the ingress chosen in Phase 0, a Job for ingest, and workload identity) and on ACA (Container Apps with external and internal ingress, an ACA Job for ingest, and managed identity), in the same region.

Use at most three container images. Avoid message queues, caches, custom dashboards, additional agents, or services that do not demonstrate a session requirement.

## Required Behavior And Evidence

Create `COVERAGE-MATRIX.md` in the POC folder with one row for every requirement below, mapped to implementation, automated or manual check, stream moment, and expected evidence.

### 1. The Seven Questions

Every question gets a deterministic tool or small set of tools, a `docs/METHODS.md` entry, an insight card with an expander in the UI, at least three phrasings in the evaluation set, a moment in the run of show, and a coverage-matrix row. The minimum analysis per question:

| # | Deterministic Analysis (Minimum) | Development Lens (WDI) | Must Disclose |
| --- | --- | --- | --- |
| 1 | A transparent rating model, for example Elo-style with documented match-importance weights, home advantage, and margin handling, with all-time peak, sustained average, and longevity lenses, plus simple records with minimum-match thresholds. | Optional per-capita view, labeled as a novelty. | "Best" depends on the definition; show the lens and parameters; early eras have sparse schedules. |
| 2 | Documented era boundaries; leaders per era by rating; dominance margin; records against the era's other top teams. | Not required. | Era boundaries are a choice; early samples are small. |
| 3 | Home advantage over time in non-neutral matches; goals per match over time; spread of team strength over time; optional penalty and goal-timing trends from goalscorer data. | Strength distribution by WDI region and income group since 1960. | Goalscorer coverage; changing composition, such as more teams and more friendlies, confounds trends. |
| 4 | Distinct active teams by year, with entries and exits reconciled through former names; the fixture network, including the most frequent pairings, communities versus confederation or region, and intra- versus inter-region share over time. | WDI region and income group to describe who plays whom. | Observational only; a team is not always a sovereign state; historical teams have no WDI entity. |
| 5 | Matches whose venue country at the time is neither participant, reconciled with former names and the `neutral` flag; rankings and trends; top host cities. | Region and income group of frequent neutral hosts. | How venue and team names were reconciled, and how disagreements with `neutral` were handled. |
| 6 | A documented list of major tournaments; hosts per edition derived from venue countries, handling co-hosts; host performance versus rating-based expectation and versus the same team's non-host editions; matches played per edition as a progression proxy. Use the 2026 FIFA World Cup as the timely example if it is in the frozen data. | Optional control for host GDP per capita or population. | Small samples and uncertainty; formats vary; there is no stage column, so do not claim titles or rounds unless they are reliably derivable. |
| 7 | A documented friendly classification (`Friendly` plus a reviewed list of friendly tournaments); activity leaders by era; the relationship between friendly volume and subsequent competitive results or rating change, with a documented comparison design. | Friendly volume by income group. | Observational, not causal; selection effects, such as strong teams receiving more invitations. |

Set minimum sample sizes, show uncertainty where it matters (for example, intervals for the host effect), and state what each question cannot conclude.

**Responsible framing.** Questions 3, 4, 5, and 7 touch on geopolitics and national development. Describe patterns neutrally; make no causal or value-laden claims about countries or peoples; and treat development indicators as context, not as explanations or rankings of worth. Enforce this in the model instructions and in evaluation cases.

### 2. Grounded Insights Agent

- The agent calls typed, read-only tools with bounded outputs: aggregates, never raw tables. Each tool result carries evidence IDs, the method version, the dataset version, coverage notes, and caveats.
- Each answer contains a short narrative; the key numbers, each tied to an evidence ID; a chart built from tool data, never from model-generated numbers; caveats taken from tool metadata; a "what this data can't tell you" note; and the model deployment, latency, and token usage.
- A deterministic grounding validator checks that every number in the narrative matches a tool value within stated rounding. On failure, retry once with feedback, then fall back to the deterministic evidence with a visible notice. Never show an ungrounded number as fact.
- Out-of-scope requests get an honest explanation of the limitation and of the data that would be needed, never an invented answer. They include club football, women's internationals, tactics such as possession or counterattacks, player statistics beyond goals, predictions or betting, and anything outside the data's date range.
- Viewer questions and dataset strings are untrusted input. The agent has no write, admin, shell, or network tools. Bound question length, tool calls per answer, and output tokens.
- Foundry content filtering stays on. Handle a filtered response gracefully, and pre-test geopolitics questions on both models for false positives, including Astra's enhanced safety controls.
- When the model is unavailable, insight cards and evidence still render. The narrative area says the AI narrative is unavailable, or shows a cached narrative labeled with its generation time and source. Never fabricate. A graceful fallback must never hide a broken model path: the badge and telemetry show whenever an answer isn't live, and POC validation fails if an answer that should be live isn't.

### 3. Same App On AKS And ACA, Compared With Evidence

- Deploy identical image digests to both platforms, in the same region, against the same serving model deployment and curated data version. Inject the platform name and region through deployment configuration so the badge reflects reality.
- **AKS:** a Deployment and Service per service; `insights` internal only; ingress for `web` using the option chosen in Phase 0; horizontal scaling with HPA or KEDA; workload identity federated to a user-assigned managed identity; image pulls from the registry through managed identity; a Job for ingest; probes and resource requests and limits; and a network policy that allows only `web` to reach `insights`.
- **ACA:** one Container Apps environment; `web` with external ingress; `insights` with internal-only ingress; scale rules; a user-assigned managed identity; image pulls from the registry through that identity; an ACA Job for ingest; probes; and revisions.
- Give each identity only the roles it needs on Foundry, storage, and the registry, and verify the current least-privilege role names. Foundry roles were renamed recently; for example, Foundry User was previously Azure AI User.
- Build `docs/AKS-VS-ACA.md` from measurements, each with its date and method: what you manage; deployment artifacts, as object and line counts; identity setup steps; ingress and TLS; internal service-to-service networking; scaling behavior under the same bounded load test; rollout and rollback of the same v2 image (an ACA revision with a traffic split versus an AKS rolling update); jobs; observability integration; cold-start behavior at the chosen minimum replicas; estimated daily cost at demo scale from dated pricing pages; and day-2 operations such as upgrades. Label estimates as estimates. Keep the comparison fair: same image, region, replica floors, model, and data.
- Load tests target deterministic endpoints only, never model calls, and are bounded in rate and duration.
- End with guidance, grounded in what you measured, for a hackathon team choosing between the platforms.

### 4. Data Pipeline And Data Quality

- `verify-data`, then `ingest`, produce the curated store and a data-quality report: row counts, date ranges, dataset versions, crosswalk coverage, goalscorer coverage, and rows excluded or unmapped, with reasons.
- Ingestion is idempotent, versions its output, and switches the active version atomically. Both platforms can run the same job image with their native job primitives without conflicting.
- Show the data-quality report in the app on a Data page and through a command.

### 5. Observability, Evaluation, And Cost

- Use OpenTelemetry with W3C trace-context propagation from `web` through `insights` to the Foundry call. Follow the current generative AI semantic conventions for model spans where the SDK supports them, and verify their status. Emit a span per tool call with the tool name, duration, row counts, and evidence IDs, plus attributes for platform, image digest, dataset version, method version, and grounding result.
- Both platforms export to the same Application Insights resource and are distinguishable by cloud role and platform. Supply working KQL queries that match the actual telemetry, plus an immediate local JSON trace view for on-stream reliability when ingestion lags.
- Do not log full prompts or model responses by default, and never log secrets.
- Report token usage and estimated cost per answer and per day, and latency at p50 and p95, for each platform and each model deployment.
- Build an evaluation suite: at least three phrasings per question; expected tools; expected facts computed through the deterministic layer at test time; grounding pass rate; tool-selection accuracy; limitation handling; responsible-framing checks; and latency and token budgets. Run it repeatedly against both model deployments, because model output varies; agree thresholds and the model decision rule at Phase 3; and summarize the results, including the model comparison, in `docs/METHODS.md` as metrics only. Use Foundry's evaluation tooling only if it adds visible value.

### 6. A Web UI Built For A Livestream

- Use a base font of at least 20 px, a zoom control, a high-contrast theme tested on a 1080p screen share, a color-blind-safe chart palette, and a text summary for every chart.
- An "About this app" expander at the top explains the purpose, how the app works, what is deterministic and what is AI, and where the data came from. Each question card has an expander explaining what is asked, which data and method are used, what the expected result looks like, and why it matters, including caveats. Each answer has an expander showing the tool calls and evidence.
- An environment badge shows the platform (Local, AKS, or ACA) and region from real runtime configuration, never hardcoded; the short image digest; the dataset version; the serving model deployment; and whether the AI narrative is live, cached, or unavailable.
- Every answer shows a copyable trace ID for Application Insights.
- The footer carries data attribution.
- Apply security headers and per-client rate limiting, and expose no admin or reset endpoints publicly.

### 7. Attendee Takeaways

- `docs/ARCHITECTURE.md`: diagrams (Mermaid is fine) for the components; the request flow from question through agent, tools, and Foundry to a grounded answer; the data flow from download through verification and ingestion to the services; identity; and telemetry.
- `docs/AKS-VS-ACA.md`: the evidence-backed comparison and decision guide.
- `docs/HACKATHON-GUIDE.md`: how to add a question and tool, following the same pattern as the Copilot moment; how to add a development-indicator lens; how to bring your own dataset with the schema-contract and crosswalk pattern; how to swap the model; how to deploy to your own subscription on either platform; cost and teardown; and extension ideas grounded in the seven questions and this data.
- Documentation may quote a few aggregate results as illustrations, never tables of records.

## Azure Proof Of Concept

The Azure POC proves, before any rehearsal, that the code works on Azure and that the repository is complete and coherent. It is the evidence behind Gate 4. Its foundation is provisioned at the start of Phase 2, so local development calls the real models; the platforms follow in Phase 4.

### Approved Scope And Naming

- **Resource group:** `bbenz-football-results-dashboard`, containing every POC resource. The presenter approved creating and changing resources in it. At Gate 0, the presenter confirms the subscription, the region, the estimated cost, and the budget; that one confirmation covers all later POC provisioning in this resource group.
- **Still ask first:** any other resource group or subscription; public access beyond the operator's IP address; spending past the budget; deleting the resource group or anything the POC didn't create; and pushing or publishing the repository.
- **Foundry:** a Foundry resource with a project named `bbenz-football-results-dashboard`. Model deployments belong to the Foundry resource and its projects share them, so create both deployments on that resource and call them through the project; verify this resource model at implementation time. Name the Foundry resource `bbenz-football-results-dashboard` as well if that globally unique name is available; otherwise add a short suffix and record why.
- **Models:** `gpt-6-astra` as the default and `gpt-6-sol` alongside, as described in Confirmed Constraints.
- **Other names:** derive them from `bbenz-football-results-dashboard` within each resource type's rules. Registry and storage account names allow only letters and digits and must be globally unique, storage account names are lowercase with at most 24 characters, and container app names allow at most 32 characters. Tag every resource with the project, the event date, and the planned teardown date.
- **Presenter values stay out of tracked files.** Bicep and scripts take every name as a parameter; the presenter's values live in the ignored local configuration and in `EVENT-REGISTER.md`; public docs use placeholders.

### Sequence

1. **Foundation, at the start of Phase 2:** the resource group, the Foundry resource and project with both model deployments, Log Analytics and Application Insights, and a budget alert, provisioned with the same documented commands the public docs describe. Grant the operator's own identity the least-privilege inference role, so local development calls the real models without keys.
2. **Platforms, in Phase 4:** the registry, private storage with the raw data uploaded, managed identities, the AKS cluster, and the ACA environment; then the ingest job and the same image digests on both platforms.
3. **Deploy from the docs.** Follow `docs/DEPLOYMENT.md` literally in PowerShell. Whenever reality differs, fix the code or the document, rerun, and log the discrepancy in `POC-NOTES.md`. Then rerun the whole deployment to prove it is idempotent.
4. **Restrict access.** Until the presenter approves wider access, each public endpoint accepts traffic only from the operator's current public IP address, using each platform's native IP restriction. How each platform does this is itself a comparison data point.

### Validation: The Code Works On Azure

Run each check on both platforms, and record the results and sanitized evidence in the POC folder:

- The ingest job ran on the platform's native job primitive and produced the same curated dataset version and checksums as on the other platform.
- Health checks, the UI, and truthful badges work; all seven insight cards render with evidence.
- The evaluation suite ran against the deployed endpoint with the serving model deployment, plus a smaller run with the other deployment.
- The model was actually reached: every live answer reports its model deployment and token usage, Application Insights records the same calls, and Foundry's own metrics show matching requests. A graceful fallback that hides a broken model path fails this check.
- Configuration is keyless: no keys, connection strings, or secrets in any deployed configuration; local authentication disabled on the Foundry resource, shared-key access disabled on storage, and the registry admin user disabled, wherever each consumer supports it.
- The network is isolated: `insights` can't be reached from the internet on either platform, tested from outside, and only `web` reaches it.
- The cross-platform parity test, the bounded load tests and scaling, the v2 rollout and rollback, and one end-to-end trace per platform, found with the documented KQL queries, all succeed.
- A security review of the public endpoints is complete, with findings fixed or explicitly accepted by the presenter.
- Cost to date, the projected daily cost for the event window, and the budget alert are recorded.

### Validation: The Repository Is Complete And Coherent

- Every command in the public docs was run as written, in PowerShell, and in bash wherever the docs claim bash support. Anything not run is marked unverified in the docs.
- Configuration agrees everywhere: every setting the code reads appears in `.env.example`, in the docs, and in the Bicep, manifests, or ACA definitions that set it, and nothing sets a value the code never reads.
- Names, ports, and paths agree across code, scripts, infrastructure, and docs. Every file, script, and link the docs mention exists, and the link check passes.
- There are no TODO or FIXME markers, stubs, placeholder logic, dead endpoints, unused dependencies, or orphaned files. Lint, type checks, and tests are green.
- Every question, tool, and insight card the docs describe exists in the app, and the app has none the docs omit.
- The fresh-clone test passes.
- The teardown script's dry run lists exactly the POC's resources. The real teardown waits for the presenter's approval after the event.
- The no-data guard passes on the working tree and the full history, and no POC or presenter-private document exists anywhere in the repository.

### Documentation During The POC

Treat the public docs as part of the product, and refine them throughout the POC. Update a doc in the same commit as the change that makes it true: corrected commands, verified versions with dates, measured comparison values, troubleshooting for problems the POC actually hit, and known limitations. Public docs explain how to build, deploy, operate, and extend the app; they never narrate the POC. What was tried, what failed, the evidence, and the decisions go in the POC folder.

## Mandatory 60-Minute Run Of Show

Preserve this total budget. Put setup details and deeper implementation discussion in the appendix, not the live path.

| Time | Duration | Prepared Live Moment |
| --- | --- | --- |
| 00:00-03:00 | 3 min | After the Reactor producer's welcome, state the question, show the seven inspiration questions, and show the app running on ACA and AKS side by side with their environment badges. Say what attendees will leave with. |
| 03:00-09:00 | 6 min | One reference-architecture diagram: one set of images on two platforms, the data flow, deterministic tools versus the AI narrative, keyless identity, and telemetry. State the data rule: the repository contains no data, and here is where to get it. |
| 09:00-15:00 | 6 min | Data: sources and licenses, the verify command, the data-quality report (coverage, crosswalk, and quirks), and the ingestion job on one platform, with the other platform's run as recorded evidence. |
| 15:00-30:00 | 15 min | The seven questions: ask at least three live through the agent, showing tool calls, evidence, the chart, and the grounding badge; show the rest as insight cards; include one development-lens view and the 2026 World Cup hosting example; then ask one question the data cannot answer and show the honest limitation. |
| 30:00-39:00 | 9 min | AKS versus ACA side by side: deployment definitions, identity wiring, ingress, internal networking, and a bounded load test against deterministic endpoints showing how each platform scales; then the evidence-backed comparison table. |
| 39:00-46:00 | 7 min | Develop and ship: GitHub Copilot extends the app with one small analytics tool and its test; then roll out the prepared v2 image as an ACA revision with a traffic split and as an AKS rolling update, and roll one back. |
| 46:00-51:00 | 5 min | Operate: one end-to-end trace from the UI through the agent, a tool, and the Foundry call; token usage and cost per answer on each platform; evaluation results, including how they chose between GPT-6 Astra and GPT-6 Sol; and content filtering. |
| 51:00-53:00 | 2 min | Hackathon launchpad: repository tour, how to get the data, extension ideas, and the AKS-versus-ACA decision guide. |
| 53:00-60:00 | 7 min | Q&A relayed by the Reactor moderator, with the decision guide visible. |

For every segment, generate exact presenter actions, short narration, the literal questions or prompts to type, expected tool calls, expected safe output, code locations to open, a one-command or equivalent rehearsed action, and a fallback. Say in advance which evidence is recorded rather than produced live, and say on stream that the v2 image was built from the prepared commit during rehearsal. Keep screen switching minimal and everything legible on a compressed video stream.

For the three live questions, default to question 6 (the 2026 World Cup hosts), question 1 (the best team, showing how the definition changes the answer), and question 3 (trends), unless rehearsal shows that others land better.

Design the GitHub Copilot moment to succeed even though generated code varies: show the prompt and the generation, run the tests, and if anything deviates, switch to the prepared commit and say so. A good target is one small deterministic tool plus its insight card and test, such as the biggest upsets by era based on the existing rating model. Questions typed into the app operate prepared features and inspect evidence; the single Copilot prompt adds one small, rehearsed feature and never rewrites or redeploys the project.

### Time Discipline: Cut Depth, Never Coverage

Everything the published description promises, as scoped above, must appear on screen at least as a stated result with visible evidence. When running long, reduce how something is produced, not whether it is shown. Generate an explicit degradation ladder in the runbook:

- **Tier A, always live:** both deployments reachable with truthful badges; at least three questions answered live through Foundry with the grounding badge; all seven questions visible with deterministic evidence; the honest-limitation answer; the no-data-in-the-repository moment with download instructions; the evidence-backed comparison table; and one end-to-end trace.
- **Tier B, live if on time, otherwise prepared evidence:** the ingestion job run, the load-test scaling, the GitHub Copilot moment, the v2 rollout and rollback, additional live questions, the content-filter example, and the evaluation run.
- **Tier C, compress first:** narration depth; code, Bicep, and manifest walkthroughs; the KQL query; methodology detail; and appendix topics deferred to Q&A or the repository.

Add a per-segment hard stop rule: if a segment runs more than 60 seconds over budget, switch to its prepared evidence and move on. Mark each runbook step with its tier and its stop-time checkpoint so the presenter can self-correct without doing arithmetic on stream.

Provide short Q&A answers for: which platform a hackathon team should choose; why the model does not compute the statistics or write SQL; where the Premier League scenarios from the abstract went, and how this architecture would take club or event-level data; what the demo costs to run; why the app deploys two models and how the evaluation chose between them; and whether an open or self-hosted model could replace them.

## Implementation And Setup Deliverables

Generate the following, adapting names to repository conventions:

1. **Runnable Python project:** `web`, `insights` (the analytics tools and the agent), and `ingest`; typed tool schemas; the grounding validator; the crosswalk and reference lists; structured telemetry; and secure configuration loading. Include a dependency lock and the supported Python version.
2. **Data tooling:** the schema contract, `verify-data`, an optional Kaggle CLI download helper, `ingest`, the data-quality report, and the no-data guard.
3. **Containers:** Dockerfiles for the three images and a Docker Compose file for local use, with raw `data/` mounted read-only and the curated store in a separate git-ignored location.
4. **Infrastructure as code:** Bicep for the shared resources (registry, storage, the Foundry resource and project with both model deployments, Log Analytics and Application Insights, managed identities, least-privilege role assignments, and a budget alert), the AKS cluster, and the ACA environment, apps, and job, with every name and presenter value supplied as a parameter; Kubernetes manifests for AKS; and parameters, outputs, cost notes, and a teardown with a dry-run mode, scoped to demo-owned resources.
5. **Operator commands** with short aliases, PowerShell first: bootstrap, verify data, ingest, start locally, run tests, run the evaluation, deploy shared resources, upload data, deploy to AKS, deploy to ACA, run the ingest job on each platform, smoke-test both, load-test both within bounds, roll out v2 on both, roll back, switch the serving model deployment, update the ingress allow-list, open the local trace view, preflight, reset, and teardown. Keep reset and admin actions outside the app's public surface. No live step should require typing a long command.
6. **Tests and evidence:** unit tests for every analytics tool on synthetic fixtures; schema-contract tests; crosswalk coverage reporting; API tests; agent tests that use recorded tool outputs and are labeled as replays; grounding-validator tests; the live evaluation suite, skipped without configuration; a cross-platform parity test proving identical deterministic results from AKS and ACA; the no-data guard; and a UI smoke test.
7. **Presenter materials:** the runbook (with the timed schedule, tiers, stop times, code bookmarks, recovery paths, and a rehearsal checklist) and the on-stage script named in the output contract, plus the prepared fallback commit for the Copilot moment and the prebuilt v2 image.
8. **Attendee materials:** every public document named in the output contract.
9. **Risk register:** `RISKS-AND-FALLBACKS.md` in the POC folder, covering at least Foundry throttling or quota exhaustion on either deployment, model latency spikes, a content-filter false positive or an Astra safety-control intervention on a geopolitics question, an unexpected model version change, AKS ingress or node problems, a failed ACA revision, registry pull or storage authorization failures, expired Azure CLI or kubectl credentials, the operator's IP address changing so the allow-list blocks the presenter, dataset drift from an accidental re-download, a tool or Copilot client update, nondeterministic Copilot output, telemetry ingestion delay, and a dropped stream or failed screen share. For each, record how the presenter detects it within seconds and the exact prepared fallback.

Use placeholders only for environment-specific values and credentials, never as substitutes for required analytics, grounding, or security checks.

## Reliability And Safety

- Use the dedicated resource group `bbenz-football-results-dashboard` and least-privilege identities. Include quotas, model availability, deployment latency, expected cost drivers (AKS nodes, ACA replicas, Foundry tokens, with Astra at five times Sol's price, and Log Analytics ingestion), the budget alert, and cleanup guidance in the preflight.
- Keep credentials out of prompts, source files, logs, command arguments, and screenshots. The Kaggle token stays in the presenter's user profile or environment, and the deployed app never needs it.
- **Plan for credential lifetime.** Azure CLI sessions, kubectl credentials, GitHub Copilot sign-in, and Kaggle tokens can expire between rehearsal and stream. Document each lifetime, refresh where supported, and include a 60-second preflight that proves each is valid immediately before the livestream, plus a rehearsed re-authentication path that fits inside a segment.
- Prebuild, deploy, seed data, and warm services before stream time. Keep at least one replica of each service running on both platforms during the show and document the temporary cost; make a warm-up model call; and test the stream connection, with a wired or tethered fallback.
- Apply bounded timeouts and retries. Tools are read-only, so retries are safe; bound model calls, inputs, and outputs, and never let model output change deterministic results or configuration.
- Keep scenarios independently runnable and state resettable so that one failure does not block the next. Rehearse successive runs without manual repair.
- Provide explicit fallback tiers: both platforms live; one platform live, with the other shown through recorded evidence; local Docker Compose with live Foundry; local with cached narratives clearly labeled; and then a recorded screen capture. Offline mode cannot demonstrate live model inference or live cloud behavior; say so on stream.
- Provide commands to capture replay artifacts during a successful rehearsal. Do not fabricate recordings or present fixture output as observed cloud behavior.
- **Public endpoints.** During the POC, both public endpoints accept traffic only from the operator's IP address, and the preflight checks that the allow-list still matches the presenter's current address. Decide with the presenter whether viewers get a URL. If they do, require TLS, per-client rate limits, a token budget cap, content filtering, no admin endpoints, monitoring, and a recorded teardown or scale-down date. Run a security review of the public endpoints before sharing any URL and before leaving the deployment running after the event.
- Keep fail-open switches and intentionally vulnerable endpoints out of deployed configurations.

### Livestream And Screen Hygiene

Generate a presenter machine checklist covering at least: notifications and focus assist off; mail, chat, and calendar closed; system sounds muted; a demo-only browser profile with no corporate autofill, saved passwords, or personal bookmarks; UI, terminal, and editor fonts legible on a compressed 1080p stream; a high-contrast theme; a fixed window layout with few switches; confirmation of exactly which screen or window the producer is capturing; the runbook on a second, unshared screen; shell history cleared of anything sensitive; and no subscription IDs, tenant IDs, email addresses, keys, portal account menus, or POC notes on screen. The recording is permanent, so pseudonymize anything identifying and prefer the app and terminal over the Azure portal.

## Preparation Timeline

This prompt was written on September 29, 2026, fifteen days before the livestream. Express milestones as T-minus days from October 14, 2026, and include them in the rehearsal checklist:

- **T-14 (September 30):** Phase 0 complete: companion repository and POC folder created; compatibility record dated; subscription, region, and model quota confirmed; methodology drafted; blockers escalated.
- **T-12 (October 2):** Phase 1 complete locally; POC foundation provisioned with both model deployments.
- **T-10 (October 4):** Phases 2 and 3 complete against the live models; evaluation has chosen the livestream deployment.
- **T-8 (October 6):** Azure POC deployed to AKS and ACA and validated, including the completeness-and-coherence review; public docs refined from what it proved.
- **T-7 (October 7):** First timed end-to-end rehearsal on the presenter machine with pinned tools; replay artifacts captured; Copilot moment rehearsed.
- **T-4 (October 10):** Second timed rehearsal after a full reset; runbook and on-stage script frozen; Reactor tech check completed (confirm its date with the producer).
- **T-1 (October 13):** Services warmed; dataset version frozen and re-verified; credentials re-validated; fallback artifacts verified openable offline.
- **Day of:** Preflight run an hour before the stream; credentials confirmed; no updates installed.

This runway is short. If you start later than September 30, recompute the dates and say so in your report rather than silently compressing the plan.

## Publication Readiness

The public repository must read as a demo someone can replicate, not as a working folder for one talk. Before any push, and only with the presenter's approval:

- Prove that no data or derived data exists in any commit, by scanning history and not just the working tree, and that no container image contains data.
- Remove presenter-specific values from tracked files, using placeholders instead: the resource group and Foundry names (`bbenz-football-results-dashboard`), subscription and tenant identifiers, email addresses, endpoints, and absolute paths. This prompt contains several of them, including the POC folder path: flag them, and do not edit prompts without asking.
- Confirm that no POC or presenter-private document exists anywhere in the repository, tracked or ignored, and that no public document links to the POC folder. Run a link check with zero broken local links.
- Add `prompts/README.md` explaining what each prompt does, and that the session information lives outside the repository.  Commit only the prompts the presenter approves.
- Add community health files written for this repository: `LICENSE` (MIT unless the presenter decides otherwise), `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, and `SECURITY.md`.
- Run a fresh-clone test: clone into a temporary folder, follow `data/README.md` literally, and bring the app up with Docker Compose.
- Confirm that the POC folder's `README.md` index is current and its documents are complete.

## Verification And Completion Contract

Build incrementally and run focused checks after each meaningful change. Complete all feasible local validation. With authorized cloud access, run deployment validation and a full rehearsal against both platforms. A replay does not count as a successful live integration.

The project is ready only when:

- Every scoped promise and all seven questions map to an implementation, evidence, and a moment within the 60-minute schedule.
- Each of the seven questions is answered by deterministic, tested analytics, with its method, coverage, and caveats stated in `docs/METHODS.md` and in the UI.
- Both model deployments run behind the insights agent on AKS and ACA through keyless identity; the livestream deployment was chosen by evaluation; model calls are visible in traces and in Foundry's metrics; and the grounding check proves the model is never the source of a number.
- The same image digests run on both platforms, both endpoints are healthy with truthful badges, and deterministic results are identical across platforms.
- `docs/AKS-VS-ACA.md` rests on dated measurements, with estimates labeled.
- The Azure POC in `bbenz-football-results-dashboard` passed every check in Azure Proof Of Concept, including the completeness-and-coherence review, as recorded in `POC-VALIDATION-REPORT.md`.
- The public documentation was refined during the POC and matches verified behavior, and no POC or presenter-private document exists in the repository.
- No dataset or derived data is tracked in git, including history; images contain no data; CI runs on synthetic fixtures; and the fresh-clone test passes by following `data/README.md` literally.
- Out-of-scope questions produce honest limitations, and responsible-framing checks pass.
- Local checks pass, cloud checks are either evidenced or explicitly marked unverified, the reset path works, and the presenter has rehearsed the full flow within 60 minutes.

Finish with a concise handoff: generated file locations, commands executed and their outcomes, coverage status, remaining environment-specific actions, estimated versus actual rehearsal timing, limitations, and links to the runbook, the comparison guide, the data instructions, and the POC validation report. Never call the demo ready when a required number, model call, or platform deployment has only been mocked.

## Authoritative Starting References

Recheck these and their relevant linked pages at implementation time; the event is in October 2026, and product behavior can change. Prefer dated or versioned sources in the compatibility record.

- Session page: https://developer.microsoft.com/en-us/reactor/events/27536/
- Data sources: `data/data sources.md`, which links to:
  - https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017
  - https://www.kaggle.com/datasets/yogeshm01/global-development-data-19602025
- Kaggle API and CLI: https://www.kaggle.com/docs/api and https://github.com/Kaggle/kaggle-cli
- World Bank data licenses: https://datacatalog.worldbank.org/public-licenses
- Azure Kubernetes Service: https://learn.microsoft.com/en-us/azure/aks/
- AKS workload identity: https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
- AKS application routing and the Gateway API transition: https://learn.microsoft.com/en-us/azure/aks/app-routing
- Azure Container Apps: https://learn.microsoft.com/en-us/azure/container-apps/
- Comparing Container Apps with other Azure container options: https://learn.microsoft.com/en-us/azure/container-apps/compare-options
- Container Apps managed identity: https://learn.microsoft.com/en-us/azure/container-apps/managed-identity
- Container Apps jobs: https://learn.microsoft.com/en-us/azure/container-apps/jobs
- Microsoft Foundry documentation: https://learn.microsoft.com/en-us/azure/foundry/
- Foundry Models sold directly by Azure, including GPT-6 capabilities: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure
- GPT-6 Astra, Sol, and Luna in Foundry, with pricing (September 2026): https://azure.microsoft.com/en-us/blog/gpt-6-astra-sol-and-luna-for-production-agents-in-microsoft-foundry/
- Foundry deployment types: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types
- Foundry quotas and limits: https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits
- Deploy a Foundry resource with Bicep: https://learn.microsoft.com/en-us/azure/foundry/how-to/create-resource-template
- Foundry project resource reference: https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/accounts/projects
- Foundry role-based access control: https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry
- Azure OpenAI pricing: https://azure.microsoft.com/en-us/pricing/details/azure-openai/
- Azure resource naming rules: https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/resource-name-rules
- Container Apps IP ingress restrictions: https://learn.microsoft.com/en-us/azure/container-apps/ip-restrictions
- Microsoft Agent Framework: https://learn.microsoft.com/en-us/agent-framework/overview/
- Azure Monitor OpenTelemetry: https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable
- GitHub Copilot app: https://docs.github.com/en/copilot/concepts/agents/github-copilot-app
- GitHub Copilot in VS Code: https://code.visualstudio.com/docs/copilot/overview
- FastAPI: https://fastapi.tiangolo.com/

Start with Phase 0. Report the selected architecture, the compatibility record, the data profile, and any true blockers briefly, then implement and verify the project phase by phase. Keep the live demo centered on the question: **What can more than 150 years of international football tell us, and what does it take to ship those insights as an AI app on AKS and on ACA?**
