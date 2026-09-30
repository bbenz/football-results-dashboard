# AKS versus ACA: the same app on both

This app runs the same three container images, by digest, on Azure Kubernetes Service (AKS) and on Azure Container Apps (ACA), in the same region, against the same model deployment and the same curated data. This page compares what it took, with each value's date and how it was obtained, and ends with a guide for choosing a platform for your hackathon project.

**How to read the values.** *Counted* values come from the files in this repository. *Documented* values come from the linked Microsoft Learn pages or the public [Azure Retail Prices API](https://prices.azure.com/api/retail/prices), with the date checked. *Estimates* are labeled as estimates. Values that can only come from running both platforms side by side, such as scaling under load, rollout times, and actual cost, are marked **not yet measured**, with the method that will measure them.

## Keeping the comparison fair

| Held equal | How |
| --- | --- |
| Images | Both platforms deploy `<registry>/football-insights-<service>@<digest>` from the same `.local/deploy/digests.json`, and each badge shows the running digest. |
| Replica size | 0.5 vCPU and 1 GiB per replica on both (AKS requests equal limits). |
| Replica floors and ceilings | 1 to 5 replicas for `web` and `insights` on both. |
| Region, model, data | One region, one Foundry deployment, and one curated version in one storage account, shared by both. |
| Settings | A test (`demo/tests/test_configuration.py`) checks that each service gets the same settings on both platforms. |
| Results | `demo parity` compares the deterministic results of all seven insight cards from both endpoints. |

What differs is what each platform does natively: how it scales (CPU-based autoscaling on AKS, HTTP concurrency on ACA), how it rolls out (rolling update on AKS, revisions with traffic weights on ACA), and how it restricts and routes traffic.

## At a glance

| Topic | AKS (Automatic) | ACA (workload profiles, Consumption) | Source |
| --- | --- | --- | --- |
| What you manage | A Kubernetes cluster: Kubernetes objects, the Gateway, autoscalers, network policies, workload identity federation, and the upgrade schedule. AKS Automatic manages nodes, node repair, and upgrades. | An environment, two apps, and a job. No cluster, nodes, or Kubernetes versions. | Counted from `demo/infra` and `demo/k8s`, 2026-09-30 |
| Deployment definitions | **24 declarations in 529 lines**: 8 Azure resources in Bicep (183 lines, including parameters) plus 16 Kubernetes objects in YAML (346 lines) | **5 Azure resources in 309 lines** of Bicep, including parameters | Counted, 2026-09-30 |
| Shared by both | 23 resource declarations in 467 lines: Foundry and its model deployments (one declaration, repeated for each allowed deployment), Log Analytics, Application Insights, budget, registry, storage, six identities, and role assignments | same | Counted, 2026-09-30 |
| Identity setup per service | 5 steps, plus 2 cluster-wide | 4 steps | Counted; see [Identity](#identity) |
| Public ingress | Gateway API `Gateway` + `HTTPRoute` (application routing, class `approuting-istio`) on an Azure load balancer with a public IP | `ingress.external: true` on the app | Templates |
| TLS | Plain HTTP on the gateway's IP address in this demo. HTTPS needs a DNS name and a certificate, for example from Key Vault through application routing. | HTTPS on a generated `*.azurecontainerapps.io` name, with a managed certificate, by default | [AKS app routing Gateway API](https://learn.microsoft.com/en-us/azure/aks/app-routing-gateway-api) (2026-08-31); [ACA ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview); checked 2026-09-30 |
| Restricting who can connect | Gateway `spec.infrastructure.annotations` sets `service.beta.kubernetes.io/azure-allowed-ip-ranges` on the generated load balancer Service; the Azure cloud provider turns it into network security group rules | `ingress.ipSecurityRestrictions` allow rules on the app | [Istio Gateway API annotations](https://learn.microsoft.com/en-us/azure/aks/istio-gateway-api) (2025-08-21); [ACA IP restrictions](https://learn.microsoft.com/en-us/azure/container-apps/ip-restrictions) (2026-03-19) |
| What a blocked caller sees | The connection times out: the network security group drops the packets | HTTP `403` with `RBAC: access denied` | Tested 2026-09-30 from each platform's outbound address |
| The caller's address inside the app | Only with `externalTrafficPolicy: Local` on the gateway's Service, set through a ConfigMap that the Gateway references in `spec.infrastructure.parametersRef`. The default, `Cluster`, replaces it with node addresses, so per-caller rate limits would count per node. | The ingress appends it to `X-Forwarded-For` by default | [Istio Gateway API ConfigMap customizations](https://learn.microsoft.com/en-us/azure/aks/istio-gateway-api) (2025-08-21); tested 2026-09-30 |
| Service-to-service | `ClusterIP` Service; a Cilium network policy admits only `web` pods to `insights` | Internal ingress: reachable only by apps and jobs in the same environment; outside callers get 404 | Templates; [ACA environment networking](https://learn.microsoft.com/en-us/azure/container-apps/networking) |
| Isolation granularity | Per pod, by label | Per environment | Templates |
| Autoscaling | Horizontal Pod Autoscaler at 70% CPU; AKS Automatic adds nodes as needed | HTTP scale rule at 20 concurrent requests per replica | Templates |
| Rollout of v2 | Rolling update (`kubectl set image`); Kubernetes keeps the previous ReplicaSet | New revision at 0% traffic, then a 50/50 split between revisions | Templates and `demo rollout-v2` |
| Rollback | Another rolling update, back to the v1 digests | Move 100% of traffic back to the previous revision, which is still running | `demo rollback` |
| Batch job | Kubernetes `Job` (retry once, deleted an hour after it finishes); rerun by deleting and re-applying it, because its pod template is immutable | Container Apps job with a manual trigger (30-minute timeout, retry once); rerun with `az containerapp job start` | Templates |
| Job logs | `kubectl logs job/ingest` | Log Analytics (`ContainerAppConsoleLogs`), a few minutes behind | Scripts |
| App telemetry | OpenTelemetry to Application Insights, same code | same | `telemetry.py` |
| Platform telemetry | Managed Prometheus and Container insights, preconfigured by AKS Automatic | Environment logs to Log Analytics | [AKS Automatic](https://learn.microsoft.com/en-us/azure/aks/intro-aks-automatic) (2026-07-07) |
| Day-2 upgrades | Cluster auto-upgrade on the stable channel (N-1) and automatic node image upgrades; upgrades stop if deprecated Kubernetes APIs are in use. This demo sets planned maintenance windows that exclude the days around the event. | No platform versions to upgrade; you deploy new revisions of your apps | [AKS Automatic](https://learn.microsoft.com/en-us/azure/aks/intro-aks-automatic) (2026-07-07) |

## Deployment definitions

Counted from the repository on 2026-09-30. Lines include parameter files.

| | AKS | ACA |
| --- | --- | --- |
| Azure resources (Bicep) | 8: the cluster, the kubelet's registry pull role, your Kubernetes RBAC role, three federated identity credentials, two planned-maintenance configurations (`aks.bicep`, 183 lines) | 5: the environment, its diagnostic setting that sends logs to Log Analytics without a key, `web`, `insights`, and the ingest job (`aca.bicep`, 309 lines) |
| Kubernetes objects (YAML) | 16: a namespace, 3 service accounts, 2 Deployments, 2 Services, a Gateway and the ConfigMap that keeps callers' addresses, an HTTPRoute, 2 autoscalers, 2 network policies (`football.yaml`, 295 lines), and the ingest Job (`ingest-job.yaml`, 51 lines) | none |
| Total | 24 declarations, 529 lines | 5 declarations, 309 lines |

Both also use `foundation.bicep` and `platform.bicep`, which neither platform could do without.

## Identity

Both platforms use a user-assigned managed identity per service and Microsoft Entra tokens everywhere; no keys exist. The steps differ:

| Step | AKS (workload identity) | ACA (managed identity) |
| --- | --- | --- |
| 1 | Create a user-assigned identity | Create a user-assigned identity |
| 2 | Grant it only the roles it needs | Grant it only the roles it needs, plus AcrPull |
| 3 | Create a federated identity credential that trusts the cluster's OIDC issuer for `system:serviceaccount:football:<service>` | Attach the identity to the app or job |
| 4 | Create a service account annotated with the identity's client ID | Reference it in `registries[].identity` for image pulls, and set `AZURE_CLIENT_ID` |
| 5 | Label the pod `azure.workload.identity/use: "true"` and set its service account | |
| Once per cluster | Enable the OIDC issuer and workload identity (preconfigured on AKS Automatic); grant the kubelet identity AcrPull | |

## Measurements that need both platforms running

**Not yet measured.** Each row names the command that measures it. Results will replace this table, with the date.

| Measurement | Method |
| --- | --- |
| Scaling under the same load | `demo load-test both -Rps 20 -Seconds 60` against the deterministic pages only (never the model), recording requests, errors, p50/p95 latency, and replicas before and after on each platform |
| Rollout and rollback time | `demo rollout-v2` then `demo rollback`, timing each platform until all traffic is served by the target version |
| Time to ready from a new deployment | Time from `kubectl apply` or the Container Apps revision creation until the first successful `/readyz` |
| Ingest job duration | `demo ingest-aks` and `demo ingest-aca` on the same raw files, which must produce the same curated version and checksums |
| Time to first public URL from an empty resource group | `demo aks-deploy` versus `demo aca-deploy` wall-clock time, after the shared foundation and platform |
| Actual daily cost | Azure Cost Management for the resource group, per resource, over the event days |

Cold starts: both platforms keep at least one replica of each service running, so neither scales from zero during the livestream. Scale-to-zero is available on ACA and is off here to keep the comparison fair and the demo warm.

## Estimated daily cost at demo scale

**Estimates**, in USD per day, from list prices for `westus3` in the Azure Retail Prices API, queried 2026-09-30, before free grants, discounts, and taxes. The actual cost of the proof of concept will be measured.

| Item | AKS | ACA |
| --- | --- | --- |
| Platform fee | Automatic hosted control plane, $0.16/hour: **$3.84** | No environment fee for a Consumption-only environment ([billing](https://learn.microsoft.com/en-us/azure/container-apps/billing), 2025-12-09): **$0** |
| Compute for `web` and `insights` at one replica each | Node autoprovisioning chooses the VM. With one 2-vCPU general-purpose node (D2s_v5, $0.096/hour) plus the Automatic General Purpose meter ($0.007841/hour per vCPU): **about $2.68**; with a 4-vCPU node, about $5.36 | 2 replicas × 0.5 vCPU and 1 GiB: **$0.78** if idle all day, **$2.59** if active all day |
| Ingress | Standard load balancer, $0.025/hour ($0.60) plus the gateway's public IP, $0.005/hour ($0.12): **$0.72** | Included |
| Outbound NAT gateway | Not included in this estimate | Not applicable |
| Monitoring ingestion | Container insights and Prometheus volume: not yet measured | Environment log volume: not yet measured |
| **Estimated total** | **about $7.24 to $9.92**, plus NAT gateway and monitoring | **about $0.78 to $2.59**, plus monitoring |

ACA's monthly free grant per subscription (180,000 vCPU-seconds, 360,000 GiB-seconds, and 2 million requests) covers about two days of this configuration.

Shared by both platforms:

- Container Registry Basic: about $0.17 per day.
- Log Analytics and Application Insights: $2.30 per GB ingested; the volume will be measured.
- Storage: a few hundred MB, negligible.
- Model tokens: GPT-6 Astra costs $10 per million input tokens and $50 per million output tokens; GPT-6 Sol costs $2 and $10. The app reports tokens and the estimated cost of every answer; see [METHODS.md](METHODS.md#grounding-and-evaluation) for the evaluation results.

Tear everything down with `demo teardown` when you're done: see [DEPLOYMENT.md](DEPLOYMENT.md#teardown).

## Which should my hackathon team choose?

Both platforms ran the same images with the same identity model and the same telemetry, so the choice is about what your team wants to own. Based on what this repository needed:

**Start with ACA if** you want the shortest path from a container to an HTTPS URL, your team is new to Kubernetes, or your project is a few HTTP services plus a batch job.

- Here it took 4 resources and 297 lines, against 23 declarations and 501 lines on AKS.
- TLS, internal service discovery, revisions, and traffic splitting are built in.
- Per-second billing and scale-to-zero suit a project that sits idle between demos.

**Choose AKS if** you need Kubernetes itself, or want Kubernetes experience for production work later:

- Helm charts, operators, custom resources, or anything from the Kubernetes ecosystem.
- Per-pod network policies and fine-grained control of scheduling, node types, or GPUs.
- Gateway API features beyond simple routing.

AKS Automatic removes most node management, but you still write and maintain Kubernetes objects, and the cluster costs money even when idle.

**Either way,** keep one image for both, configure everything through environment variables, use managed identities instead of keys, and deploy by digest. Then switching platforms later is a deployment change, not a rewrite.
