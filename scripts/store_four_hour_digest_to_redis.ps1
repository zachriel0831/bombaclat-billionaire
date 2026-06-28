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

& python @cmdArgs
exit $LASTEXITCODE
