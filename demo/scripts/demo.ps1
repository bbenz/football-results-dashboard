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
    down          Stop Docker Compose and delete any local token file.
    logs          Show the last Compose log lines.
    test          Run the no-data guard, ruff, mypy, and the tests.
    guard         Run the no-data guard on the index and the full history.

  Settings come from environment variables and the repository's .env (see .env.example).
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Command = 'help',
    [switch]$LiveModel,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

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
    'up' {
        Invoke-Checked docker compose @(Get-ComposeArgs) build
        $env:WEB_IMAGE_DIGEST = (docker image inspect football-insights-web:local --format '{{.Id}}')
        $env:INSIGHTS_IMAGE_DIGEST = (docker image inspect football-insights-insights:local --format '{{.Id}}')
        $files = @()
        if ($LiveModel) {
            if (-not $env:FOUNDRY_PROJECT_ENDPOINT) { throw 'demo up -LiveModel needs FOUNDRY_PROJECT_ENDPOINT in .env' }
            Update-TokenFile
            Start-TokenRefresh
            $files = @('-f', (Join-Path $script:Root 'demo/docker/compose.live.yaml'))
        }
        Invoke-Checked docker compose @(Get-ComposeArgs) @files up -d
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
    'guard' {
        Invoke-Checked $script:Python (Join-Path $script:Root 'demo/scripts/check_no_data.py')
        Invoke-Checked $script:Python (Join-Path $script:Root 'demo/scripts/check_no_data.py') --history
    }
    default { Get-Help $PSCommandPath -Detailed | Out-String | Write-Host }
}
