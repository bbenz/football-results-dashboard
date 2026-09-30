# Azure operator commands for the football insights demo. Dot-sourced by demo.ps1 after _common.ps1.
# Commands pin AZURE_SUBSCRIPTION_ID, derive deployment outputs in-process, and never print secrets.
Set-StrictMode -Version Latest
# Each command signs in to the subscription and the cluster at most once per process.
$script:SubscriptionSet = $false
$script:AksConnected = $false

function Get-RequiredEnv([string]$Name) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { throw "Set $Name in .env before running this Azure command." }
    return $value
}
function Get-EnvOrDefault([string]$Name, [string]$Default) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}
function Invoke-AzChecked {
    Write-Host "> az $($args -join ' ')"
    & az @args
    if ($LASTEXITCODE -ne 0) { throw "az command failed ($LASTEXITCODE): az $($args -join ' ')" }
}
function Invoke-KubectlChecked {
    Write-Host "> kubectl $($args -join ' ')"
    & kubectl @args
    if ($LASTEXITCODE -ne 0) { throw "kubectl command failed ($LASTEXITCODE): kubectl $($args -join ' ')" }
}
function Invoke-DockerChecked {
    Write-Host "> docker $($args -join ' ')"
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "docker command failed ($LASTEXITCODE): docker $($args -join ' ')" }
}
function Get-InfraPath([string]$Name) { Join-Path $script:Root "demo/infra/$Name" }
function Get-DeployDir { New-Item -ItemType Directory -Force -Path (Join-Path $script:Root '.local/deploy') | Out-Null; Join-Path $script:Root '.local/deploy' }
function Set-DemoDefaults {
    # Values with safe defaults; the operator's own principal ID comes from the current sign-in.
    foreach ($pair in @(@('PROJECT_TAG', 'football-insights'), @('AKS_KUBERNETES_VERSION', '1.36'),
                        @('AI_MODEL_DEPLOYMENT', 'gpt-6-astra'), @('AI_ALLOWED_DEPLOYMENTS', 'gpt-6-astra,gpt-6-sol'),
                        @('BUDGET_START_DATE', (Get-Date -Day 1).ToString('yyyy-MM-dd')))) {
        if (-not [Environment]::GetEnvironmentVariable($pair[0])) { [Environment]::SetEnvironmentVariable($pair[0], $pair[1]) }
    }
    if (-not $env:OPERATOR_PRINCIPAL_ID) {
        $env:OPERATOR_PRINCIPAL_ID = (az ad signed-in-user show --query id -o tsv)
        if ($LASTEXITCODE -ne 0) { throw 'Could not read your signed-in principal; run az login.' }
    }
}

function Get-EvidenceDir {
    $dir = Get-EnvOrDefault 'EVIDENCE_DIR' '.local/evidence'
    if (-not [IO.Path]::IsPathRooted($dir)) { $dir = Join-Path $script:Root $dir }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-RolloutPath { Join-Path (Get-DeployDir) 'rollout.json' }
function Set-DemoSubscription {
    $subscription = Get-RequiredEnv 'AZURE_SUBSCRIPTION_ID'
    if ($script:SubscriptionSet) { return }
    & az account set --subscription $subscription
    if ($LASTEXITCODE -ne 0) { throw 'az account set failed; run az login and check AZURE_SUBSCRIPTION_ID.' }
    Write-Host "Using subscription $((az account show --query name -o tsv)) and resource group $(Get-RequiredEnv 'AZURE_RESOURCE_GROUP')."
    Set-DemoDefaults
    $script:SubscriptionSet = $true
}
function Connect-Aks {
    if ($script:AksConnected) { return }
    Set-DemoSubscription
    Invoke-AzChecked aks get-credentials --resource-group (Get-RequiredEnv 'AZURE_RESOURCE_GROUP') --name (Get-RequiredEnv 'AKS_CLUSTER_NAME') --overwrite-existing
    # AKS Automatic uses Microsoft Entra ID; without this, kubectl prompts for a device-code sign-in.
    Invoke-Checked kubelogin convert-kubeconfig -l azurecli
    $script:AksConnected = $true
}
function Invoke-GroupDeployment([string]$Name, [string]$Template, [string]$Params) {
    $rg = Get-RequiredEnv 'AZURE_RESOURCE_GROUP'
    Write-Host "Deploying $Name to resource group $rg."
    Invoke-AzChecked deployment group create --resource-group $rg --name $Name --template-file (Get-InfraPath $Template) `
        --parameters (Get-InfraPath $Params) --output none
}
function Get-DeploymentOutputs([string]$Name) {
    $rg = Get-RequiredEnv 'AZURE_RESOURCE_GROUP'
    $json = az deployment group show --resource-group $rg --name $Name --query properties.outputs -o json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $json) { throw "Deployment $Name not found in $rg; run its demo command first." }
    return $json | ConvertFrom-Json
}
function Import-DeploymentOutputs {
    # Derived values live only in this process; they are never written to .env or printed.
    $foundation = Get-DeploymentOutputs 'football-foundation'
    $platform = Get-DeploymentOutputs 'football-platform'
    $env:FOUNDRY_PROJECT_ENDPOINT = $foundation.foundryProjectEndpoint.value
    $env:APPLICATIONINSIGHTS_CONNECTION_STRING = $foundation.applicationInsightsConnectionString.value
    $env:ACR_LOGIN_SERVER = $platform.registryLoginServer.value
    $env:STORAGE_ACCOUNT_URL = $platform.storageBlobEndpoint.value.TrimEnd('/')
    $env:AKS_WEB_CLIENT_ID = $platform.aksWebClientId.value
    $env:AKS_INSIGHTS_CLIENT_ID = $platform.aksInsightsClientId.value
    $env:AKS_INGEST_CLIENT_ID = $platform.aksIngestClientId.value
}
function Update-DotEnvValue([string]$Name, [string]$Value) {
    $path = Join-Path $script:Root '.env'
    $lines = if (Test-Path $path) { @(Get-Content $path) } else { @() }
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$([regex]::Escape($Name))\s*=") { $lines[$i] = "$Name=$Value"; $found = $true }
    }
    if (-not $found) { $lines += "$Name=$Value" }
    Set-Content -Encoding utf8 -Path $path -Value $lines
    [Environment]::SetEnvironmentVariable($Name, $Value)
}
function Write-Check([string]$Name, [bool]$Ok, [string]$Detail = '') {
    Write-Host ("{0}: {1} {2}" -f ($(if ($Ok) { 'PASS' } else { 'FAIL' })), $Name, $Detail)
}
function Test-VersionPin([string]$Name, [string]$Actual, [string]$Pin) {
    if ($Pin) { Write-Check $Name ($Actual -like "$Pin*") "actual=$Actual pinned=$Pin" } else { Write-Check $Name $true $Actual }
}
function Test-IPv4InCidr([string]$Ip, [string]$Cidr) {
    try {
        $parts = $Cidr.Split('/')
        if ($parts.Count -ne 2) { return $false }
        $ipBytes = [Net.IPAddress]::Parse($Ip).GetAddressBytes(); [Array]::Reverse($ipBytes)
        $netBytes = [Net.IPAddress]::Parse($parts[0]).GetAddressBytes(); [Array]::Reverse($netBytes)
        $ipInt = [BitConverter]::ToUInt32($ipBytes, 0)
        $netInt = [BitConverter]::ToUInt32($netBytes, 0)
        $prefix = [int]$parts[1]
        $mask = if ($prefix -eq 0) { [uint32]0 } else { [uint32]([uint32]::MaxValue -shl (32 - $prefix)) }
        return (($ipInt -band $mask) -eq ($netInt -band $mask))
    } catch { return $false }
}
function Invoke-AzureFoundation {
    Set-DemoSubscription
    $rg = Get-RequiredEnv 'AZURE_RESOURCE_GROUP'
    $location = Get-RequiredEnv 'AZURE_LOCATION'
    if ((az group exists --name $rg) -ne 'true') {
        Invoke-AzChecked group create --name $rg --location $location --output none --tags "project=$env:PROJECT_TAG" `
            "event-date=$(Get-RequiredEnv 'EVENT_DATE')" "teardown-date=$(Get-RequiredEnv 'TEARDOWN_DATE')"
    }
    Invoke-GroupDeployment 'football-foundation' 'foundation.bicep' 'foundation.bicepparam'
    $outputs = Get-DeploymentOutputs 'football-foundation'
    Write-Host "Foundation ready. Project endpoint: $($outputs.foundryProjectEndpoint.value)"
}
function Invoke-AzurePlatform {
    Set-DemoSubscription
    Invoke-GroupDeployment 'football-platform' 'platform.bicep' 'platform.bicepparam'
    Write-Host 'Platform ready: registry, storage, and six workload identities with least-privilege roles.'
}
function Invoke-UploadData {
    Set-DemoSubscription
    $account = Get-RequiredEnv 'STORAGE_ACCOUNT_NAME'
    $source = Get-EnvOrDefault 'FOOTBALL_DATA_DIR' 'data'
    if (-not [IO.Path]::IsPathRooted($source)) { $source = Join-Path $script:Root $source }
    foreach ($folder in 'football_stats', 'global_development_data') {
        if (-not (Test-Path (Join-Path $source $folder))) { throw "Missing $source/$folder; see data/README.md." }
        Write-Host "Uploading $folder to $account/raw with your Entra sign-in (no keys)."
        Invoke-AzChecked storage blob upload-batch --auth-mode login --account-name $account --destination raw `
            --destination-path $folder --source (Join-Path $source $folder) --pattern '*.csv' --overwrite true --output none
    }
}
function Get-ImageTag {
    $tag = [Environment]::GetEnvironmentVariable('IMAGE_TAG')
    if (-not [string]::IsNullOrWhiteSpace($tag)) { return $tag }
    $short = (git -C $script:Root rev-parse --short HEAD 2>$null)
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($short)) { return $short.Trim() }
    return 'local'
}
function Invoke-BuildPush([string]$Output = '') {
    Set-DemoSubscription
    Import-DeploymentOutputs
    $acrName = Get-RequiredEnv 'ACR_NAME'
    $tag = Get-ImageTag
    Invoke-AzChecked acr login --name $acrName
    $digests = [ordered]@{ tag = $tag; registry = $env:ACR_LOGIN_SERVER }
    foreach ($target in 'web', 'insights', 'ingest') {
        $remote = "$($env:ACR_LOGIN_SERVER)/football-insights-${target}:${tag}"
        Invoke-DockerChecked build -f (Join-Path $script:Root 'demo/docker/Dockerfile') --target $target -t $remote (Join-Path $script:Root 'demo')
        Invoke-DockerChecked push $remote
        $digest = docker buildx imagetools inspect $remote --format '{{json .Manifest.Digest}}'
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($digest)) { throw "Could not resolve the digest of $remote" }
        $digests[$target] = ($digest | ConvertFrom-Json)
    }
    $fileName = if ($Output -eq 'v2') { 'digests-v2.json' } elseif ([string]::IsNullOrWhiteSpace($Output)) { 'digests.json' } else { throw 'Use -Output v2 or omit -Output.' }
    $out = Join-Path (Get-DeployDir) $fileName
    $digests | ConvertTo-Json | Set-Content -Encoding utf8 $out
    Write-Host "Pushed tag $tag; digests recorded in $out (both platforms deploy these exact digests)."
}
function Import-Digests([string]$Output = '') {
    $fileName = if ($Output -eq 'v2') { 'digests-v2.json' } else { 'digests.json' }
    $path = Join-Path (Get-DeployDir) $fileName
    if (-not (Test-Path $path)) { throw "Run demo build-push first; $fileName is missing." }
    $json = Get-Content $path -Raw | ConvertFrom-Json
    $env:WEB_IMAGE_DIGEST = $json.web
    $env:INSIGHTS_IMAGE_DIGEST = $json.insights
    $env:INGEST_IMAGE_DIGEST = $json.ingest
    return $json
}
function Convert-TemplateFile([string]$Source, [string]$Destination) {
    $text = Get-Content $Source -Raw
    $text = [regex]::Replace($text, '\$\{([A-Za-z_][A-Za-z0-9_]*)\}', {
        param($m)
        $value = [Environment]::GetEnvironmentVariable($m.Groups[1].Value)
        if ($null -eq $value) { throw "Missing $($m.Groups[1].Value) for manifest substitution." }
        $value
    })
    Set-Content -Encoding utf8 -Path $Destination -Value $text
}
function Invoke-AksApply {
    $manifest = Join-Path (Get-DeployDir) 'aks-rendered.yaml'
    Convert-TemplateFile (Join-Path $script:Root 'demo/k8s/football.yaml') $manifest
    Invoke-KubectlChecked apply -f $manifest
}
function Invoke-AksIngestJob {
    $manifest = Join-Path (Get-DeployDir) 'aks-ingest-rendered.yaml'
    Convert-TemplateFile (Join-Path $script:Root 'demo/k8s/ingest-job.yaml') $manifest
    Invoke-KubectlChecked -n football delete job ingest --ignore-not-found=true
    Invoke-KubectlChecked apply -f $manifest
    Invoke-KubectlChecked -n football wait --for=condition=complete job/ingest --timeout=30m
    Invoke-KubectlChecked -n football logs job/ingest
}
function Invoke-AksDeploy {
    Set-DemoSubscription
    Import-DeploymentOutputs
    [void](Import-Digests)
    Invoke-GroupDeployment 'football-aks' 'aks.bicep' 'aks.bicepparam'
    Connect-Aks
    Invoke-AksApply
    Invoke-AksIngestJob
    Invoke-KubectlChecked -n football rollout status deployment/insights --timeout=10m
    Invoke-KubectlChecked -n football rollout status deployment/web --timeout=10m
    Write-Host "AKS web: $(Get-AksWebUrl)"
}
function Invoke-IngestAks {
    Set-DemoSubscription
    Import-DeploymentOutputs
    [void](Import-Digests)
    Connect-Aks
    Invoke-AksIngestJob
}
function Get-AksWebUrl {
    if ($env:AKS_WEB_URL) { return $env:AKS_WEB_URL }
    Connect-Aks | Out-Null
    $address = kubectl -n football get gateway football-web -o jsonpath='{.status.addresses[0].value}' 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $address) { throw 'The AKS gateway has no address yet; check kubectl -n football get gateway.' }
    return "http://$address"
}
function Get-ContainerImage([string]$Deployment) { kubectl -n football get deploy $Deployment -o jsonpath='{.spec.template.spec.containers[0].image}' }
function Start-AcaIngestJob {
    $rg = Get-RequiredEnv 'AZURE_RESOURCE_GROUP'
    $job = Get-RequiredEnv 'ACA_INGEST_JOB_NAME'
    $execution = az containerapp job start --resource-group $rg --name $job --query name -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $execution) { throw 'Failed to start the ACA ingest job.' }
    Write-Host "Started ACA job execution $execution."
    $deadline = (Get-Date).AddMinutes(30)
    do {
        Start-Sleep -Seconds 10
        $status = az containerapp job execution show --resource-group $rg --name $job --job-execution-name $execution --query properties.status -o tsv
        if ($LASTEXITCODE -ne 0) { throw 'Failed to read ACA ingest job status.' }
        Write-Host "  status: $status"
    } while ($status -in @('Running', 'Processing', '') -and (Get-Date) -lt $deadline)
    if ($status -ne 'Succeeded') { throw "ACA ingest job ended with status '$status'." }
    Write-Host 'ACA ingest job succeeded; logs are in Log Analytics (ContainerAppConsoleLogs_CL).'
}
function Invoke-IngestAca {
    Set-DemoSubscription
    Start-AcaIngestJob
}
function Invoke-AcaDeploy {
    Set-DemoSubscription
    Import-DeploymentOutputs
    [void](Import-Digests)
    $old = $env:ACA_DEPLOY_APPS
    try {
        $env:ACA_DEPLOY_APPS = 'false'
        Invoke-GroupDeployment 'football-aca' 'aca.bicep' 'aca.bicepparam'
        Start-AcaIngestJob
        $env:ACA_DEPLOY_APPS = 'true'
        Invoke-GroupDeployment 'football-aca' 'aca.bicep' 'aca.bicepparam'
    } finally {
        if ($null -eq $old) { Remove-Item Env:ACA_DEPLOY_APPS -ErrorAction SilentlyContinue } else { $env:ACA_DEPLOY_APPS = $old }
    }
    Write-Host "ACA web: $(Get-AcaWebUrl)"
}
function Get-AcaWebUrl {
    if ($env:ACA_WEB_URL) { return $env:ACA_WEB_URL }
    $fqdn = az containerapp show --resource-group (Get-RequiredEnv 'AZURE_RESOURCE_GROUP') --name (Get-RequiredEnv 'ACA_WEB_APP_NAME') --query properties.configuration.ingress.fqdn -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $fqdn) { throw 'The ACA web app has no ingress address yet.' }
    return "https://$fqdn"
}
function Get-PlatformUrl([string]$Platform) {
    if ($Platform -eq 'aks') { return Get-AksWebUrl }
    if ($Platform -eq 'aca') { return Get-AcaWebUrl }
    throw "Unknown platform $Platform"
}
function Test-Endpoint([string]$Name, [string]$BaseUrl, $Digests) {
    foreach ($path in '/healthz', '/readyz', '/data') {
        $response = Invoke-WebRequest -Uri ($BaseUrl.TrimEnd('/') + $path) -TimeoutSec 20 -SkipHttpErrorCheck
        if ($response.StatusCode -ne 200) { throw "$Name $path returned $($response.StatusCode)" }
    }
    $page = (Invoke-WebRequest -Uri $BaseUrl -TimeoutSec 30).Content
    $expected = "image $($Digests.web.Split(':')[1].Substring(0, 12))"
    if ($page -notmatch [regex]::Escape($expected)) { throw "$Name badge does not show the pushed web digest ($expected)." }
    $version = [regex]::Match($page, 'data (cv-[0-9a-f]{12})').Groups[1].Value
    Write-Host ("{0}: healthy; badge shows {1} and data {2}" -f $Name, $expected, $version)
    return $version
}
function Invoke-Snapshot([string]$Platform = 'both') {
    # Replay artifacts for the fallback tiers: every card view and the prepared answers, openable offline.
    if ($Platform -notin @('aks', 'aca', 'both', 'local')) { throw 'Usage: demo snapshot [aks|aca|both|local]' }
    $targets = if ($Platform -eq 'both') { @('aks', 'aca') } else { @($Platform) }
    foreach ($target in $targets) {
        $url = if ($target -eq 'local') { 'http://127.0.0.1:8080' } else { Get-PlatformUrl $target }
        Invoke-Checked $script:Python -m football_insights snapshot --url $url --label $target
    }
}
function Invoke-Parity {
    $aks = Get-PlatformUrl 'aks'
    $aca = Get-PlatformUrl 'aca'
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $out = Join-Path (Get-EvidenceDir) "parity-$stamp.json"
    & $script:Python -m football_insights parity --url $aks --url $aca | Tee-Object -FilePath $out | Out-Host
    $exit = $LASTEXITCODE
    if ($exit -ne 0) { throw "parity failed ($exit); report saved to $out" }
    Write-Host "parity OK: $out"
}
function Test-InsightsIsolation {
    Connect-Aks
    $svcType = kubectl -n football get svc insights -o jsonpath='{.spec.type}'
    if ($LASTEXITCODE -ne 0 -or $svcType -ne 'ClusterIP') { throw "AKS insights service is $svcType, expected ClusterIP." }
    $loadBalancers = kubectl -n football get svc -o json | ConvertFrom-Json
    $unexpected = @($loadBalancers.items | Where-Object { $_.spec.type -eq 'LoadBalancer' -and $_.metadata.name -notmatch 'gateway|istio|football-web' })
    if ($unexpected.Count) { throw "Unexpected AKS LoadBalancer services: $($unexpected.metadata.name -join ', ')" }
    Write-Host 'AKS insights isolation: PASS (ClusterIP; no unexpected LoadBalancer services).'
    $fqdn = az containerapp show --resource-group (Get-RequiredEnv 'AZURE_RESOURCE_GROUP') --name (Get-RequiredEnv 'ACA_INSIGHTS_APP_NAME') --query properties.configuration.ingress.fqdn -o tsv
    if ($LASTEXITCODE -ne 0) { throw 'Could not read ACA insights ingress FQDN.' }
    if ($fqdn -notmatch '\.internal\.') { throw "ACA insights FQDN is not internal: $fqdn" }
    try {
        Invoke-WebRequest -Uri "https://$fqdn/healthz" -TimeoutSec 10 -SkipHttpErrorCheck | Out-Null
        throw 'ACA insights /healthz was reachable from this machine; expected DNS or connection failure.'
    } catch {
        if ($_.Exception.Message -like 'ACA insights /healthz was reachable*') { throw }
        Write-Host 'ACA insights isolation: PASS (internal FQDN not reachable from this machine).'
    }
}
function Invoke-Smoke {
    Set-DemoSubscription
    Connect-Aks
    $digests = Import-Digests
    $versions = @()
    $versions += Test-Endpoint 'AKS' (Get-PlatformUrl 'aks') $digests
    $versions += Test-Endpoint 'ACA' (Get-PlatformUrl 'aca') $digests
    if ($versions[0] -ne $versions[1]) { throw "Curated data versions differ: AKS $($versions[0]) vs ACA $($versions[1])." }
    Invoke-Parity
    Test-InsightsIsolation
    Write-Host 'smoke OK: health, digests, data version, parity, and private insights isolation passed.'
}
function Invoke-LoadTest([string]$Platform = 'both', [int]$Rps = 20, [int]$Seconds = 60) {
    if ($Platform -notin @('aks', 'aca', 'both')) { throw 'Usage: demo load-test [aks|aca|both] [-Rps N] [-Seconds N]' }
    if ($Rps -lt 1 -or $Seconds -lt 1) { throw 'Rps and Seconds must be positive.' }
    $targets = if ($Platform -eq 'both') { @('aks', 'aca') } else { @($Platform) }
    foreach ($target in $targets) {
        if ($target -eq 'aks') { Connect-Aks }
        $url = Get-PlatformUrl $target
        $localOverride = $url -match '^https?://(127\.0\.0\.1|localhost)(:|/|$)'
        if ($localOverride) { Write-Host 'Local URL override detected; skipping platform replica observations.' }
        elseif ($target -eq 'aks') { kubectl -n football get hpa,pods }
        else {
            $rg = Get-RequiredEnv 'AZURE_RESOURCE_GROUP'
            foreach ($app in (Get-RequiredEnv 'ACA_WEB_APP_NAME'), (Get-RequiredEnv 'ACA_INSIGHTS_APP_NAME')) { Write-Host "$app replicas before: $(az containerapp replica list --resource-group $rg --name $app --query 'length(@)' -o tsv)" }
        }
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
        $out = Join-Path (Get-EvidenceDir) "loadtest-$target-$stamp.json"
        Write-Host "Load testing $target at $url ($Rps rps for $Seconds s)."
        $summary = & $script:Python -m football_insights load-test --url $url --rps $Rps --seconds $Seconds 2>&1
        $exit = $LASTEXITCODE
        $summary | Tee-Object -FilePath $out | Out-Host
        if ($exit -ne 0) { throw "load-test failed ($exit)" }
        if ($localOverride) { Write-Host 'Local URL override detected; skipped platform replica observations.' }
        elseif ($target -eq 'aks') { kubectl -n football get hpa,pods }
        else {
            $rg = Get-RequiredEnv 'AZURE_RESOURCE_GROUP'
            foreach ($app in (Get-RequiredEnv 'ACA_WEB_APP_NAME'), (Get-RequiredEnv 'ACA_INSIGHTS_APP_NAME')) { Write-Host "$app replicas after: $(az containerapp replica list --resource-group $rg --name $app --query 'length(@)' -o tsv)" }
        }
        Write-Host "Saved $out"
    }
}
function Invoke-RolloutV2 {
    Set-DemoSubscription
    Import-DeploymentOutputs
    $v2 = Import-Digests 'v2'
    Connect-Aks
    $suffix = 'v2-' + (Get-Date).ToUniversalTime().ToString('MMddHHmm')
    Write-Host "Rolling out tag $($v2.tag) with revision suffix $suffix."
    $rg = Get-RequiredEnv 'AZURE_RESOURCE_GROUP'
    $web = Get-RequiredEnv 'ACA_WEB_APP_NAME'
    $insights = Get-RequiredEnv 'ACA_INSIGHTS_APP_NAME'
    $current = az containerapp revision list --resource-group $rg --name $web --query '[?properties.active].name | [0]' -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $current) { throw 'Could not determine current ACA web revision.' }
    Invoke-AzChecked containerapp ingress traffic set --resource-group $rg --name $web --revision-weight "$current=100" --output none
    Invoke-AzChecked containerapp update --resource-group $rg --name $web --image "$($v2.registry)/football-insights-web@$($v2.web)" --revision-suffix $suffix --output none
    $newWeb = az containerapp revision list --resource-group $rg --name $web --query "[?ends_with(name, '$suffix')].name | [0]" -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $newWeb) { throw 'Could not determine new ACA web revision.' }
    Invoke-AzChecked containerapp ingress traffic set --resource-group $rg --name $web --revision-weight "$current=50" "$newWeb=50" --output none
    Invoke-AzChecked containerapp update --resource-group $rg --name $insights --image "$($v2.registry)/football-insights-insights@$($v2.insights)" --revision-suffix $suffix --output none
    @{ aca_web_previous = $current; aca_web_v2 = $newWeb; suffix = $suffix } | ConvertTo-Json | Set-Content -Encoding utf8 (Get-RolloutPath)
    Invoke-KubectlChecked -n football set image deployment/web "web=$($v2.registry)/football-insights-web@$($v2.web)"
    Invoke-KubectlChecked -n football set image deployment/insights "insights=$($v2.registry)/football-insights-insights@$($v2.insights)"
    Invoke-KubectlChecked -n football rollout status deployment/web --timeout=10m
    Invoke-KubectlChecked -n football rollout status deployment/insights --timeout=10m
    Write-Host 'ACA web traffic:'; az containerapp ingress traffic show --resource-group $rg --name $web -o table
    Write-Host 'AKS images:'; kubectl -n football get deploy web insights -o wide
}
function Invoke-Rollback([string]$Platform = 'both') {
    if ($Platform -notin @('aks', 'aca', 'both')) { throw 'Usage: demo rollback [aks|aca|both]' }
    Set-DemoSubscription
    Import-DeploymentOutputs
    $v1 = Import-Digests
    $v1Web = "$($v1.registry)/football-insights-web@$($v1.web)"
    $v1Insights = "$($v1.registry)/football-insights-insights@$($v1.insights)"
    $rg = Get-RequiredEnv 'AZURE_RESOURCE_GROUP'
    $web = Get-RequiredEnv 'ACA_WEB_APP_NAME'
    if ($Platform -in @('aca', 'both')) {
        $insights = Get-RequiredEnv 'ACA_INSIGHTS_APP_NAME'
        $rolloutPath = Get-RolloutPath
        if (Test-Path $rolloutPath) {
            # The previous revision is still running, so this is only a traffic change and takes effect at once.
            $rollout = Get-Content $rolloutPath -Raw | ConvertFrom-Json
            Invoke-AzChecked containerapp ingress traffic set --resource-group $rg --name $web --revision-weight "$($rollout.aca_web_previous)=100" --output none
            Remove-Item -Force $rolloutPath
        } else { Write-Host 'No v2 rollout recorded for ACA web; its traffic is unchanged.' }
        $current = az containerapp show --resource-group $rg --name $insights --query 'properties.template.containers[0].image' -o tsv
        if ($current -ne $v1Insights) { Invoke-AzChecked containerapp update --resource-group $rg --name $insights --image $v1Insights --output none }
        else { Write-Host 'ACA insights already runs the v1 image.' }
        Write-Host 'ACA web traffic:'; az containerapp ingress traffic show --resource-group $rg --name $web -o table
    }
    if ($Platform -in @('aks', 'both')) {
        # An explicit rolling update back to the v1 digests; `kubectl rollout undo` would revert whatever changed
        # last, which may be a model switch rather than the image.
        Connect-Aks
        if ((Get-ContainerImage 'web') -ne $v1Web) { Invoke-KubectlChecked -n football set image deployment/web "web=$v1Web" } else { Write-Host 'AKS web already runs the v1 image.' }
        if ((Get-ContainerImage 'insights') -ne $v1Insights) { Invoke-KubectlChecked -n football set image deployment/insights "insights=$v1Insights" } else { Write-Host 'AKS insights already runs the v1 image.' }
        Invoke-KubectlChecked -n football rollout status deployment/web --timeout=10m
        Invoke-KubectlChecked -n football rollout status deployment/insights --timeout=10m
        Write-Host 'AKS images:'; kubectl -n football get deploy web insights -o wide
    }
}
function Invoke-SwitchModel([string]$Deployment) {
    if ([string]::IsNullOrWhiteSpace($Deployment)) { throw 'Usage: demo switch-model <deployment>' }
    $allowed = (Get-EnvOrDefault 'AI_ALLOWED_DEPLOYMENTS' 'gpt-6-astra,gpt-6-sol').Split(',') | ForEach-Object { $_.Trim() }
    if ($Deployment -notin $allowed) { throw "Deployment $Deployment is not in AI_ALLOWED_DEPLOYMENTS." }
    Set-DemoSubscription
    Connect-Aks
    Update-DotEnvValue 'AI_MODEL_DEPLOYMENT' $Deployment
    Invoke-AzChecked containerapp update --resource-group (Get-RequiredEnv 'AZURE_RESOURCE_GROUP') --name (Get-RequiredEnv 'ACA_INSIGHTS_APP_NAME') --set-env-vars "AI_MODEL_DEPLOYMENT=$Deployment" --output none
    Invoke-KubectlChecked -n football set env deployment/insights "AI_MODEL_DEPLOYMENT=$Deployment"
    Invoke-KubectlChecked -n football rollout status deployment/insights --timeout=5m
    Write-Host "Both platforms now serve answers with $Deployment (configuration only; no rebuild)."
}
function Invoke-AllowIp {
    Set-DemoSubscription
    $ip = (Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 10).Trim()
    $cidr = "$ip/32"
    Update-DotEnvValue 'ALLOWED_CIDRS' $cidr
    $rg = Get-RequiredEnv 'AZURE_RESOURCE_GROUP'
    $app = Get-RequiredEnv 'ACA_WEB_APP_NAME'
    $cluster = Get-RequiredEnv 'AKS_CLUSTER_NAME'
    # Update whichever platforms are deployed; a team may deploy only one.
    if (az containerapp show --resource-group $rg --name $app --query name -o tsv 2>$null) {
        $rules = az containerapp ingress access-restriction list --resource-group $rg --name $app -o json | ConvertFrom-Json
        if ($LASTEXITCODE -eq 0) {
            foreach ($rule in @($rules)) { if ($rule.name -ne 'allow-0') { Invoke-AzChecked containerapp ingress access-restriction remove --resource-group $rg --name $app --rule-name $rule.name --output none } }
        }
        Invoke-AzChecked containerapp ingress access-restriction set --resource-group $rg --name $app --rule-name allow-0 --ip-address $cidr --action Allow --output none
        Write-Host "ACA web now accepts only $cidr."
    } else { Write-Host "ACA web app $app not found; skipped." }
    if (az aks show --resource-group $rg --name $cluster --query name -o tsv 2>$null) {
        Connect-Aks
        $patch = @{ spec = @{ infrastructure = @{ annotations = @{ 'service.beta.kubernetes.io/azure-allowed-ip-ranges' = $cidr } } } } | ConvertTo-Json -Depth 6 -Compress
        Invoke-KubectlChecked -n football patch gateway football-web --type merge -p $patch
        Write-Host "AKS web now accepts only $cidr."
    } else { Write-Host "AKS cluster $cluster not found; skipped." }
}
function Invoke-Trace([string]$TraceId) {
    if ([string]::IsNullOrWhiteSpace($TraceId)) { throw 'Usage: demo trace <id>' }
    Write-Host "AKS trace: $(Get-PlatformUrl 'aks')/trace/$TraceId"
    Write-Host "ACA trace: $(Get-PlatformUrl 'aca')/trace/$TraceId"
    $kql = Get-Content (Join-Path $script:Root 'demo/observability/queries.kql') -Raw
    $query = [regex]::Match($kql, '(?s)// 1\..*?(?=// 2\.)').Value.Replace('<trace id>', $TraceId).Trim()
    Write-Host "`nKQL query:`n$query"
}
function Invoke-Preflight {
    $ok = $true
    try { Set-DemoSubscription; Write-Check 'az signed in and subscription pinned' $true } catch { Write-Check 'az signed in and subscription pinned' $false $_.Exception.Message; $ok = $false }
    try {
        $expiry = az account get-access-token --query expiresOn -o tsv
        if ($LASTEXITCODE -ne 0) { throw 'az account get-access-token failed.' }
        $expiryTime = [datetime]::Parse($expiry)
        Write-Check 'Azure CLI token valid >30m' ($expiryTime -gt (Get-Date).AddMinutes(30)) "expires=$expiry"
    } catch { Write-Check 'Azure CLI token valid >30m' $false $_.Exception.Message; $ok = $false }
    try {
        $deployments = (Get-EnvOrDefault 'AI_ALLOWED_DEPLOYMENTS' 'gpt-6-astra,gpt-6-sol').Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        foreach ($deployment in $deployments) {
            $jsonText = az cognitiveservices account deployment show --resource-group (Get-RequiredEnv 'AZURE_RESOURCE_GROUP') --name (Get-RequiredEnv 'FOUNDRY_RESOURCE_NAME') --deployment-name $deployment --query '{version:properties.model.version, upgrade:properties.versionUpgradeOption}' -o json
            if ($LASTEXITCODE -ne 0) { throw "Could not read Foundry deployment $deployment." }
            $json = $jsonText | ConvertFrom-Json
            Write-Check "Foundry $deployment pinned" ($json.upgrade -eq 'NoAutoUpgrade') "version=$($json.version) upgrade=$($json.upgrade)"
        }
    } catch { Write-Check 'Foundry deployments pinned' $false $_.Exception.Message; $ok = $false }
    try { Connect-Aks; kubectl -n football get deploy | Out-Host; if ($LASTEXITCODE -ne 0) { throw 'kubectl get deploy failed.' }; Write-Check 'kubectl reaches cluster' $true } catch { Write-Check 'kubectl reaches cluster' $false $_.Exception.Message; $ok = $false }
    try {
        $digests = Import-Digests
        foreach ($platform in 'aks', 'aca') { [void](Test-Endpoint $platform.ToUpper() (Get-PlatformUrl $platform) $digests) }
        Write-Check 'web endpoints healthy with recorded digest' $true '(demo smoke runs the full check)'
    } catch { Write-Check 'web endpoints healthy with recorded digest' $false $_.Exception.Message; $ok = $false }
    try {
        $ip = (Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 10).Trim()
        $allowed = (Get-RequiredEnv 'ALLOWED_CIDRS').Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        $contains = @($allowed | Where-Object { Test-IPv4InCidr $ip $_ }).Count -gt 0
        Write-Check 'public IP inside ALLOWED_CIDRS' $contains $ip
    } catch { Write-Check 'public IP inside ALLOWED_CIDRS' $false $_.Exception.Message; $ok = $false }
    try { docker info *> $null; Write-Check 'Docker Desktop running' ($LASTEXITCODE -eq 0) } catch { Write-Check 'Docker Desktop running' $false $_.Exception.Message; $ok = $false }
    try {
        if (Test-Path $script:TokenFile) {
            $tokens = Get-Content $script:TokenFile -Raw | ConvertFrom-Json
            $min = ($tokens.PSObject.Properties.Value | ForEach-Object { [long]$_.expires_on } | Measure-Object -Minimum).Minimum
            Write-Check 'local token file not near expiry' ([DateTimeOffset]::FromUnixTimeSeconds($min) -gt [DateTimeOffset]::Now.AddMinutes(10))
        } else { Write-Check 'local token file absent' $true }
    } catch { Write-Check 'local token file not near expiry' $false $_.Exception.Message; $ok = $false }
    $kaggle = (Test-Path (Join-Path $HOME '.kaggle/kaggle.json')) -or [bool]$env:KAGGLE_API_TOKEN
    Write-Host "INFO: Kaggle credential present: $kaggle"
    Test-VersionPin 'az version' (az version --query '"azure-cli"' -o tsv) $env:PINNED_AZ
    if ($LASTEXITCODE -ne 0) { $ok = $false }
    Test-VersionPin 'kubectl version' ((kubectl version --client=true -o json | ConvertFrom-Json).clientVersion.gitVersion) $env:PINNED_KUBECTL
    if ($LASTEXITCODE -ne 0) { $ok = $false }
    Test-VersionPin 'docker version' (docker version --format '{{.Client.Version}}') $env:PINNED_DOCKER
    if ($LASTEXITCODE -ne 0) { $ok = $false }
    $githubExe = Join-Path $env:LOCALAPPDATA 'Programs/GitHub Copilot/github.exe'
    if (Test-Path $githubExe) { Test-VersionPin 'GitHub Copilot app' ((Get-Item $githubExe).VersionInfo.ProductVersion) $env:PINNED_COPILOT_APP } else { Write-Check 'GitHub Copilot app' $false 'github.exe not found'; $ok = $false }
    if (-not $ok) { throw 'preflight failed.' }
}
function Invoke-Reset {
    Set-DemoSubscription
    Import-DeploymentOutputs
    $v1 = Import-Digests
    $changed = @()
    Connect-Aks
    $needsRollback = Test-Path (Get-RolloutPath)
    if (-not $needsRollback) {
        $webImage = Get-ContainerImage 'web'
        $insightsImage = Get-ContainerImage 'insights'
        $needsRollback = ($webImage -ne "$($v1.registry)/football-insights-web@$($v1.web)") -or ($insightsImage -ne "$($v1.registry)/football-insights-insights@$($v1.insights)")
    }
    if ($needsRollback) { Invoke-Rollback; $changed += 'rolled back v2 images/traffic to v1' }
    $defaultModel = Get-EnvOrDefault 'DEFAULT_MODEL_DEPLOYMENT' 'gpt-6-astra'
    if ((Get-EnvOrDefault 'AI_MODEL_DEPLOYMENT' 'gpt-6-astra') -ne $defaultModel) { Invoke-SwitchModel $defaultModel; $changed += "model reset to $defaultModel" }
    if ($changed.Count -eq 0) { Write-Host 'reset: no changes needed.' } else { Write-Host "reset changed: $($changed -join '; ')" }
}
function Invoke-Teardown([switch]$DryRun) {
    Set-DemoSubscription
    $rg = Get-RequiredEnv 'AZURE_RESOURCE_GROUP'
    $project = Get-EnvOrDefault 'PROJECT_TAG' 'football-insights'
    Write-Host "Resources in $rg (project tag comparison: $project):"
    $resources = az resource list --resource-group $rg --query '[].{name:name,type:type,project:tags.project}' -o json | ConvertFrom-Json
    foreach ($r in @($resources)) {
        $note = if ($r.project -eq $project) { 'tagged by this project' } else { 'not tagged by this project - confirm before deleting' }
        Write-Host ("{0}`t{1}`t{2}" -f $r.name, $r.type, $note)
    }
    $nodeRg = az aks show --resource-group $rg --name (Get-EnvOrDefault 'AKS_CLUSTER_NAME' '') --query nodeResourceGroup -o tsv 2>$null
    if ($LASTEXITCODE -eq 0 -and $nodeRg) { Write-Host "AKS node resource group: $nodeRg (deleted with the cluster)." }
    if ($DryRun) { Write-Host 'Dry run only: nothing was deleted.'; return }
    $confirm = Read-Host "Delete the whole resource group '$rg'? Type its name to confirm"
    if ($confirm -ne $rg) { throw 'Confirmation did not match; nothing was deleted.' }
    Invoke-AzChecked group delete --name $rg --yes --no-wait
    Write-Host "Deletion of $rg started."
}
