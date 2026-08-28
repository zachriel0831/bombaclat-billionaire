# Run international homepage headline collection in one persistent console window.
param(
  [string]$EnvFile = ".env",
  [ValidateSet("direct-db", "relay")]
  [string]$EventSink = "direct-db",
  [string]$RelayUrl = "http://127.0.0.1:18090/events",
  [int]$Limit = 3,
  [int]$EveryMinutes = 60,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [switch]$NoInitialRun,
  [switch]$Once,
  [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$runScript = Join-Path $PSScriptRoot "run_international_homepage_headlines.ps1"
$logDir = Join-Path $ProjectRoot "runtime\logs"
$statusDir = Join-Path $ProjectRoot "runtime\status"
$logFile = Join-Path $logDir ("international-homepage-headlines-window-{0}.log" -f (Get-Date).ToString("yyyyMMdd"))
$statusFile = Join-Path $statusDir "international-homepage-headlines-window-status.json"

if ($EveryMinutes -lt 30) {
  throw "EveryMinutes must be at least 30 for public homepage headline sources."
}
if (-not (Test-Path -LiteralPath $runScript)) {
  throw "run_international_homepage_headlines.ps1 not found: $runScript"
}

New-Item -ItemType Directory -Force -Path $logDir, $statusDir | Out-Null

function Write-HomepageLog {
  param(
    [string]$Message,
    [ConsoleColor]$Color = "Gray"
  )

  $line = "[{0}] {1}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $Message
  Write-Host $line -ForegroundColor $Color
  Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Write-HomepageState {
  param(
    [string]$LastJob,
    [int]$LastExitCode,
    [datetime]$NextRun
  )

  [ordered]@{
    updated_at = (Get-Date).ToString("o")
    pid = $PID
    last_job = $LastJob
    last_exit_code = $LastExitCode
    next_run = $NextRun.ToString("o")
    limit = $Limit
    event_sink = $EventSink
    log_file = $logFile
  } | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8
}

function Invoke-HomepageHeadlines {
  Write-HomepageLog "Starting international homepage headline crawl (limit=$Limit, log=$LogLevel)..." Cyan

  $runArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $runScript,
    "-EnvFile", $EnvFile,
    "-EventSink", $EventSink,
    "-RelayUrl", $RelayUrl,
    "-Limit", $Limit,
    "-LogLevel", $LogLevel
  )

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & powershell.exe @runArgs 2>&1 |
      ForEach-Object { Write-HomepageLog ([string]$_) }
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  if ($null -eq $exitCode) {
    $exitCode = 0
  }

  if ($exitCode -eq 0) {
    Write-HomepageLog "International homepage headline crawl finished." Green
  } else {
    Write-HomepageLog "International homepage headline crawl failed with exit code $exitCode; the fixed window will keep running." Red
  }

  return $exitCode
}

if ($PlanOnly) {
  Write-HomepageLog "Plan only: international homepage fixed window would run from $ProjectRoot." Cyan
  Write-HomepageLog "Cadence: every $EveryMinutes minutes."
  exit 0
}

$mutex = [System.Threading.Mutex]::new($false, "Global\NewsCollectorInternationalHomepageHeadlinesWindow")
if (-not $mutex.WaitOne(0)) {
  Write-HomepageLog "Another international homepage headline window is already running. Exiting duplicate launcher." Yellow
  exit 0
}

try {
  try {
    [Console]::Title = "NewsCollector international homepage headlines"
  } catch {
  }

  Set-Location -LiteralPath $ProjectRoot
  Write-HomepageLog "International homepage headline fixed window started. Close this window to stop the local schedule." Green
  Write-HomepageLog "Cadence: $EveryMinutes minutes."
  Write-HomepageLog "Log file: $logFile"
  Write-HomepageLog "Status file: $statusFile"

  $interval = New-TimeSpan -Minutes $EveryMinutes
  $now = Get-Date
  $nextRun = if ($NoInitialRun) { $now.Add($interval) } else { $now }
  Write-HomepageState -LastJob "startup" -LastExitCode 0 -NextRun $nextRun

  do {
    $now = Get-Date
    if ($now -ge $nextRun) {
      $exitCode = Invoke-HomepageHeadlines
      $nextRun = (Get-Date).Add($interval)
      Write-HomepageState -LastJob "international_homepage_headlines" -LastExitCode $exitCode -NextRun $nextRun
    }

    if ($Once) {
      break
    }

    Write-HomepageLog ("Next international homepage headline run={0}" -f $nextRun.ToString("HH:mm:ss"))
    $sleepSeconds = [Math]::Max(5, [Math]::Min(30, [int][Math]::Ceiling(($nextRun - (Get-Date)).TotalSeconds)))
    Start-Sleep -Seconds $sleepSeconds
  } while ($true)
} finally {
  $mutex.ReleaseMutex()
  $mutex.Dispose()
}
