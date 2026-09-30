# Appendix: deeper topics and sources

Background for anyone who wants more than the livestream covered. The sources at the end are dated: they are the pages checked when this demo was built, and product behavior changes, so re-check them before relying on a detail.

## Design choices

### Why deterministic tools instead of letting the model compute

Numbers in an analytics app must be reproducible, reviewable, and tested. A model that writes its own arithmetic or SQL can be wrong without any visible sign, and a reviewer can't check its work live. Here the model's job is narrower: choose among nine typed, read-only tools and explain what they return. Every tool is covered by tests on synthetic data, and the grounding validator checks every number the model writes against the tool results. The model can be replaced, or unavailable, without changing any number on the page. See [METHODS.md](METHODS.md#grounding-and-evaluation).

### Why a direct tool-calling loop

The insights agent is about 320 lines in `demo/src/football_insights/agent/loop.py`. It calls the Responses API through the Foundry project's OpenAI-compatible client, runs the tools the model asks for, and repeats until the model answers. A direct loop makes the limits explicit and testable: at most 6 tool calls, 1,200 output tokens, and 45 seconds per answer, and no stored conversation state. The Microsoft Agent Framework was evaluated. It adds built-in tracing, but this app already traces every model and tool call, and the framework's documentation did not show a per-answer tool-call limit.

### Why DuckDB over Parquet instead of a database

The curated data is small (under 1 MB of Parquet per table), read-only between ingest runs, and identical for every replica. Loading it into DuckDB in memory at startup gives fast SQL with no database server to deploy, secure, or pay for. Versions are immutable and content-addressed, so rolling back data is as simple as pointing `ACTIVE.json` at an earlier version.

### Why ingest is content-addressed

The version name is a hash of the input files, the reviewed reference lists, the indicator shortlist, and the ingest code version. The same inputs always produce the same version with byte-identical files, on Windows, in the Linux image, on AKS, or on ACA. Two consequences:

- Both platforms can run the ingest job without coordinating: the second run finds its version already published and reuses it.
- A changed input never overwrites an existing version: it produces a new one.

### Keyless local development

Containers can't use the Azure CLI sign-in on your machine, and this app has no API-key path at all. `demo up -LiveModel` writes a short-lived access token from your own sign-in to a git-ignored file, which `insights` reads. The token is refreshed every 15 minutes, never printed, and deleted by `demo down`. Code that runs directly on your machine uses your sign-in through `DefaultAzureCredential`.

### Ingress on AKS: Gateway API

AKS's NGINX-based application routing add-on receives only critical security patches through November 2026, and AKS recommends the Gateway API going forward. New AKS Automatic clusters on Kubernetes 1.36 or later use the application routing Gateway API implementation (class `approuting-istio`) by default. This demo also enables it explicitly in Bicep, so its setup doesn't depend on a default.

### Restricting access by IP address

- **ACA.** Allow rules on the app's ingress (`ipSecurityRestrictions`), evaluated by the environment's ingress.
- **AKS.** An annotation on the Gateway's generated load balancer Service (`service.beta.kubernetes.io/azure-allowed-ip-ranges`), set through the Gateway's `spec.infrastructure.annotations`. The Azure cloud provider turns it into network security group rules that see the client's real address.

An in-cluster policy would see the load balancer's translated address instead, so it can't do this job.

### Observability choices

- **One Application Insights resource.** The app exports through the Azure Monitor OpenTelemetry distro, which authenticates with Microsoft Entra ID. The resource has local (key-based) authentication disabled.
- **Not the ACA managed OpenTelemetry agent.** It is in preview and requires local authentication on Application Insights, so it can't be keyless.
- **GenAI conventions.** Model and tool spans follow the OpenTelemetry generative AI semantic conventions (`gen_ai.*`), which are still marked as in development upstream; attribute names may change.
- **Sampling.** The demo sets sampling to 100% explicitly, because the distro's default is a rate-limited sampler.

### Model deployments

Both models are **Global Standard** deployments with pinned versions and `versionUpgradeOption: NoAutoUpgrade`, so a new model version can't arrive during an event. GPT-6 Astra is the higher-quality, higher-priced deployment (five times Sol's price per token); GPT-6 Sol is faster and cheaper. The serving deployment is one setting, chosen by the evaluation suite's rule (see [RUNBOOK.md](RUNBOOK.md), segment 7). Foundry content filters stay on for both. A filtered response is labeled on the page, and the evidence still renders.

### Upgrades during an event

AKS Automatic upgrades the cluster automatically (the stable channel, one minor version behind the latest) and keeps node images current. `demo/infra/aks.bicep` adds planned-maintenance windows that exclude the three days before `EVENT_DATE` and the day after it. The windows are best effort: AKS can still run urgent, critical maintenance inside excluded dates. ACA has no cluster to upgrade.

### Responsible framing

Questions 3, 4, 5, and 7 touch geopolitics and national development. The app describes patterns neutrally, treats World Bank indicators as context rather than explanation, and never ranks countries or peoples by worth. The model's instructions say so, evaluation cases check it (`frame-*` in `cases.yaml`), and each development-lens view reports its own crosswalk coverage.

## Common questions

- **Could this app use club data, like the Premier League?** The architecture would take it unchanged: a schema contract, a crosswalk, ingest tables, and new tools. The work is in the data. Match events and tracking data are needed for play styles or counterattacks, and they are usually commercial and licensed per use. Check the license before you build on any dataset, and keep the data out of your repository.
- **Could an open or self-hosted model replace GPT-6?** If it supports tool calling with strict schemas and structured output, yes. Deploy it, add it to `AI_ALLOWED_DEPLOYMENTS` and to `agent/pricing.py`, run `demo eval` against it, and switch. The grounding check protects the numbers whatever the model.
- **What does a question cost?** Each answer page shows its input and output tokens and an estimated cost, computed from the list prices in `agent/pricing.py`. KQL query 4 in `demo/observability/queries.kql` sums them per day, platform, and deployment.
- **Why are the numbers different from other football rankings?** The rating model here is a transparent Elo-style model with published parameters (start 1500, home advantage 100, match importance 20–60, a goal-margin multiplier). It is not FIFA's ranking or any official ranking, and its results depend on those parameters; the app shows them.

## Glossary

| Term | Meaning here |
| --- | --- |
| AKS Automatic | An AKS cluster mode in which Azure manages node pools, scaling, upgrades, and security defaults |
| ACA revision | An immutable snapshot of a container app's template; traffic can be split between revisions |
| HPA | The Kubernetes Horizontal Pod Autoscaler, which adds or removes pods based on metrics such as CPU |
| Workload identity | AKS pods get Microsoft Entra tokens for a managed identity by exchanging a Kubernetes service account token, with no secret |
| Evidence ID | A stable name for a number a tool returned, such as `q6.pooled.performance_diff`; the page shows it under the number |
| Grounding check | The deterministic test that every number in a narrative matches a number a tool returned |
| Wilson interval | A 95% confidence interval for a proportion that behaves well for small samples |
| Bootstrap interval | A 95% interval from 2,000 resamples of the data, with a fixed seed so results repeat |
| Crosswalk | The reviewed mapping from football team names to World Bank economies |

## Sources

Checked on the dates shown. "Page date" is the page's own last-updated date where it shows one.

### Session and data

| Source | Checked | Notes |
| --- | --- | --- |
| [Session page](https://developer.microsoft.com/en-us/reactor/events/27536/) | 2026-09-29 | |
| [International football results from 1872 to 2026](https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017) | 2026-09-29 | Version 137, updated 2026-08-26, CC0 |
| [Global Development Data (1960–2025)](https://www.kaggle.com/datasets/yogeshm01/global-development-data-19602025) | 2026-09-29 | Version 1, updated 2026-07-14, CC BY 4.0; the downloaded files are `WDICSV.csv`, `WDICountry_Cleaned.csv`, `WDISeries_Cleaned.csv`, and `Data_Dictionary.csv` |
| [World Bank data licenses](https://datacatalog.worldbank.org/public-licenses) | 2026-09-29 | CC BY 4.0, with attribution and an indication of changes |
| [Kaggle API documentation](https://github.com/Kaggle/kaggle-api/blob/main/docs/README.md) | 2026-09-29 | Kaggle CLI 2.2.4 can't request a dataset version; `kagglehub` can |

### Azure Kubernetes Service

| Source | Checked | Page date |
| --- | --- | --- |
| [What is AKS Automatic?](https://learn.microsoft.com/en-us/azure/aks/intro-aks-automatic) | 2026-09-30 | 2026-07-07 |
| [AKS Automatic quickstart](https://learn.microsoft.com/en-us/azure/aks/automatic/quick-automatic-managed-network) | 2026-09-30 | 2026-09-15 |
| [Application routing with the Gateway API](https://learn.microsoft.com/en-us/azure/aks/app-routing-gateway-api) | 2026-09-30 | 2026-08-31 |
| [Istio Gateway API: annotation and ConfigMap customizations](https://learn.microsoft.com/en-us/azure/aks/istio-gateway-api) | 2026-09-30 | 2025-08-21 |
| [Supported Kubernetes versions](https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions) | 2026-09-29 | 2026-09-15 |
| [Planned maintenance](https://learn.microsoft.com/en-us/azure/aks/planned-maintenance) | 2026-09-30 | 2025-12-19 |

### Azure Container Apps

| Source | Checked | Page date |
| --- | --- | --- |
| [Environments](https://learn.microsoft.com/en-us/azure/container-apps/environment) | 2026-09-29 | 2026-02-26 |
| [IP restrictions](https://learn.microsoft.com/en-us/azure/container-apps/ip-restrictions) | 2026-09-29 | 2026-03-19 |
| [Jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs) | 2026-09-29 | 2026-09-16 |
| [OpenTelemetry agents](https://learn.microsoft.com/en-us/azure/container-apps/opentelemetry-agents) | 2026-09-29 | 2026-03-31 |
| [Billing](https://learn.microsoft.com/en-us/azure/container-apps/billing) | 2026-09-30 | 2025-12-09 |

### Microsoft Foundry and SDKs

| Source | Checked | Page date |
| --- | --- | --- |
| [Foundry models sold directly by Azure](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure) | 2026-09-29 | 2026-09-21 |
| [Quotas and limits](https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits) | 2026-09-29 | 2026-08-20 |
| [Role-based access control for Foundry](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry) | 2026-09-29 | 2026-09-16 |
| [SDK overview](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview) | 2026-09-29 | 2026-08-05 |

### Telemetry and pricing

| Source | Checked | Notes |
| --- | --- | --- |
| [Microsoft Entra authentication for Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/azure-ad-authentication) | 2026-09-29 | |
| [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai) | 2026-09-29 | Status: Development |
| [Azure Retail Prices API](https://prices.azure.com/api/retail/prices) | 2026-09-29 and 2026-09-30 | List prices for `westus3` used in [AKS-VS-ACA.md](AKS-VS-ACA.md) |

### GitHub Copilot

| Source | Checked | Notes |
| --- | --- | --- |
| [GitHub Copilot app generally available](https://github.blog/changelog/2026-06-17-github-copilot-app-generally-available/) | 2026-09-29 | The Copilot moment was prepared with version 1.1.23 |
