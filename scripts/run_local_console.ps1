﻿# 本地輪巡抓取入口（單次/Watch 模式）。
param(
  [ValidateSet("rss", "x", "all")]
  [string]$Source = "rss",
  [int]$Limit = 3,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [int]$IntervalSeconds = 120,
  [switch]$Watch,
  [string]$EnvFile = ".env",
  [string]$Languages = "",
  [switch]$TitleUrlOnly
)

$ErrorActionPreference = "Stop"

# Resolve project root from script location.
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OutputDir = Join-Path $ProjectRoot "runtime\logs"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# Ensure relative paths (.env/.secrets) resolve from project root.
Set-Location -LiteralPath $ProjectRoot

$env:PYTHONPATH = Join-Path $ProjectRoot "src"

function Invoke-NewsFetchOnce {
  $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $logFile = Join-Path $OutputDir "fetch-$timestamp.log"

  Write-Host "[$(Get-Date -Format 'u')] Running fetch source=$Source limit=$Limit log_level=$LogLevel languages=$Languages" -ForegroundColor Cyan
  Write-Host "Log file: $logFile" -ForegroundColor DarkGray

  # Merge stdout and stderr, and save both to file and console.
  $cmdArgs = @(
    "-m", "news_collector.main", "fetch",
    "--source", $Source,
    "--limit", "$Limit",
    "--log-level", $LogLevel,
    "--env-file", $EnvFile,
    "--pretty"
  )

  if (-not [string]::IsNullOrWhiteSpace($Languages)) {
    $cmdArgs += @("--languages", $Languages)
  }

  if ($TitleUrlOnly) {
    $cmdArgs += @("--title-url-only")
  }

  & python @cmdArgs 2>&1 | Tee-Object -FilePath $logFile
}

if (-not $Watch) {
  Invoke-NewsFetchOnce
  exit $LASTEXITCODE
}

Write-Host "Watch mode enabled. Press Ctrl+C to stop." -ForegroundColor Yellow
while ($true) {
  Invoke-NewsFetchOnce
  Start-Sleep -Seconds $IntervalSeconds
}
