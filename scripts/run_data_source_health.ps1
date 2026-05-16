# Run the read-only data-source freshness health report.
param(
  [string]$EnvFile = ".env",
  [switch]$Json,
  [switch]$SkipProcesses,
  [switch]$FailOnWarn,
  [switch]$FailOnStale,
  [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"

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

$argsList = @("scripts\check_data_source_health.py", "--env-file", $EnvFile)
if ($Json) { $argsList += "--json" }
if ($SkipProcesses) { $argsList += "--skip-processes" }
if ($FailOnWarn) { $argsList += "--fail-on-warn" }
if ($FailOnStale) { $argsList += "--fail-on-stale" }

$resolvedPython = Resolve-PythonExe -RequestedPath $PythonExe
& $resolvedPython @argsList
exit $LASTEXITCODE

