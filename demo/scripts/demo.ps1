<#
.SYNOPSIS
  Operator commands for the football insights demo (PowerShell 7).

.DESCRIPTION
  Run from anywhere:  ./demo/scripts/demo.ps1 <command> [options]
  Or load the alias once per terminal:  . ./demo/scripts/aliases.ps1   then   demo <command>

  Local commands
    bootstrap     Create .venv and install the pinned development dependencies.
    download      Optional: fetch the Kaggle datasets into data/ (see data/README.md).
    verify        Check the raw data under FOOTBALL_DATA_DIR (default data/) against the contract.
    ingest        Build and publish a curated version into CURATED_DIR (default .local/curated).
    up            Build the three images and start Docker Compose (web on http://127.0.0.1:8080).
                  -LiveModel: also give insights a short-lived Foundry token from your own sign-in.
                  -FromRegistry: run the digests pushed by build-push instead of building locally.
    down          Stop Docker Compose and delete any local token file.
    logs          Show the last Compose log lines.
    test          Run the no-data guard, ruff, mypy, and the tests.
    pytest        Run only the named tests, for example: demo pytest tests/test_q3_trends.py
    guard         Run the no-data guard on the index and the full history.
    install-hook  Optional: install a git pre-commit hook that runs the no-data guard.

  Model commands (need a Foundry project; see docs/METHODS.md)
    eval          Run the evaluation suite against the model deployments.
    capture       Save labeled narratives of the prepared questions for the offline fallback.

  Azure commands (not run by local setup)
    azure-foundation, azure-platform, upload-data, build-push, aks-deploy, aca-deploy,
    ingest-aks, ingest-aca, smoke, parity, snapshot [aks|aca|both|local], load-test [aks|aca|both], rollout-v2,
    rollback [aks|aca|both], trace <id>, preflight, reset, allow-ip, switch-model <deployment>, teardown -DryRun

  Settings come from environment variables and the repository's .env (see .env.example).
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Command = 'help',
    [switch]$LiveModel,
    [switch]$FromRegistry,
    [switch]$DryRun,
    [int]$Rps = 20,
    [int]$Seconds = 60,
    [string]$Output = '',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
. (Join-Path $PSScriptRoot 'azure.ps1')

switch ($Command) {
    'bootstrap' {
        if (-not (Test-Path $script:Python)) { & (Get-SystemPython) -m venv (Join-Path $script:Root '.venv') }
        Invoke-Checked $script:Python -m pip install --quiet --upgrade pip
        Invoke-Checked $script:Python -m pip install --quiet --require-hashes -r (Join-Path $script:Root 'demo/requirements-dev.lock')
        Write-Host 'bootstrap OK: .venv ready. Next: demo verify'
    }
    'download' { Invoke-Cli download-data @Rest }
    'verify' { Invoke-Cli verify-data @Rest }
    'ingest' { Invoke-Cli ingest @Rest }
    'eval' { Invoke-Cli eval @Rest }
    'capture' { Invoke-Cli capture-narratives @Rest }
    'up' {
        $files = @()
        if ($FromRegistry) {
            # Run the exact digests pushed by build-push, so the local badge matches AKS and ACA.
            Set-DemoSubscription
            $digests = Import-Digests
            Invoke-AzChecked acr login --name (Get-RequiredEnv 'ACR_NAME')
            foreach ($t in 'web', 'insights', 'ingest') {
                [Environment]::SetEnvironmentVariable("$($t.ToUpper())_IMAGE", "$($digests.registry)/football-insights-$t@$($digests.$t)")
            }
            $upArgs = @('up', '-d', '--no-build', '--pull', 'always')
        } else {
            Invoke-Checked docker compose @(Get-ComposeArgs) build
            $env:WEB_IMAGE_DIGEST = (docker image inspect football-insights-web:local --format '{{.Id}}')
            $env:INSIGHTS_IMAGE_DIGEST = (docker image inspect football-insights-insights:local --format '{{.Id}}')
            $upArgs = @('up', '-d')
        }
        if ($LiveModel) {
            if (-not $env:FOUNDRY_PROJECT_ENDPOINT) { throw 'demo up -LiveModel needs FOUNDRY_PROJECT_ENDPOINT in .env' }
            Update-TokenFile
            Start-TokenRefresh
            $files = @('-f', (Join-Path $script:Root 'demo/docker/compose.live.yaml'))
        }
        Invoke-Checked docker compose @(Get-ComposeArgs) @files @upArgs
        Wait-Http 'http://127.0.0.1:8080/readyz' 180
        Write-Host "up OK: http://127.0.0.1:8080  (web $($env:WEB_IMAGE_DIGEST.Substring(7, 12)), insights $($env:INSIGHTS_IMAGE_DIGEST.Substring(7, 12)))"
    }
    'down' {
        Stop-TokenRefresh
        Invoke-Checked docker compose @(Get-ComposeArgs) -f (Join-Path $script:Root 'demo/docker/compose.live.yaml') down
        Remove-TokenFile
        Write-Host 'down OK'
    }
    'logs' { docker compose @(Get-ComposeArgs) logs --tail 40 @Rest }
    'test' {
        Invoke-Checked $script:Python (Join-Path $script:Root 'demo/scripts/check_no_data.py')
        Push-Location (Join-Path $script:Root 'demo')
        try {
            Invoke-Checked $script:Python -m ruff check src tests scripts
            Invoke-Checked $script:Python -m mypy
            Invoke-Checked $script:Python -m pytest -q @Rest
        } finally { Pop-Location }
    }
    'pytest' {
        # Only the named tests, without lint and type checks: for a quick check on stage.
        Push-Location (Join-Path $script:Root 'demo')
        try { Invoke-Checked $script:Python -m pytest -q @Rest } finally { Pop-Location }
    }
    'guard' {
        Invoke-Checked $script:Python (Join-Path $script:Root 'demo/scripts/check_no_data.py')
        Invoke-Checked $script:Python (Join-Path $script:Root 'demo/scripts/check_no_data.py') --history
    }
    'install-hook' {
        $hook = Join-Path $script:Root '.git/hooks/pre-commit'
        $lines = @(
            '#!/bin/sh',
            '# Installed by demo install-hook: refuse commits that would add data.',
            'for py in .venv/Scripts/python.exe .venv/bin/python python3 python; do',
            '  if command -v "$py" >/dev/null 2>&1; then exec "$py" demo/scripts/check_no_data.py; fi',
            'done',
            'echo "no-data guard: no Python found; run demo bootstrap" >&2',
            'exit 1'
        )
        [IO.File]::WriteAllText($hook, ($lines -join "`n") + "`n")
        Write-Host "pre-commit hook installed: $hook"
    }
    'azure-foundation' { Invoke-AzureFoundation }
    'azure-platform' { Invoke-AzurePlatform }
    'upload-data' { Invoke-UploadData }
    'build-push' { Invoke-BuildPush -Output $Output }
    'aks-deploy' { Invoke-AksDeploy }
    'aca-deploy' { Invoke-AcaDeploy }
    'ingest-aks' { Invoke-IngestAks }
    'ingest-aca' { Invoke-IngestAca }
    'smoke' { Invoke-Smoke }
    'parity' { Invoke-Parity }
    'snapshot' { Invoke-Snapshot -Platform $(if ($Rest.Count) { $Rest[0] } else { 'both' }) }
    'load-test' { Invoke-LoadTest -Platform $(if ($Rest.Count) { $Rest[0] } else { 'both' }) -Rps $Rps -Seconds $Seconds }
    'rollout-v2' { Invoke-RolloutV2 }
    'rollback' { Invoke-Rollback -Platform $(if ($Rest.Count) { $Rest[0] } else { 'both' }) }
    'trace' { Invoke-Trace -TraceId $(if ($Rest.Count) { $Rest[0] } else { '' }) }
    'preflight' { Invoke-Preflight }
    'reset' { Invoke-Reset }
    'allow-ip' { Invoke-AllowIp }
    'switch-model' { Invoke-SwitchModel -Deployment $(if ($Rest.Count) { $Rest[0] } else { '' }) }
    'teardown' { Invoke-Teardown -DryRun:$DryRun }
    default { Get-Help $PSCommandPath -Detailed | Out-String | Write-Host }
}
