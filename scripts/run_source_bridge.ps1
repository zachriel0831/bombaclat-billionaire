﻿# 啟動多來源 bridge，將事件轉送至 relay。
param(
  [string]$RelayUrl = "http://127.0.0.1:18090/events",
  [int]$PollIntervalSeconds = 300,
  [int]$Limit = 5,
  [string]$Tickers = "",
  [string]$Channels = "",
  [string]$Languages = "en,cn",
  [string]$EnvFile = ".env",
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Starting source bridge (BENZINGA + GDELT + RSS + X -> LINE relay)..." -ForegroundColor Cyan

$cmdArgs = @(
  "-m", "news_collector.relay_bridge",
  "--relay-url", $RelayUrl,
  "--poll-interval-seconds", "$PollIntervalSeconds",
  "--limit", "$Limit",
  "--env-file", $EnvFile,
  "--log-level", $LogLevel
)

if (-not [string]::IsNullOrWhiteSpace($Tickers)) {
  $cmdArgs += @("--tickers", $Tickers)
}
if (-not [string]::IsNullOrWhiteSpace($Channels)) {
  $cmdArgs += @("--channels", $Channels)
}
if (-not [string]::IsNullOrWhiteSpace($Languages)) {
  $cmdArgs += @("--languages", $Languages)
}

& python @cmdArgs
