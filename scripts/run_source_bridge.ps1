# Start multi-source bridge and forward events to relay.
param(
  [string]$RelayUrl = "http://127.0.0.1:18090/events",
  [string]$RelayDirectPushUrl = "http://127.0.0.1:18090/push/direct",
  [int]$PollIntervalSeconds = 300,
  [int]$Limit = 5,
  [string]$Tickers = "",
  [string]$Channels = "",
  [string]$Languages = "en,cn",
  [int]$XStreamTimeoutSeconds = 90,
  [int]$XStreamReconnectMaxSeconds = 120,
  [int]$UsIndexPollIntervalSeconds = 30,
  [switch]$DisableUsIndex,
  [string]$EnvFile = ".env",
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Starting source bridge (BENZINGA stream + X stream + RSS/GDELT polling + US index direct push -> LINE relay)..." -ForegroundColor Cyan

$cmdArgs = @(
  "-m", "news_collector.relay_bridge",
  "--relay-url", $RelayUrl,
  "--relay-direct-push-url", $RelayDirectPushUrl,
  "--poll-interval-seconds", "$PollIntervalSeconds",
  "--limit", "$Limit",
  "--env-file", $EnvFile,
  "--x-stream-timeout-seconds", "$XStreamTimeoutSeconds",
  "--x-stream-reconnect-max-seconds", "$XStreamReconnectMaxSeconds",
  "--us-index-poll-interval-seconds", "$UsIndexPollIntervalSeconds",
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
if ($DisableUsIndex) {
  $cmdArgs += "--disable-us-index"
}

& python @cmdArgs
