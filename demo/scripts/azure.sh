#!/usr/bin/env bash
# Azure operator commands for the football insights demo. Source from demo.sh after _common.sh.
# Mirrors azure.ps1: pin subscription, derive deployment outputs in-process, and avoid printing secrets.
# Progress messages go to stderr so functions that return values (URLs, versions) stay clean.
# Each command signs in to the subscription and the cluster at most once per process.
SUBSCRIPTION_SET=0
AKS_CONNECTED=0

required_env() { local name="$1"; [[ -n "${!name:-}" ]] || { echo "Set $name in .env before running this Azure command." >&2; exit 1; }; printf '%s' "${!name}"; }
env_or_default() { local name="$1" default="$2"; if [[ -n "${!name:-}" ]]; then printf '%s' "${!name}"; else printf '%s' "$default"; fi; }
infra_path() { printf '%s/demo/infra/%s' "$ROOT" "$1"; }
deploy_dir() { mkdir -p "$ROOT/.local/deploy"; printf '%s/.local/deploy' "$ROOT"; }
evidence_dir() {
  local dir="$(env_or_default EVIDENCE_DIR .local/evidence)"
  [[ "$dir" = /* || "$dir" =~ ^[A-Za-z]: ]] || dir="$ROOT/$dir"
  mkdir -p "$dir"
  printf '%s' "$dir"
}
rollout_path() { printf '%s/rollout.json' "$(deploy_dir)"; }
az_checked() { echo "> az $*" >&2; az "$@"; }
kubectl_checked() { echo "> kubectl $*" >&2; kubectl "$@"; }
docker_checked() { echo "> docker $*" >&2; docker "$@"; }
set_demo_defaults() {
  [[ -n "${PROJECT_TAG:-}" ]] || export PROJECT_TAG=football-insights
  [[ -n "${AKS_KUBERNETES_VERSION:-}" ]] || export AKS_KUBERNETES_VERSION=1.36
  [[ -n "${AI_MODEL_DEPLOYMENT:-}" ]] || export AI_MODEL_DEPLOYMENT=gpt-6-astra
  [[ -n "${AI_ALLOWED_DEPLOYMENTS:-}" ]] || export AI_ALLOWED_DEPLOYMENTS=gpt-6-astra,gpt-6-sol
  [[ -n "${BUDGET_START_DATE:-}" ]] || export BUDGET_START_DATE="$(date +%Y-%m-01)"
  if [[ -z "${OPERATOR_PRINCIPAL_ID:-}" ]]; then
    OPERATOR_PRINCIPAL_ID="$(az ad signed-in-user show --query id -o tsv)" || { echo "Could not read your signed-in principal; run az login." >&2; exit 1; }
    export OPERATOR_PRINCIPAL_ID
  fi
}
set_demo_subscription() {
  local subscription account_name
  subscription="$(required_env AZURE_SUBSCRIPTION_ID)"
  [[ $SUBSCRIPTION_SET -eq 1 ]] && return 0
  az account set --subscription "$subscription" || { echo "az account set failed; run az login and check AZURE_SUBSCRIPTION_ID." >&2; exit 1; }
  account_name="$(az account show --query name -o tsv)"
  echo "Using subscription $account_name and resource group $(required_env AZURE_RESOURCE_GROUP)." >&2
  set_demo_defaults
  SUBSCRIPTION_SET=1
}
connect_aks() {
  [[ $AKS_CONNECTED -eq 1 ]] && return 0
  set_demo_subscription
  az_checked aks get-credentials --resource-group "$(required_env AZURE_RESOURCE_GROUP)" --name "$(required_env AKS_CLUSTER_NAME)" --overwrite-existing >&2
  # AKS Automatic uses Microsoft Entra ID; without this, kubectl prompts for a device-code sign-in.
  kubelogin convert-kubeconfig -l azurecli >&2
  AKS_CONNECTED=1
}
group_deployment() {
  local name="$1" template="$2" params="$3" rg
  rg="$(required_env AZURE_RESOURCE_GROUP)"
  echo "Deploying $name to resource group $rg."
  az_checked deployment group create --resource-group "$rg" --name "$name" --template-file "$(infra_path "$template")" --parameters "$(infra_path "$params")" --output none
}
deployment_outputs_json() {
  local name="$1" rg json
  rg="$(required_env AZURE_RESOURCE_GROUP)"
  json="$(az deployment group show --resource-group "$rg" --name "$name" --query properties.outputs -o json 2>/dev/null)" || { echo "Deployment $name not found in $rg; run its demo command first." >&2; exit 1; }
  [[ -n "$json" ]] || { echo "Deployment $name not found in $rg; run its demo command first." >&2; exit 1; }
  printf '%s' "$json"
}
output_value() {
  "$PYTHON" -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]]["value"])' "$1" "$2"
}
import_deployment_outputs() {
  local foundation platform
  foundation="$(deployment_outputs_json football-foundation)"
  platform="$(deployment_outputs_json football-platform)"
  export FOUNDRY_PROJECT_ENDPOINT="$(output_value "$foundation" foundryProjectEndpoint)"
  export APPLICATIONINSIGHTS_CONNECTION_STRING="$(output_value "$foundation" applicationInsightsConnectionString)"
  export ACR_LOGIN_SERVER="$(output_value "$platform" registryLoginServer)"
  STORAGE_ACCOUNT_URL="$(output_value "$platform" storageBlobEndpoint)"; export STORAGE_ACCOUNT_URL="${STORAGE_ACCOUNT_URL%/}"
  export AKS_WEB_CLIENT_ID="$(output_value "$platform" aksWebClientId)"
  export AKS_INSIGHTS_CLIENT_ID="$(output_value "$platform" aksInsightsClientId)"
  export AKS_INGEST_CLIENT_ID="$(output_value "$platform" aksIngestClientId)"
}
update_env_value() {
  local name="$1" value="$2" path="$ROOT/.env"
  touch "$path"
  if grep -qE "^[[:space:]]*${name}[[:space:]]*=" "$path"; then
    "$PYTHON" -c 'import re,sys
p,n,v=sys.argv[1:]
lines=open(p,encoding="utf-8").read().splitlines()
open(p,"w",encoding="utf-8").write("\n".join((f"{n}={v}" if re.match(rf"^\s*{re.escape(n)}\s*=", line) else line) for line in lines)+"\n")' "$path" "$name" "$value"
  else
    printf '%s=%s\n' "$name" "$value" >> "$path"
  fi
  export "$name=$value"
}
write_check() { local name="$1" ok="$2" detail="${3:-}"; if [[ "$ok" == true ]]; then echo "PASS: $name $detail"; else echo "FAIL: $name $detail"; fi; }
version_pin() { local name="$1" actual="$2" pin="${3:-}"; if [[ -n "$pin" ]]; then [[ "$actual" == "$pin"* ]] && write_check "$name" true "actual=$actual pinned=$pin" || write_check "$name" false "actual=$actual pinned=$pin"; else write_check "$name" true "$actual"; fi; }
ip_in_cidr() { "$PYTHON" -c 'import ipaddress,sys; print(str(ipaddress.ip_address(sys.argv[1]) in ipaddress.ip_network(sys.argv[2], False)).lower())' "$1" "$2"; }
azure_foundation() {
  set_demo_subscription
  local rg location exists
  rg="$(required_env AZURE_RESOURCE_GROUP)"; location="$(required_env AZURE_LOCATION)"
  exists="$(az group exists --name "$rg")"
  if [[ "$exists" != true ]]; then
    az_checked group create --name "$rg" --location "$location" --output none --tags "project=$PROJECT_TAG" "event-date=$(required_env EVENT_DATE)" "teardown-date=$(required_env TEARDOWN_DATE)"
  fi
  group_deployment football-foundation foundation.bicep foundation.bicepparam
  local foundation; foundation="$(deployment_outputs_json football-foundation)"
  echo "Foundation ready. Project endpoint: $(output_value "$foundation" foundryProjectEndpoint)"
}
azure_platform() {
  set_demo_subscription
  group_deployment football-platform platform.bicep platform.bicepparam
  echo "Platform ready: registry, storage, and six workload identities with least-privilege roles."
}
upload_data() {
  set_demo_subscription
  local account source folder
  account="$(required_env STORAGE_ACCOUNT_NAME)"; source="$(env_or_default FOOTBALL_DATA_DIR data)"
  [[ "$source" = /* || "$source" =~ ^[A-Za-z]: ]] || source="$ROOT/$source"
  for folder in football_stats global_development_data; do
    [[ -d "$source/$folder" ]] || { echo "Missing $source/$folder; see data/README.md." >&2; exit 1; }
    echo "Uploading $folder to $account/raw with your Entra sign-in (no keys)."
    az_checked storage blob upload-batch --auth-mode login --account-name "$account" --destination raw --destination-path "$folder" --source "$source/$folder" --pattern '*.csv' --overwrite true --output none
  done
}
image_tag() {
  if [[ -n "${IMAGE_TAG:-}" ]]; then printf '%s' "$IMAGE_TAG"; elif git -C "$ROOT" rev-parse --short HEAD >/dev/null 2>&1; then git -C "$ROOT" rev-parse --short HEAD; else printf '%s' local; fi
}
build_push() {
  local output="${1:-}" file_name acr tag target remote digest out
  set_demo_subscription
  import_deployment_outputs
  acr="$(required_env ACR_NAME)"; tag="$(image_tag)"
  az_checked acr login --name "$acr"
  if [[ "$output" == v2 ]]; then file_name=digests-v2.json; elif [[ -z "$output" ]]; then file_name=digests.json; else echo "Use --output v2 or omit --output." >&2; exit 1; fi
  out="$(deploy_dir)/$file_name"
  printf '{
  "tag": "%s",
  "registry": "%s"' "$tag" "$ACR_LOGIN_SERVER" > "$out"
  for target in web insights ingest; do
    remote="${ACR_LOGIN_SERVER}/football-insights-${target}:${tag}"
    docker_checked build -f "$ROOT/demo/docker/Dockerfile" --target "$target" -t "$remote" "$ROOT/demo"
    docker_checked push "$remote"
    digest="$(docker buildx imagetools inspect "$remote" --format '{{json .Manifest.Digest}}' | tr -d '"')"
    [[ -n "$digest" ]] || { echo "Could not resolve the digest of $remote" >&2; exit 1; }
    printf ',
  "%s": "%s"' "$target" "$digest" >> "$out"
  done
  printf '
}
' >> "$out"
  echo "Pushed tag $tag; digests recorded in $out (both platforms deploy these exact digests)."
}
import_digests() {
  local output="${1:-}" file_name path
  if [[ "$output" == v2 ]]; then file_name=digests-v2.json; else file_name=digests.json; fi
  path="$(deploy_dir)/$file_name"
  [[ -f "$path" ]] || { echo "Run demo build-push first; $file_name is missing." >&2; exit 1; }
  WEB_IMAGE_DIGEST="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["web"])' "$path")"
  INSIGHTS_IMAGE_DIGEST="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["insights"])' "$path")"
  INGEST_IMAGE_DIGEST="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["ingest"])' "$path")"
  export WEB_IMAGE_DIGEST INSIGHTS_IMAGE_DIGEST INGEST_IMAGE_DIGEST
}
render_template() {
  local source="$1" dest="$2"
  "$PYTHON" -c 'import os,re,sys
s=open(sys.argv[1],encoding="utf-8").read()
def repl(m):
    n=m.group(1)
    if n not in os.environ:
        raise SystemExit(f"Missing {n} for manifest substitution.")
    return os.environ[n]
open(sys.argv[2],"w",encoding="utf-8").write(re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", repl, s))' "$source" "$dest"
}
aks_apply() {
  local manifest attempt; manifest="$(deploy_dir)/aks-rendered.yaml"
  render_template "$ROOT/demo/k8s/football.yaml" "$manifest"
  # Right after a cluster create or update, the API server's authorization webhook can time out for a few
  # minutes. apply is idempotent, so retry it.
  for attempt in 1 2 3 4; do
    echo "> kubectl apply -f $manifest" >&2
    kubectl apply -f "$manifest" && return 0
    [[ $attempt -lt 4 ]] || { echo "kubectl apply failed after $attempt attempts." >&2; exit 1; }
    echo "kubectl apply failed (attempt $attempt of 4); retrying in 30 seconds." >&2
    sleep 30
  done
}
wait_aks_ingest_job() {
  # kubectl wait can't wait for "complete or failed", and a failed Job never completes.
  local deadline states
  deadline=$(( $(date +%s) + 1800 ))
  while (( $(date +%s) < deadline )); do
    states="$(kubectl -n football get job ingest -o json | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print(" ".join(c["type"] for c in d.get("status",{}).get("conditions",[]) if c.get("status")=="True"))')" || { echo "Could not read the AKS ingest Job status." >&2; exit 1; }
    [[ " $states " == *" Complete "* ]] && return 0
    if [[ " $states " == *" Failed "* ]]; then
      kubectl -n football logs job/ingest --tail=40 >&2 || true
      echo "The AKS ingest Job failed; its last log lines are above." >&2; exit 1
    fi
    sleep 10
  done
  echo "The AKS ingest Job did not finish within 30 minutes." >&2; exit 1
}
aks_ingest_job() {
  local manifest; manifest="$(deploy_dir)/aks-ingest-rendered.yaml"
  render_template "$ROOT/demo/k8s/ingest-job.yaml" "$manifest"
  kubectl_checked -n football delete job ingest --ignore-not-found=true
  kubectl_checked apply -f "$manifest"
  wait_aks_ingest_job
  kubectl_checked -n football logs job/ingest
}
aks_deploy() {
  set_demo_subscription
  # AKS Automatic's deployment safeguards need this provider; without it the cluster ends up Failed after ~10 minutes.
  [[ "$(az provider show --namespace Microsoft.PolicyInsights --query registrationState -o tsv)" == Registered ]] || { echo "AKS Automatic needs the Microsoft.PolicyInsights resource provider. Register it once per subscription (free), then rerun: az provider register --namespace Microsoft.PolicyInsights --wait" >&2; exit 1; }
  import_deployment_outputs; import_digests
  group_deployment football-aks aks.bicep aks.bicepparam
  connect_aks
  aks_apply
  aks_ingest_job
  kubectl_checked -n football rollout status deployment/insights --timeout=10m
  kubectl_checked -n football rollout status deployment/web --timeout=10m
  echo "AKS web: $(get_aks_web_url)"
}
ingest_aks() { set_demo_subscription; import_deployment_outputs; import_digests; connect_aks; aks_ingest_job; }
get_aks_web_url() {
  if [[ -n "${AKS_WEB_URL:-}" ]]; then printf '%s' "$AKS_WEB_URL"; return; fi
  connect_aks
  local address
  address="$(kubectl -n football get gateway football-web -o jsonpath='{.status.addresses[0].value}' 2>/dev/null)" || { echo "The AKS gateway has no address yet; check kubectl -n football get gateway." >&2; exit 1; }
  [[ -n "$address" ]] || { echo "The AKS gateway has no address yet; check kubectl -n football get gateway." >&2; exit 1; }
  printf 'http://%s' "$address"
}
container_image() { kubectl -n football get deploy "$1" -o jsonpath='{.spec.template.spec.containers[0].image}'; }
start_aca_ingest_job() {
  local rg job execution deadline status
  rg="$(required_env AZURE_RESOURCE_GROUP)"; job="$(required_env ACA_INGEST_JOB_NAME)"
  execution="$(az containerapp job start --resource-group "$rg" --name "$job" --query name -o tsv)" || { echo "Failed to start the ACA ingest job." >&2; exit 1; }
  [[ -n "$execution" ]] || { echo "Failed to start the ACA ingest job." >&2; exit 1; }
  echo "Started ACA job execution $execution."
  deadline=$((SECONDS + 1800))
  while true; do
    sleep 10
    status="$(az containerapp job execution show --resource-group "$rg" --name "$job" --job-execution-name "$execution" --query properties.status -o tsv)" || { echo "Failed to read ACA ingest job status." >&2; exit 1; }
    echo "  status: $status"
    if [[ "$status" != Running && "$status" != Processing && -n "$status" ]]; then break; fi
    (( SECONDS < deadline )) || break
  done
  [[ "$status" == Succeeded ]] || { echo "ACA ingest job ended with status '$status'." >&2; exit 1; }
  echo "ACA ingest job succeeded; logs reach Log Analytics (ContainerAppConsoleLogs) within minutes."
}
ingest_aca() { set_demo_subscription; start_aca_ingest_job; }
aca_deploy() {
  set_demo_subscription; import_deployment_outputs; import_digests
  local old="${ACA_DEPLOY_APPS:-__unset__}"
  export ACA_DEPLOY_APPS=false
  group_deployment football-aca aca.bicep aca.bicepparam
  start_aca_ingest_job
  export ACA_DEPLOY_APPS=true
  group_deployment football-aca aca.bicep aca.bicepparam
  if [[ "$old" == __unset__ ]]; then unset ACA_DEPLOY_APPS; else export ACA_DEPLOY_APPS="$old"; fi
  aca_retire_idle_revisions >/dev/null
  echo "ACA web: $(get_aca_web_url)"
}
aca_retire_idle_revisions() {
  # web runs in multiple-revision mode for the v2 traffic split, so earlier revisions keep running at 0% traffic,
  # each holding a replica. Deactivate them; they stay in the revision history and can be reactivated.
  local rg web revisions rev count=0
  rg="$(required_env AZURE_RESOURCE_GROUP)"; web="$(required_env ACA_WEB_APP_NAME)"
  revisions="$(az containerapp revision list --resource-group "$rg" --name "$web" -o json)" || { echo "Could not list ACA web revisions." >&2; exit 1; }
  for rev in $("$PYTHON" -c 'import json,sys; [print(r["name"]) for r in json.loads(sys.argv[1]) if r["properties"].get("active") and not r["properties"].get("trafficWeight")]' "$revisions"); do
    az_checked containerapp revision deactivate --resource-group "$rg" --name "$web" --revision "$rev" --output none >&2
    echo "Deactivated idle ACA web revision $rev." >&2
    count=$((count + 1))
  done
  printf '%s' "$count"
}
get_aca_web_url() {
  if [[ -n "${ACA_WEB_URL:-}" ]]; then printf '%s' "$ACA_WEB_URL"; return; fi
  local fqdn
  fqdn="$(az containerapp show --resource-group "$(required_env AZURE_RESOURCE_GROUP)" --name "$(required_env ACA_WEB_APP_NAME)" --query properties.configuration.ingress.fqdn -o tsv)" || { echo "The ACA web app has no ingress address yet." >&2; exit 1; }
  [[ -n "$fqdn" ]] || { echo "The ACA web app has no ingress address yet." >&2; exit 1; }
  printf 'https://%s' "$fqdn"
}
platform_url() {
  case "$1" in aks) get_aks_web_url ;; aca) get_aca_web_url ;; *) echo "Unknown platform $1" >&2; exit 1 ;; esac
}
test_endpoint() {
  local name="$1" base="${2%/}" path code body_file expected version web_digest_short
  local hint='A 403 or a timeout usually means the platform saw a source address outside ALLOWED_CIDRS; a VPN or secure access client can route Azure traffic through another address. See "Restrict access to your IP" in docs/DEPLOYMENT.md.'
  body_file="$(deploy_dir)/smoke-${name}.html"
  for path in /healthz /readyz /data; do
    code="$(curl -sS --max-time 20 -o "$body_file" -w '%{http_code}' "${base}${path}" || true)"
    [[ "$code" == 200 ]] || { echo "$name $path returned ${code:-no response}" >&2; [[ "$code" == 403 || "$code" == 000 || -z "$code" ]] && echo "$hint" >&2; exit 1; }
  done
  curl -sS -o "$body_file" "$base/"
  web_digest_short="${WEB_IMAGE_DIGEST#sha256:}"; web_digest_short="${web_digest_short:0:12}"
  expected="image $web_digest_short"
  grep -Fq "$expected" "$body_file" || { echo "$name badge does not show the pushed web digest ($expected)." >&2; exit 1; }
  version="$("$PYTHON" -c 'import re,sys; s=open(sys.argv[1],encoding="utf-8").read(); m=re.search(r"data (cv-[0-9a-f]{12})", s); print(m.group(1) if m else "")' "$body_file")"
  echo "$name: healthy; badge shows $expected and data $version" >&2
  printf '%s' "$version"
}
snapshot() {
  # Replay artifacts for the fallback tiers: every card view and the prepared answers, openable offline.
  local platform="${1:-both}" targets target url
  [[ "$platform" =~ ^(aks|aca|both|local)$ ]] || { echo "Usage: demo snapshot [aks|aca|both|local]" >&2; exit 1; }
  [[ "$platform" == both ]] && targets="aks aca" || targets="$platform"
  for target in $targets; do
    if [[ "$target" == local ]]; then url="http://127.0.0.1:8080"; else url="$(platform_url "$target")"; fi
    "$PYTHON" -m football_insights snapshot --url "$url" --label "$target"
  done
}
parity() {
  local aks aca stamp out
  aks="$(platform_url aks)"; aca="$(platform_url aca)"; stamp="$(date -u +%Y%m%dT%H%M%SZ)"; out="$(evidence_dir)/parity-${stamp}.json"
  "$PYTHON" -m football_insights parity --url "$aks" --url "$aca" | tee "$out"
}
test_insights_isolation() {
  connect_aks
  local svc_type lbs fqdn code
  svc_type="$(kubectl -n football get svc insights -o jsonpath='{.spec.type}')" || { echo "AKS insights service check failed." >&2; exit 1; }
  [[ "$svc_type" == ClusterIP ]] || { echo "AKS insights service is $svc_type, expected ClusterIP." >&2; exit 1; }
  lbs="$(kubectl -n football get svc -o json | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print(",".join(i["metadata"]["name"] for i in d["items"] if i["spec"].get("type")=="LoadBalancer" and not any(x in i["metadata"]["name"] for x in ["gateway","istio","football-web"])))')"
  [[ -z "$lbs" ]] || { echo "Unexpected AKS LoadBalancer services: $lbs" >&2; exit 1; }
  echo "AKS insights isolation: PASS (ClusterIP; no unexpected LoadBalancer services)."
  fqdn="$(az containerapp show --resource-group "$(required_env AZURE_RESOURCE_GROUP)" --name "$(required_env ACA_INSIGHTS_APP_NAME)" --query properties.configuration.ingress.fqdn -o tsv)" || { echo "Could not read ACA insights ingress FQDN." >&2; exit 1; }
  [[ "$fqdn" == *.internal.* ]] || { echo "ACA insights FQDN is not internal: $fqdn" >&2; exit 1; }
  # The internal name resolves to the environment's public address, and ACA answers outside callers with 404.
  code="$(curl -k -sS -o /dev/null -m 10 -w '%{http_code}' "https://${fqdn}/healthz" 2>/dev/null || true)"
  [[ "$code" != 200 ]] || { echo "ACA insights /healthz was reachable from this machine; expected 404 or no connection." >&2; exit 1; }
  echo "ACA insights isolation: PASS (internal ingress; this machine got HTTP ${code:-000}, 000 meaning no connection)."
}
smoke() {
  set_demo_subscription; connect_aks; import_digests
  local aks_version aca_version
  aks_version="$(test_endpoint AKS "$(platform_url aks)")"
  aca_version="$(test_endpoint ACA "$(platform_url aca)")"
  [[ "$aks_version" == "$aca_version" ]] || { echo "Curated data versions differ: AKS $aks_version vs ACA $aca_version." >&2; exit 1; }
  parity
  test_insights_isolation
  echo "smoke OK: health, digests, data version, parity, and private insights isolation passed."
}
aca_replica_count() {
  # Replicas of the revisions that receive traffic; `replica list` without --revision shows only the latest one.
  local app="$1" rg revisions rev n total=0
  rg="$(required_env AZURE_RESOURCE_GROUP)"
  revisions="$(az containerapp revision list --resource-group "$rg" --name "$app" -o json)"
  for rev in $("$PYTHON" -c 'import json,sys; [print(r["name"]) for r in json.loads(sys.argv[1]) if r["properties"].get("active") and r["properties"].get("trafficWeight")]' "$revisions"); do
    n="$(az containerapp replica list --resource-group "$rg" --name "$app" --revision "$rev" -o json | "$PYTHON" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
    total=$((total + n))
  done
  printf '%s' "$total"
}
load_test() {  local platform="${1:-both}" rps="${2:-20}" seconds="${3:-60}" targets target url stamp out app local_override
  [[ "$platform" == aks || "$platform" == aca || "$platform" == both ]] || { echo "Usage: demo load-test [aks|aca|both] [-Rps N] [-Seconds N]" >&2; exit 1; }
  [[ "$rps" =~ ^[0-9]+$ && "$seconds" =~ ^[0-9]+$ && "$rps" -gt 0 && "$seconds" -gt 0 ]] || { echo "Rps and Seconds must be positive." >&2; exit 1; }
  [[ "$platform" == both ]] && targets="aks aca" || targets="$platform"
  for target in $targets; do
    [[ "$target" == aks ]] && connect_aks
    url="$(platform_url "$target")"; local_override=0; [[ "$url" =~ ^https?://(127\.0\.0\.1|localhost)(:|/|$) ]] && local_override=1
    if [[ $local_override -eq 1 ]]; then echo "Local URL override detected; skipping platform replica observations."; elif [[ "$target" == aks ]]; then kubectl -n football get hpa,pods; else
      for app in "$(required_env ACA_WEB_APP_NAME)" "$(required_env ACA_INSIGHTS_APP_NAME)"; do echo "$app replicas before: $(aca_replica_count "$app")"; done
    fi
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"; out="$(evidence_dir)/loadtest-${target}-${stamp}.json"
    echo "Load testing $target at $url ($rps rps for $seconds s)."
    "$PYTHON" -m football_insights load-test --url "$url" --rps "$rps" --seconds "$seconds" | tee "$out"
    if [[ $local_override -eq 1 ]]; then echo "Local URL override detected; skipped platform replica observations."; elif [[ "$target" == aks ]]; then kubectl -n football get hpa,pods; else
      for app in "$(required_env ACA_WEB_APP_NAME)" "$(required_env ACA_INSIGHTS_APP_NAME)"; do echo "$app replicas after: $(aca_replica_count "$app")"; done
    fi
    echo "Saved $out"
  done
}
set_aks_image() {
  # One change for the image and the digest the badge reports, so the badge always names the running image.
  local deployment="$1" image="$2" digest="$3" patch
  patch="$("$PYTHON" -c 'import json,sys; print(json.dumps({"spec":{"template":{"spec":{"containers":[{"name":sys.argv[1],"image":sys.argv[2],"env":[{"name":"IMAGE_DIGEST","value":sys.argv[3]}]}]}}}}))' "$deployment" "$image" "$digest")"
  kubectl_checked -n football patch deployment "$deployment" --type strategic -p "$patch"
}
rollout_v2() {
  set_demo_subscription; import_deployment_outputs; import_digests v2; connect_aks
  local rg web insights current new_web suffix tag registry web_digest insights_digest
  tag="$("$PYTHON" -c 'import json; print(json.load(open(".local/deploy/digests-v2.json"))["tag"])')"
  registry="$("$PYTHON" -c 'import json; print(json.load(open(".local/deploy/digests-v2.json"))["registry"])')"
  web_digest="$WEB_IMAGE_DIGEST"; insights_digest="$INSIGHTS_IMAGE_DIGEST"
  suffix="v2-$(date -u +%m%d%H%M)"
  echo "Rolling out tag $tag with revision suffix $suffix."
  rg="$(required_env AZURE_RESOURCE_GROUP)"; web="$(required_env ACA_WEB_APP_NAME)"; insights="$(required_env ACA_INSIGHTS_APP_NAME)"
  current="$(az containerapp revision list --resource-group "$rg" --name "$web" --query '[?properties.active].name | [0]' -o tsv)" || { echo "Could not determine current ACA web revision." >&2; exit 1; }
  [[ -n "$current" ]] || { echo "Could not determine current ACA web revision." >&2; exit 1; }
  az_checked containerapp ingress traffic set --resource-group "$rg" --name "$web" --revision-weight "$current=100" --output none
  az_checked containerapp update --resource-group "$rg" --name "$web" --image "${registry}/football-insights-web@${web_digest}" --set-env-vars "IMAGE_DIGEST=${web_digest}" --revision-suffix "$suffix" --output none
  new_web="$(az containerapp revision list --resource-group "$rg" --name "$web" --query "[?ends_with(name, '$suffix')].name | [0]" -o tsv)"
  [[ -n "$new_web" ]] || { echo "Could not determine new ACA web revision." >&2; exit 1; }
  az_checked containerapp ingress traffic set --resource-group "$rg" --name "$web" --revision-weight "$current=50" "$new_web=50" --output none
  az_checked containerapp update --resource-group "$rg" --name "$insights" --image "${registry}/football-insights-insights@${insights_digest}" --set-env-vars "IMAGE_DIGEST=${insights_digest}" --revision-suffix "$suffix" --output none
  "$PYTHON" -c 'import json,sys; json.dump({"aca_web_previous":sys.argv[1],"aca_web_v2":sys.argv[2],"suffix":sys.argv[3]}, open(sys.argv[4],"w"), indent=2)' "$current" "$new_web" "$suffix" "$(rollout_path)"
  set_aks_image web "${registry}/football-insights-web@${web_digest}" "$web_digest"
  set_aks_image insights "${registry}/football-insights-insights@${insights_digest}" "$insights_digest"
  kubectl_checked -n football rollout status deployment/web --timeout=10m
  kubectl_checked -n football rollout status deployment/insights --timeout=10m
  echo "ACA web traffic:"; az containerapp ingress traffic show --resource-group "$rg" --name "$web" -o table
  echo "AKS images:"; kubectl -n football get deploy web insights -o wide
}
rollback() {
  local platform="${1:-both}" rg web insights registry rollout previous v1_web v1_insights current
  [[ "$platform" == aks || "$platform" == aca || "$platform" == both ]] || { echo "Usage: demo rollback [aks|aca|both]" >&2; exit 1; }
  set_demo_subscription; import_deployment_outputs; import_digests
  registry="$("$PYTHON" -c 'import json; print(json.load(open(".local/deploy/digests.json"))["registry"])')"
  v1_web="${registry}/football-insights-web@${WEB_IMAGE_DIGEST}"; v1_insights="${registry}/football-insights-insights@${INSIGHTS_IMAGE_DIGEST}"
  rg="$(required_env AZURE_RESOURCE_GROUP)"; web="$(required_env ACA_WEB_APP_NAME)"
  if [[ "$platform" == aca || "$platform" == both ]]; then
    insights="$(required_env ACA_INSIGHTS_APP_NAME)"; rollout="$(rollout_path)"
    if [[ -f "$rollout" ]]; then
      # The previous revision is still running, so this is only a traffic change and takes effect at once.
      previous="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["aca_web_previous"])' "$rollout")"
      az_checked containerapp ingress traffic set --resource-group "$rg" --name "$web" --revision-weight "$previous=100" --output none
      rm -f "$rollout"
    else echo "No v2 rollout recorded for ACA web; its traffic is unchanged."; fi
    current="$(az containerapp show --resource-group "$rg" --name "$insights" --query 'properties.template.containers[0].image' -o tsv)"
    if [[ "$current" != "$v1_insights" ]]; then az_checked containerapp update --resource-group "$rg" --name "$insights" --image "$v1_insights" --set-env-vars "IMAGE_DIGEST=${INSIGHTS_IMAGE_DIGEST}" --output none
    else echo "ACA insights already runs the v1 image."; fi
    echo "ACA web traffic:"; az containerapp ingress traffic show --resource-group "$rg" --name "$web" -o table
  fi
  if [[ "$platform" == aks || "$platform" == both ]]; then
    # An explicit rolling update back to the v1 digests; `kubectl rollout undo` would revert whatever changed
    # last, which may be a model switch rather than the image.
    connect_aks
    [[ "$(container_image web)" == "$v1_web" ]] && echo "AKS web already runs the v1 image." || set_aks_image web "$v1_web" "$WEB_IMAGE_DIGEST"
    [[ "$(container_image insights)" == "$v1_insights" ]] && echo "AKS insights already runs the v1 image." || set_aks_image insights "$v1_insights" "$INSIGHTS_IMAGE_DIGEST"
    kubectl_checked -n football rollout status deployment/web --timeout=10m
    kubectl_checked -n football rollout status deployment/insights --timeout=10m
    echo "AKS images:"; kubectl -n football get deploy web insights -o wide
  fi
}
switch_model() {
  local deployment="${1:-}" allowed
  [[ -n "$deployment" ]] || { echo "Usage: demo switch-model <deployment>" >&2; exit 1; }
  allowed=",$(env_or_default AI_ALLOWED_DEPLOYMENTS gpt-6-astra,gpt-6-sol),"; [[ "$allowed" == *",${deployment},"* ]] || { echo "Deployment $deployment is not in AI_ALLOWED_DEPLOYMENTS." >&2; exit 1; }
  set_demo_subscription; connect_aks; update_env_value AI_MODEL_DEPLOYMENT "$deployment"
  az_checked containerapp update --resource-group "$(required_env AZURE_RESOURCE_GROUP)" --name "$(required_env ACA_INSIGHTS_APP_NAME)" --set-env-vars "AI_MODEL_DEPLOYMENT=$deployment" --output none
  kubectl_checked -n football set env deployment/insights "AI_MODEL_DEPLOYMENT=$deployment"
  kubectl_checked -n football rollout status deployment/insights --timeout=5m
  echo "Both platforms now serve answers with $deployment (configuration only; no rebuild)."
}
allow_ip() {
  set_demo_subscription
  local cidr cidrs=() joined rg app cluster rules patch names=() i
  # Explicit addresses win: a VPN or secure access client can route Azure traffic through an address that
  # IP-echo sites never see. Without arguments, allow the address api.ipify.org reports.
  if [[ $# -gt 0 ]]; then
    IFS=',' read -ra cidrs <<< "$(IFS=','; echo "$*")"
  else
    cidrs=("$(curl -sS --max-time 10 https://api.ipify.org)")
  fi
  local cleaned=()
  for cidr in "${cidrs[@]}"; do
    cidr="${cidr// /}"; [[ -z "$cidr" ]] && continue; [[ "$cidr" == */* ]] || cidr="${cidr}/32"
    [[ "$cidr" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$ ]] || { echo "Not an IPv4 address or CIDR: $cidr" >&2; exit 1; }
    cleaned+=("$cidr")
  done
  [[ ${#cleaned[@]} -gt 0 ]] || { echo "No address to allow." >&2; exit 1; }
  joined="$(IFS=','; echo "${cleaned[*]}")"
  update_env_value ALLOWED_CIDRS "$joined"
  rg="$(required_env AZURE_RESOURCE_GROUP)"; app="$(required_env ACA_WEB_APP_NAME)"; cluster="$(required_env AKS_CLUSTER_NAME)"
  # Update whichever platforms are deployed; a team may deploy only one.
  if [[ -n "$(az containerapp show --resource-group "$rg" --name "$app" --query name -o tsv 2>/dev/null || true)" ]]; then
    # Add the new rules before removing old ones: an app with no rules at all accepts every address.
    for i in "${!cleaned[@]}"; do
      names+=("allow-$i")
      az_checked containerapp ingress access-restriction set --resource-group "$rg" --name "$app" --rule-name "allow-$i" --ip-address "${cleaned[$i]}" --action Allow --output none
    done
    rules="$(az containerapp ingress access-restriction list --resource-group "$rg" --name "$app" -o json 2>/dev/null || echo '[]')"
    "$PYTHON" -c 'import json,sys; keep=set(sys.argv[2].split(",")); [print(r.get("name","")) for r in json.loads(sys.argv[1]) if r.get("name") not in keep]' "$rules" "$(IFS=','; echo "${names[*]}")" | while IFS= read -r rule; do [[ -n "$rule" ]] && az_checked containerapp ingress access-restriction remove --resource-group "$rg" --name "$app" --rule-name "$rule" --output none; done
    echo "ACA web now accepts only $joined."
  else echo "ACA web app $app not found; skipped."; fi
  if [[ -n "$(az aks show --resource-group "$rg" --name "$cluster" --query name -o tsv 2>/dev/null || true)" ]]; then
    connect_aks
    patch="$("$PYTHON" -c 'import json,sys; print(json.dumps({"spec":{"infrastructure":{"annotations":{"service.beta.kubernetes.io/azure-allowed-ip-ranges":sys.argv[1]}}}}))' "$joined")"
    kubectl_checked -n football patch gateway football-web --type merge -p "$patch"
    echo "AKS web now accepts only $joined."
  else echo "AKS cluster $cluster not found; skipped."; fi
}
trace_cmd() {
  local id="${1:-}" query
  [[ -n "$id" ]] || { echo "Usage: demo trace <id>" >&2; exit 1; }
  echo "AKS trace: $(platform_url aks)/trace/$id"
  echo "ACA trace: $(platform_url aca)/trace/$id"
  query="$("$PYTHON" -c 'import re,sys; s=open(sys.argv[1],encoding="utf-8").read(); m=re.search(r"// 1\..*?(?=// 2\.)", s, re.S); print(m.group(0).replace("<trace id>", sys.argv[2]).strip())' "$ROOT/demo/observability/queries.kql" "$id")"
  printf '\nKQL query:\n%s\n' "$query"
}
preflight() {
  local ok=0 deployments d actual expiry ip allowed contains cidr min_exp github_exe copilot_version kaggle
  if ( set_demo_subscription ); then set_demo_subscription; write_check "az signed in and subscription pinned" true; else write_check "az signed in and subscription pinned" false; ok=1; fi
  expiry="$(az account get-access-token --query expiresOn -o tsv 2>/dev/null || true)"
  if [[ -n "$expiry" ]]; then "$PYTHON" -c 'from datetime import datetime,timedelta; import sys; e=datetime.fromisoformat(sys.argv[1].replace("Z","+00:00")).replace(tzinfo=None); sys.exit(0 if e>datetime.utcnow()+timedelta(minutes=30) else 1)' "$expiry" && write_check "Azure CLI token valid >30m" true "expires=$expiry" || { write_check "Azure CLI token valid >30m" false "expires=$expiry"; ok=1; }; else write_check "Azure CLI token valid >30m" false; ok=1; fi
  IFS=',' read -ra deployments <<< "$(env_or_default AI_ALLOWED_DEPLOYMENTS gpt-6-astra,gpt-6-sol)"
  for d in "${deployments[@]}"; do d="${d// /}"; [[ -z "$d" ]] && continue; actual="$(az cognitiveservices account deployment show --resource-group "$(required_env AZURE_RESOURCE_GROUP)" --name "$(required_env FOUNDRY_RESOURCE_NAME)" --deployment-name "$d" --query '{version:properties.model.version, upgrade:properties.versionUpgradeOption}' -o tsv 2>/dev/null || true)"; [[ "$actual" == *NoAutoUpgrade* ]] && write_check "Foundry $d pinned" true "$actual" || { write_check "Foundry $d pinned" false "$actual"; ok=1; }; done
  if ( connect_aks && kubectl -n football get deploy ); then AKS_CONNECTED=1; write_check "kubectl reaches cluster" true; else write_check "kubectl reaches cluster" false; ok=1; fi
  if ( import_digests && test_endpoint AKS "$(platform_url aks)" >/dev/null && test_endpoint ACA "$(platform_url aca)" >/dev/null ); then write_check "web endpoints healthy with recorded digest" true "(demo smoke runs the full check)"; else write_check "web endpoints healthy with recorded digest" false; ok=1; fi
  ip="$(curl -sS --max-time 10 https://api.ipify.org || true)"; allowed="$(env_or_default ALLOWED_CIDRS '')"; contains=false; IFS=',' read -ra cidrs <<< "$allowed"; for cidr in "${cidrs[@]}"; do [[ "$(ip_in_cidr "$ip" "${cidr// /}")" == true ]] && contains=true; done; [[ "$contains" == true ]] && write_check "public IP inside ALLOWED_CIDRS" true "$ip" || { write_check "public IP inside ALLOWED_CIDRS" false "$ip"; ok=1; }
  docker info >/dev/null 2>&1 && write_check "Docker Desktop running" true || { write_check "Docker Desktop running" false; ok=1; }
  if [[ -f "$TOKEN_FILE" ]]; then min_exp="$("$PYTHON" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(min(int(v["expires_on"]) for v in d.values()))' "$TOKEN_FILE" 2>/dev/null || echo 0)"; [[ "$min_exp" -gt $(($(date +%s)+600)) ]] && write_check "local token file not near expiry" true || { write_check "local token file not near expiry" false; ok=1; }; else write_check "local token file absent" true; fi
  [[ -f "$HOME/.kaggle/kaggle.json" || -n "${KAGGLE_API_TOKEN:-}" ]] && kaggle=true || kaggle=false; echo "INFO: Kaggle credential present: $kaggle"
  version_pin "az version" "$(az version --query '"azure-cli"' -o tsv)" "${PINNED_AZ:-}" || ok=1
  version_pin "kubectl version" "$(kubectl version --client=true -o json | "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["clientVersion"]["gitVersion"])')" "${PINNED_KUBECTL:-}" || ok=1
  version_pin "docker version" "$(docker version --format '{{.Client.Version}}')" "${PINNED_DOCKER:-}" || ok=1
  github_exe="${LOCALAPPDATA:-}/Programs/GitHub Copilot/github.exe"; if [[ -f "$github_exe" ]]; then copilot_version="$(powershell.exe -NoProfile -Command "(Get-Item '$github_exe').VersionInfo.ProductVersion" 2>/dev/null | tr -d '\r')"; version_pin "GitHub Copilot app" "$copilot_version" "${PINNED_COPILOT_APP:-}"; else write_check "GitHub Copilot app" false "github.exe not found"; ok=1; fi
  [[ $ok -eq 0 ]] || exit 1
}
reset_demo() {
  set_demo_subscription; import_deployment_outputs; import_digests; connect_aks
  local changed=() registry v1_web v1_insights needs=false default_model retired joined
  registry="$("$PYTHON" -c 'import json; print(json.load(open(".local/deploy/digests.json"))["registry"])')"; v1_web="${registry}/football-insights-web@${WEB_IMAGE_DIGEST}"; v1_insights="${registry}/football-insights-insights@${INSIGHTS_IMAGE_DIGEST}"
  [[ -f "$(rollout_path)" ]] && needs=true
  [[ "$(container_image web)" != "$v1_web" || "$(container_image insights)" != "$v1_insights" ]] && needs=true
  [[ "$needs" == true ]] && { rollback; changed+=("rolled back v2 images/traffic to v1"); }
  retired="$(aca_retire_idle_revisions)"; [[ "$retired" -gt 0 ]] && changed+=("deactivated $retired idle ACA web revision(s)")
  default_model="$(env_or_default DEFAULT_MODEL_DEPLOYMENT gpt-6-astra)"; if [[ "$(env_or_default AI_MODEL_DEPLOYMENT gpt-6-astra)" != "$default_model" ]]; then switch_model "$default_model"; changed+=("model reset to $default_model"); fi
  if [[ ${#changed[@]} -eq 0 ]]; then echo "reset: no changes needed."; else joined="$(printf '%s; ' "${changed[@]}")"; echo "reset changed: ${joined%; }"; fi
}
teardown() {
  local dry=0 rg project node_rg confirm
  [[ "${1:-}" == "--dry-run" || "${1:-}" == "-DryRun" ]] && dry=1
  set_demo_subscription; rg="$(required_env AZURE_RESOURCE_GROUP)"; project="$(env_or_default PROJECT_TAG football-insights)"
  echo "Resources in $rg (project tag comparison: $project):"
  az resource list --resource-group "$rg" --query '[].{name:name,type:type,project:tags.project}' -o json | "$PYTHON" -c 'import json,sys,os; p=os.environ.get("PROJECT_TAG","football-insights");
for r in json.load(sys.stdin):
 print("{}\t{}\t{}".format(r.get("name"), r.get("type"), "tagged by this project" if r.get("project")==p else "not tagged by this project - confirm before deleting"))'
  node_rg="$(az aks show --resource-group "$rg" --name "$(env_or_default AKS_CLUSTER_NAME '')" --query nodeResourceGroup -o tsv 2>/dev/null || true)"; [[ -n "$node_rg" ]] && echo "AKS node resource group: $node_rg (deleted with the cluster)."
  [[ $dry -eq 1 ]] && { echo "Dry run only: nothing was deleted."; return; }
  read -r -p "Delete the whole resource group '$rg'? Type its name to confirm: " confirm; [[ "$confirm" == "$rg" ]] || { echo "Confirmation did not match; nothing was deleted." >&2; exit 1; }
  az_checked group delete --name "$rg" --yes --no-wait; echo "Deletion of $rg started."
}
