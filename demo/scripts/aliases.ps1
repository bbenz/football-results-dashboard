# Dot-source once per terminal to get the short `demo` command:  . ./demo/scripts/aliases.ps1
Set-Alias -Name demo -Value (Join-Path $PSScriptRoot 'demo.ps1') -Scope Global
Write-Host "demo is ready. Try: demo verify, demo up, demo test"
