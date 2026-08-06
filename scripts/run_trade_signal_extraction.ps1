# Compatibility no-op. Stock recommendation extraction was retired, so this
# script intentionally stores no t_trade_signals rows.
param(
  [string]$EnvFile = ".env",
  [int]$Days = 14,
  [int]$Limit = 50,
  [int]$AnalysisId = 0,
  [switch]$FixedPoolFallback,
  [int]$EventDays = 1,
  [int]$EventLimit = 200,
  [int]$PriorDays = 30,
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
Write-Host "Trade signal extraction is retired; no stock recommendations will be generated." -ForegroundColor Yellow
exit 0
