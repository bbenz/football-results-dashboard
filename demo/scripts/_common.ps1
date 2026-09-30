# Shared helpers for demo/scripts/*.ps1. Dot-source it; it sets $script:Root and $script:Python.
Set-StrictMode -Version Latest

$script:Root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$script:Python = if ($IsWindows -or $env:OS -eq 'Windows_NT') { Join-Path $script:Root '.venv/Scripts/python.exe' } else { Join-Path $script:Root '.venv/bin/python' }
$script:TokenFile = Join-Path $script:Root '.local/secrets/tokens.json'
$script:TokenScopes = @('https://ai.azure.com/.default')

function Import-DotEnv {
    # Load KEY=VALUE lines from the repository's .env into this process only, without overriding
    # variables that are already set. Values are never printed.
    $path = Join-Path $script:Root '.env'
    if (-not (Test-Path $path)) { return }
    foreach ($line in Get-Content $path) {
        if ($line -match '^\s*#' -or $line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }
        $name, $value = $Matches[1], $Matches[2].Trim().Trim('"')
        if ($value -and -not [Environment]::GetEnvironmentVariable($name)) { [Environment]::SetEnvironmentVariable($name, $value) }
    }
}

function Invoke-Checked {
    $exe = $args[0]
    $arguments = @(if ($args.Count -gt 1) { $args[1..($args.Count - 1)] })
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "command failed ($LASTEXITCODE): $exe $($arguments -join ' ')" }
}

function Get-SystemPython {
    foreach ($candidate in 'python', 'python3', 'py') {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) { return $candidate }
    }
    throw 'Python 3.12 is not on PATH. Install it from python.org and reopen the terminal.'
}

function Invoke-Cli {
    if (-not (Test-Path $script:Python)) { throw 'No .venv yet: run demo bootstrap first.' }
    & $script:Python -m football_insights @args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Get-ComposeArgs {
    # Compose resolves relative paths against demo/docker, so hand it the data folder as an absolute path.
    $data = if ($env:FOOTBALL_DATA_DIR) { $env:FOOTBALL_DATA_DIR } else { 'data' }
    if (-not [IO.Path]::IsPathRooted($data)) { $data = Join-Path $script:Root $data }
    $env:FOOTBALL_DATA_DIR_HOST = [IO.Path]::GetFullPath($data)
    $composeArgs = @('-f', (Join-Path $script:Root 'demo/docker/compose.yaml'))
    $envFile = Join-Path $script:Root '.env'
    if (Test-Path $envFile) { $composeArgs = @('--env-file', $envFile) + $composeArgs }
    return $composeArgs
}

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -SkipHttpErrorCheck
            if ($response.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Seconds 1 }
        Start-Sleep -Seconds 2
    }
    throw "timed out after $TimeoutSeconds s waiting for $Url"
}

function Update-TokenFile {
    # Short-lived access tokens from the operator's own Azure CLI sign-in, one per scope, written to an
    # ignored file that only the insights container mounts. Tokens are never printed; only expiry is.
    $tokens = @{}
    foreach ($scope in $script:TokenScopes) {
        $json = az account get-access-token --scope $scope --query '{token: accessToken, expires_on: expires_on}' -o json
        if ($LASTEXITCODE -ne 0) { throw "az account get-access-token failed for $scope; run az login" }
        $tokens[$scope] = $json | ConvertFrom-Json
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $script:TokenFile) | Out-Null
    $tmp = "$script:TokenFile.tmp"
    [IO.File]::WriteAllText($tmp, ($tokens | ConvertTo-Json -Depth 3))
    Move-Item -Force $tmp $script:TokenFile
    $earliest = ($tokens.Values | ForEach-Object { [long]$_.expires_on } | Measure-Object -Minimum).Minimum
    Write-Host ("token file refreshed; expires {0:HH:mm}" -f [DateTimeOffset]::FromUnixTimeSeconds($earliest).LocalDateTime)
}

function Start-TokenRefresh {
    Stop-TokenRefresh
    $common = Join-Path $PSScriptRoot '_common.ps1'
    Start-Job -Name 'demo-token-refresh' -ScriptBlock {
        param($CommonPath)
        . $CommonPath
        while ($true) { Start-Sleep -Seconds 900; Update-TokenFile *> $null }
    } -ArgumentList $common | Out-Null
    Write-Host 'token refresh running every 15 minutes while this terminal stays open (demo down stops it)'
}

function Stop-TokenRefresh {
    Get-Job -Name 'demo-token-refresh' -ErrorAction SilentlyContinue | Remove-Job -Force
}

function Remove-TokenFile {
    if (Test-Path $script:TokenFile) { Remove-Item -Force $script:TokenFile }
}

Import-DotEnv
$env:PYTHONPATH = Join-Path $script:Root 'demo/src'
$env:PYTHONUTF8 = '1'
Set-Location $script:Root
