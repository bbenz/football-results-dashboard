# Azure deployment guide

> **Verified against Azure on 2026-09-30** in `westus3`. Both platforms were deployed with these commands into an empty resource group, and a second run of the whole sequence changed nothing but the new image digests. The rollout, rollback, reset, ingest, trace, allow-list, and teardown dry-run commands ran in both PowerShell and Bash. Problems found along the way are fixed in the templates and scripts; the ones you might still meet are under [Troubleshooting](#troubleshooting).

This guide deploys the same football insights images to AKS Automatic and Azure Container Apps (ACA) with Microsoft Foundry, Azure Storage, Container Registry, workspace-based Application Insights, and keyless Microsoft Entra authentication.

## Prerequisites

- PowerShell 7 or Git Bash, Docker Desktop, Azure CLI with Bicep, `kubectl`, `kubelogin`, and access to an Azure subscription.
- Register the `Microsoft.PolicyInsights` resource provider once per subscription: `az provider register --namespace Microsoft.PolicyInsights --wait`. AKS Automatic's deployment safeguards use Azure Policy, and a Bicep deployment only registers the providers of the resources it declares ([resource providers](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/resource-providers-and-types), 2026-02-27). Registering is free. `aks-deploy` stops early if the provider isn't registered.
- Copy `.env.example` to `.env` and fill in presenter-specific values there, not in tracked files.
- Required operator values: `AZURE_SUBSCRIPTION_ID`, `AZURE_LOCATION`, `AZURE_RESOURCE_GROUP`, `EVENT_DATE`, `TEARDOWN_DATE`, `FOUNDRY_RESOURCE_NAME`, `FOUNDRY_PROJECT_NAME`, `LOG_ANALYTICS_NAME`, `APPINSIGHTS_NAME`, `ACR_NAME`, `STORAGE_ACCOUNT_NAME`, `AKS_CLUSTER_NAME`, `ACA_ENVIRONMENT_NAME`, `ACA_WEB_APP_NAME`, `ACA_INSIGHTS_APP_NAME`, `ACA_INGEST_JOB_NAME`, six identity names, `ALLOWED_CIDRS`, `BUDGET_AMOUNT`, `BUDGET_CONTACT_EMAIL`, and the data location if not `data/`.
- Defaults set by the scripts if omitted: `PROJECT_TAG=football-insights`, `AKS_KUBERNETES_VERSION=1.36`, `AI_MODEL_DEPLOYMENT=gpt-6-astra`, `DEFAULT_MODEL_DEPLOYMENT=gpt-6-astra`, `AI_ALLOWED_DEPLOYMENTS=gpt-6-astra,gpt-6-sol`, `BUDGET_START_DATE` as the first day of the current month, and `OPERATOR_PRINCIPAL_ID` from `az ad signed-in-user show`.
- Derived values are read from deployment outputs or `.local/deploy/digests*.json` at run time and are not written to `.env`: Foundry endpoint, App Insights connection string, ACR login server, storage URL, AKS workload identity client IDs, and image digests.

## PowerShell sequence

```powershell
./demo/scripts/demo.ps1 azure-foundation
./demo/scripts/demo.ps1 azure-platform
./demo/scripts/demo.ps1 upload-data
./demo/scripts/demo.ps1 build-push
./demo/scripts/demo.ps1 aks-deploy
./demo/scripts/demo.ps1 aca-deploy
./demo/scripts/demo.ps1 smoke
```

## Bash sequence

```bash
./demo/scripts/demo.sh azure-foundation
./demo/scripts/demo.sh azure-platform
./demo/scripts/demo.sh upload-data
./demo/scripts/demo.sh build-push
./demo/scripts/demo.sh aks-deploy
./demo/scripts/demo.sh aca-deploy
./demo/scripts/demo.sh smoke
```

## What each step does

- Every Azure command pins `AZURE_SUBSCRIPTION_ID` first.
- `azure-foundation`: creates the tagged resource group if needed, then deploys Foundry, pinned model deployments, Log Analytics, App Insights with local auth disabled, budget alerts, and operator data-plane roles.
- `azure-platform`: deploys ACR, storage containers, six per-service user-assigned identities, and least-privilege role assignments.
- `upload-data`: uploads only CSVs from `football_stats` and `global_development_data` under `raw/<folder>/` using Entra auth.
- `build-push`: builds each image with its registry tag and records `{tag, registry, web, insights, ingest}` in `.local/deploy/digests.json`. Use `build-push -Output v2` (bash: `--output v2`) after setting `IMAGE_TAG` to record `.local/deploy/digests-v2.json`.
- `aks-deploy`: deploys AKS Automatic, including explicit app-routing Gateway API configuration, the operator's **Azure Kubernetes Service RBAC Cluster Admin** role, and planned-maintenance windows that keep automatic cluster and node-image upgrades out of the three days before `EVENT_DATE` and the day after it. It first checks that `Microsoft.PolicyInsights` is registered. It then gets credentials, runs `kubelogin convert-kubeconfig -l azurecli`, and applies `football.yaml`, retrying for up to two minutes if the API server is still settling after a cluster change. It deletes and re-creates the separate ingest Job from `ingest-job.yaml`, waits for the job and stops as soon as it fails, prints its logs, and waits for the `insights` and `web` rollouts.
- `aca-deploy`: runs in two passes so ACA works standalone. First it sets `ACA_DEPLOY_APPS=false` and deploys only the environment and ingest job, starts the ingest job and waits for success, then sets `ACA_DEPLOY_APPS=true` and deploys web and insights. Finally it deactivates earlier web revisions that receive no traffic.
- `ingest-aks` and `ingest-aca`: run each platform's ingest job again. On the same raw files, both reuse the same curated version with the same checksums.
- `smoke`: checks both public web endpoints (`/healthz`, `/readyz`, `/data`), verifies badges show the recorded web digest, verifies the same data version, runs parity, and checks insights isolation.

`smoke`, `parity`, `trace`, `rollout-v2`, `rollback`, and `reset` expect both platforms. If you deploy only one, use the platform-specific commands (`load-test aca`, `ingest-aca`, and so on).

## Identity and isolation

ACA pulls images with each app's user-assigned identity and sets `AZURE_CLIENT_ID` for Azure SDKs. AKS uses Microsoft Entra Workload ID; the scripts derive service account client IDs from deployment outputs. AKS access also requires the operator cluster-admin Azure RBAC assignment from `aks.bicep`, and each kubectl-using command reconnects and converts kubeconfig with kubelogin so a fresh terminal does not hang on device-code auth.

Insights is private on both platforms. AKS keeps `insights` as `ClusterIP` and smoke fails if unexpected namespace Services are `LoadBalancer`. ACA uses an internal ingress FQDN for insights; its name resolves to the environment's public address, ACA answers outside callers with 404, and smoke fails if an external `/healthz` request succeeds.

## Restrict access to your IP

```powershell
./demo/scripts/demo.ps1 allow-ip
```

```bash
./demo/scripts/demo.sh allow-ip
```

The command detects your public IP, writes `ALLOWED_CIDRS=<ip>/32` to `.env`, sets ACA access restrictions `allow-0` onward (adding the new rules before removing old ones, because an app with no rules accepts every address), and patches only the AKS Gateway infrastructure annotation `service.beta.kubernetes.io/azure-allowed-ip-ranges`. It updates whichever platforms are deployed, and it does not re-apply the full AKS app manifest, so image and model rollout state is preserved. Set `ALLOWED_CIDRS` in `.env` before the first deployment; use `allow-ip` when your address changes.

To allow specific addresses instead, pass them, comma-separated; a bare address means `/32`:

```powershell
./demo/scripts/demo.ps1 allow-ip 203.0.113.7,198.51.100.0/28
```

```bash
./demo/scripts/demo.sh allow-ip 203.0.113.7,198.51.100.0/28
```

**If you use a VPN or a secure access client.** It can route traffic for Azure addresses through a different egress address than the one IP-echo websites see, so the detected address is wrong. ACA then answers `403` with `RBAC: access denied`, and the AKS gateway times out. To find the address Azure sees, check the client IP that Azure Resource Manager recorded for your own recent changes:

```powershell
az monitor activity-log list --offset 1h --caller (az account show --query user.name -o tsv) --query "[?httpRequest.clientIpAddress!=null].httpRequest.clientIpAddress" -o tsv
```

Pass those addresses to `allow-ip`, or ask your network administrator which egress addresses your client uses. A shared egress address also admits everyone else who uses it.

## Additional operator commands

### Run local Compose from pushed registry images

```powershell
./demo/scripts/demo.ps1 up -FromRegistry
```

```bash
./demo/scripts/demo.sh up --from-registry
```

### Load test and parity

```powershell
./demo/scripts/demo.ps1 load-test both -Rps 20 -Seconds 60
./demo/scripts/demo.ps1 parity
```

```bash
./demo/scripts/demo.sh load-test both --rps 20 --seconds 60
./demo/scripts/demo.sh parity
```

Load-test summaries and parity reports are saved under `EVIDENCE_DIR` (default `.local/evidence`). AKS load tests print HPA/pod state before and after; ACA load tests print the web and insights replicas of the revisions that receive traffic.

### Roll out v2 and rollback

```powershell
$env:IMAGE_TAG = '<v2-tag>'
./demo/scripts/demo.ps1 build-push -Output v2
./demo/scripts/demo.ps1 rollout-v2
./demo/scripts/demo.ps1 rollback
```

```bash
IMAGE_TAG=<v2-tag> ./demo/scripts/demo.sh build-push --output v2
./demo/scripts/demo.sh rollout-v2
./demo/scripts/demo.sh rollback
```

`rollout-v2` reads the tag and digests from `.local/deploy/digests-v2.json`. ACA web first pins 100% traffic to the current active revision, creates a uniquely suffixed v2 revision, then splits 50/50 and records `.local/deploy/rollout.json`. ACA insights switches fully because it is Single revision mode. AKS patches web and insights, changing each image and its `IMAGE_DIGEST` together so the badge always names the running image, and waits for the rollouts. On ACA, the same variable changes with the image in each new revision. `rollback` takes `aks`, `aca`, or `both` (the default). On ACA it moves 100% of web traffic back to the previous revision, which is still running, so the change is immediate, and returns insights to the v1 digest. On AKS it sets the images, and the digests the badges report, back to v1 with a rolling update (not `rollout undo`, which would revert whatever changed last, such as a model switch). `reset` and `aca-deploy` also deactivate ACA web revisions that no longer receive traffic, because each one keeps a replica running; they stay in the revision history.

### Save pages for offline fallback

```powershell
./demo/scripts/demo.ps1 snapshot both
```

```bash
./demo/scripts/demo.sh snapshot both
```

`snapshot` takes `aks`, `aca`, `both`, or `local`. It saves every view of every insight card, the Data page, and the answers to the prepared livestream questions as self-contained HTML under `EVIDENCE_DIR/replay/`. Each page carries a banner with its source and capture time, so a saved page is never mistaken for the live app. Run it after a successful rehearsal; open `index.html` from the folder to check that the pages work offline.

### Trace, preflight, reset

```powershell
./demo/scripts/demo.ps1 trace <trace-id>
./demo/scripts/demo.ps1 preflight
./demo/scripts/demo.ps1 reset
```

```bash
./demo/scripts/demo.sh trace <trace-id>
./demo/scripts/demo.sh preflight
./demo/scripts/demo.sh reset
```

`trace` prints AKS/ACA trace URLs and the first KQL query with the ID filled in. `preflight` is a read-only checklist that finishes in under a minute: Azure sign-in, CLI token lifetime, Foundry deployment pinning from `AI_ALLOWED_DEPLOYMENTS`, kubectl reachability, both web endpoints healthy with the recorded digest (`smoke` is the full check), current IP in `ALLOWED_CIDRS`, Docker Desktop, optional token file expiry, Kaggle credential presence (without reading it), and optional `PINNED_*` tool versions. `reset` never deletes resources: it rolls back only when v2 is recorded or AKS images are not v1, then switches back to `DEFAULT_MODEL_DEPLOYMENT` if needed.

## Switch the model

```powershell
./demo/scripts/demo.ps1 switch-model gpt-6-sol
```

```bash
./demo/scripts/demo.sh switch-model gpt-6-sol
```

The command updates the ACA insights app and AKS insights deployment, then waits for the AKS rollout. It does not rebuild images.

## Cost

At demo scale, both platforms together cost roughly $8–13 a day before monitoring ingestion and model tokens. Most of that is the AKS Automatic control plane and its node; ACA alone costs under $3 a day, and less when idle. [AKS-VS-ACA.md](AKS-VS-ACA.md#estimated-daily-cost-at-demo-scale) has the dated list prices behind these estimates.

Model tokens are billed per answer, and each answer page shows its tokens and estimated cost. `azure-foundation` creates a monthly budget of `BUDGET_AMOUNT` US dollars on the resource group. It emails `BUDGET_CONTACT_EMAIL` at 50%, 80%, and 100% of actual spend and at 100% of forecast spend. Tear everything down when you're done.

## Teardown

Preview everything in the resource group first:

```powershell
./demo/scripts/demo.ps1 teardown -DryRun
```

```bash
./demo/scripts/demo.sh teardown --dry-run
```

Dry run lists every resource in the resource group, shows whether it carries `project=<PROJECT_TAG>`, flags untagged resources for confirmation, and lists the AKS node resource group when available. Application Insights adds a "Failure Anomalies" alert rule of its own, without the tag, so dry run flags it; it goes with the resource group. Without dry run, the script deletes the whole resource group only after you type its name; the AKS node resource group goes with the cluster.

## Troubleshooting

- **kubectl prompts for device-code login or hangs:** run any kubectl-based demo command again; it calls `kubelogin convert-kubeconfig -l azurecli` after `az aks get-credentials`.
- **ACA revision suffix conflict:** run `rollout-v2` again; it generates a unique `v2-<MMddHHmm>` suffix per run.
- **AKS ingest job pod template is immutable:** use `ingest-aks` or `aks-deploy`; they delete `job/ingest` before applying `demo/k8s/ingest-job.yaml`.
- **AKS cluster fails with `CreateDeploymentSafeguardsFailed`:** the subscription hasn't registered `Microsoft.PolicyInsights` (see [Prerequisites](#prerequisites)). Register it and run `aks-deploy` again; the redeployment repairs the cluster in place.
- **`403` with `RBAC: access denied` from ACA, or a timeout from the AKS gateway:** the platform saw a source address outside `ALLOWED_CIDRS`. See [Restrict access to your IP](#restrict-access-to-your-ip), including the note on VPNs and secure access clients.
- **Pods crash at startup with `web_port ... unable to parse string as an integer, input_value='tcp://...'`:** Kubernetes injected Service variables such as `WEB_PORT=tcp://<ip>:8080`. The manifests set `enableServiceLinks: false` on every pod to prevent this; keep it if you add Services or pods.
- **AKS warnings when applying manifests:** deployment safeguards (in warning mode on AKS Automatic) add anti-affinity and topology spread to the Deployments, and note that the ingest Job has no probes. A batch Job doesn't serve traffic, so it has no readiness or liveness probe. Right after a deployment, the autoscalers report `FailedGetResourceMetric` until the first CPU metrics arrive.
- **ACA job logs aren't in Log Analytics yet:** the environment sends logs through Azure Monitor diagnostic settings, keylessly, to the `ContainerAppConsoleLogs` and `ContainerAppSystemLogs` tables, which lag a few minutes. `az containerapp job logs show` streams them live.
- **A Foundry deployment fails with `RequestConflict`:** a Foundry resource accepts one change at a time. `foundation.bicep` creates the project first and then the model deployments one by one; rerun `azure-foundation` if a change made elsewhere at the same time collided with it.
