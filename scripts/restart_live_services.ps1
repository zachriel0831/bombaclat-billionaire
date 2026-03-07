﻿# 一鍵重啟 relay 與 source bridge 服務視窗。
param(
  [string]$EnvFile = ".env",
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

# Stop existing relay/bridge python processes first.
$targets = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^python(3\.12)?(\.exe)?$' -and (
    $_.CommandLine -match 'line_event_relay\.main' -or
    $_.CommandLine -match 'news_collector\.relay_bridge'
  )
}
if ($targets) {
  $targets | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}

$relayCmd = "Set-Location '$ProjectRoot'; powershell -ExecutionPolicy Bypass -File '.\\scripts\\run_line_event_relay.ps1' -EnvFile '$EnvFile' -LogLevel '$LogLevel'"
$bridgeCmd = "Set-Location '$ProjectRoot'; powershell -ExecutionPolicy Bypass -File '.\\scripts\\run_source_bridge.ps1' -EnvFile '$EnvFile' -LogLevel '$LogLevel'"

Start-Process powershell -ArgumentList @('-NoExit', '-Command', $relayCmd) -WindowStyle Normal
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $bridgeCmd) -WindowStyle Normal

Write-Host "Live service windows started (relay + source bridge)." -ForegroundColor Green
