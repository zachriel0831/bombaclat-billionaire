# Run official-list coverage audit for news-platform sources.
param(
  [string]$EnvFile = ".env",
  [string]$Categories = "society,politics",
  [string]$SourceIds = "",
  [string]$SkipSourceIds = "ctee",
  [int]$Limit = 20,
  [double]$MinCoverage = 0.85,
  [int]$MinItems = 3,
  [switch]$Compensate,
  [switch]$FailOnWarn,
  [switch]$Json,
  [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"
. (Join-Path $PSScriptRoot "codex_observer.ps1")

function Resolve-PythonExe {
  param([string]$RequestedPath)

  if (-not [string]::IsNullOrWhiteSpace($RequestedPath) -and (Test-Path -LiteralPath $RequestedPath)) {
    return $RequestedPath
  }

  $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $venvPython) {
    return $venvPython
  }

  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCmd) {
    return $pythonCmd.Source
  }

  throw "Unable to locate python.exe. Pass -PythonExe explicitly."
}

$reportDir = Join-Path $ProjectRoot "runtime\news-source-accuracy"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$jsonOut = Join-Path $reportDir "latest.json"
$textOut = Join-Path $reportDir "latest.txt"

$argsList = @(
  "scripts\check_news_source_accuracy.py",
  "--env-file", $EnvFile,
  "--categories", $Categories,
  "--skip-source-ids", $SkipSourceIds,
  "--limit", [string]$Limit,
  "--min-coverage", [string]$MinCoverage,
  "--min-items", [string]$MinItems,
  "--json-out", $jsonOut,
  "--text-out", $textOut
)
if (-not [string]::IsNullOrWhiteSpace($SourceIds)) {
  $argsList += @("--source-ids", $SourceIds)
}
if ($Compensate) {
  $argsList += "--compensate"
}
if ($Json) {
  $argsList += "--json"
}
if ($FailOnWarn) {
  $argsList += "--fail-on-warn"
}

$resolvedPython = Resolve-PythonExe -RequestedPath $PythonExe
$exitCode = Invoke-CodexObservedCommand `
  -Job "news_source_accuracy_audit" `
  -Category "audit" `
  -Skill "news-ingestion-skill" `
  -Metadata @{
    categories = $Categories
    source_ids = if ([string]::IsNullOrWhiteSpace($SourceIds)) { "default+low_frequency" } else { $SourceIds }
    skip_source_ids = $SkipSourceIds
    limit = $Limit
    min_coverage = $MinCoverage
    compensate = [bool]$Compensate
    report = "runtime/news-source-accuracy/latest.json"
  } `
  -Command {
    & $resolvedPython @argsList
    $auditExitCode = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
    $finalExitCode = $auditExitCode
    if ($Compensate) {
      & $resolvedPython -m news_platform.main `
        --env-file $EnvFile `
        --extract-keywords `
        --classify-topics `
        --log-level INFO
      if ($LASTEXITCODE -ne 0) {
        $finalExitCode = 1
      }
    }
    $global:LASTEXITCODE = $finalExitCode
  }

exit $exitCode
