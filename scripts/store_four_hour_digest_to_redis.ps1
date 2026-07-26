param(
  [string]$InputFile = "-",
  [int]$TtlSeconds = 15000,
  [string]$RedisUrl = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONUNBUFFERED = "1"
. (Join-Path $PSScriptRoot "codex_observer.ps1")

$cmdArgs = @(
  (Join-Path $ProjectRoot "scripts\store_four_hour_digest_to_redis.py"),
  "--input-file", $InputFile,
  "--ttl-seconds", "$TtlSeconds"
)

if ($RedisUrl) {
  $cmdArgs += @("--redis-url", $RedisUrl)
}
if ($DryRun) {
  $cmdArgs += "--dry-run"
}

$exitCode = Invoke-CodexObservedCommand `
  -Job "four_hour_digest_store" `
  -Category "article" `
  -Skill "four-hour-digest-workflow" `
  -Metadata @{ input_file = [System.IO.Path]::GetFileName($InputFile); ttl_seconds = $TtlSeconds; dry_run = $DryRun.IsPresent } `
  -Command { & python @cmdArgs }

exit $exitCode
