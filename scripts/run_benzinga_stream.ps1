﻿# 啟動 Benzinga 串流並輸出日誌檔。
param(
  [string]$Tickers = "",
  [string]$Channels = "",
  [string]$Languages = "",
  [switch]$UrlOnly,
  [int]$MaxMessages = 20,
  [int]$DurationSeconds = 0,
  [int]$ReconnectMaxSeconds = 60,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OutputDir = Join-Path $ProjectRoot "runtime\logs"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# Ensure relative paths (.env/.secrets) resolve from project root.
Set-Location -LiteralPath $ProjectRoot

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$jsonlFile = Join-Path $OutputDir "benzinga-stream-$timestamp.jsonl"

Write-Host "Starting Benzinga stream..." -ForegroundColor Cyan
Write-Host "Output file: $jsonlFile" -ForegroundColor DarkGray

$cmdArgs = @(
  "-m", "news_collector.main", "stream",
  "--env-file", $EnvFile,
  "--max-messages", "$MaxMessages",
  "--duration-seconds", "$DurationSeconds",
  "--reconnect-max-seconds", "$ReconnectMaxSeconds",
  "--log-level", $LogLevel,
  "--output-file", $jsonlFile
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

if ($UrlOnly) {
  $cmdArgs += @("--url-only")
}

& python @cmdArgs
