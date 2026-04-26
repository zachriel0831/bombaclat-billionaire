# Run historical-case RAG indexer (single-shot).
param(
  [string]$EnvFile = ".env",
  [int]$Days = 30,
  [int]$EventLimit = 500,
  [int]$AnalysisLimit = 100,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Running RAG indexer days=$Days eventLimit=$EventLimit analysisLimit=$AnalysisLimit ..." -ForegroundColor Cyan

& python -m event_relay.rag `
  --env-file $EnvFile `
  --days $Days `
  --event-limit $EventLimit `
  --analysis-limit $AnalysisLimit `
  --log-level $LogLevel
