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
. (Join-Path $PSScriptRoot "codex_observer.ps1")

$cmdArgs = @(
  (Join-Path $ProjectRoot "scripts\collect_four_hour_digest_context.py"),
  "--env-file", $EnvFile,
  "--hours", "$Hours",
  "--limit-per-section", "$LimitPerSection"
)

if ($OutFile) {
  $cmdArgs += @("--out-file", $OutFile)
}

$exitCode = Invoke-CodexObservedCommand `
  -Job "four_hour_digest_context" `
  -Category "article" `
  -Skill "four-hour-digest-workflow" `
  -Rag "four-hour-digest-context" `
  -Metadata @{ hours = $Hours; limit_per_section = $LimitPerSection; out_file = [System.IO.Path]::GetFileName($OutFile) } `
  -Command { & python @cmdArgs }

exit $exitCode
