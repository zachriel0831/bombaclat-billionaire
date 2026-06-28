param(
  [string]$EnvFile = ".env",
  [int]$Hours = 4,
  [int]$LimitPerSection = 80,
  [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"

$cmdArgs = @(
  (Join-Path $ProjectRoot "scripts\collect_four_hour_digest_context.py"),
  "--env-file", $EnvFile,
  "--hours", "$Hours",
  "--limit-per-section", "$LimitPerSection"
)

if ($OutFile) {
  $cmdArgs += @("--out-file", $OutFile)
}

& python @cmdArgs
exit $LASTEXITCODE
