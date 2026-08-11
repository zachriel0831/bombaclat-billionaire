# Run low-frequency news-platform source collection in one persistent console window.
param(
  [string]$EnvFile = ".env",
  [string]$SourceIds = "tvbs,udn,setn",
  [string]$Categories = "society,politics",
  [int]$Limit = 20,
  [int]$AuthorLimit = 30,
  [double]$AuthorSleepSeconds = 1.0,
  [int]$AuthorTimeoutSeconds = 15,
  [int]$EveryMinutes = 60,
  [switch]$SkipAuthorBackfill,
  [switch]$SkipKeywordsAndTopics,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [switch]$NoInitialRun,
  [switch]$Once,
  [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$runScript = Join-Path $PSScriptRoot "run_news_platform_low_frequency_sources.ps1"
$logDir = Join-Path $ProjectRoot "runtime\logs"
$statusDir = Join-Path $ProjectRoot "runtime\status"
$logFile = Join-Path $logDir ("news-platform-low-frequency-window-{0}.log" -f (Get-Date).ToString("yyyyMMdd"))
$statusFile = Join-Path $statusDir "news-platform-low-frequency-window-status.json"

if ($EveryMinutes -lt 15) {
  throw "EveryMinutes must be at least 15 for public HTML list sources."
}
if (-not (Test-Path -LiteralPath $runScript)) {
  throw "run_news_platform_low_frequency_sources.ps1 not found: $runScript"
}

New-Item -ItemType Directory -Force -Path $logDir, $statusDir | Out-Null

function Write-LowFrequencyLog {
  param(
    [string]$Message,
    [ConsoleColor]$Color = "Gray"
  )

  $line = "[{0}] {1}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $Message
  Write-Host $line -ForegroundColor $Color
  Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Write-LowFrequencyState {
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
    source_ids = $SourceIds
    categories = $Categories
    log_file = $logFile
  } | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8
}

function Invoke-LowFrequencySources {
  Write-LowFrequencyLog "Starting low-frequency news-platform sources (sources=$SourceIds, categories=$Categories, log=$LogLevel)..." Cyan

  $runArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $runScript,
    "-EnvFile", $EnvFile,
    "-SourceIds", $SourceIds,
    "-Categories", $Categories,
    "-Limit", $Limit,
    "-AuthorLimit", $AuthorLimit,
    "-AuthorSleepSeconds", $AuthorSleepSeconds,
    "-AuthorTimeoutSeconds", $AuthorTimeoutSeconds,
    "-LogLevel", $LogLevel
  )
  if ($SkipAuthorBackfill) {
    $runArgs += "-SkipAuthorBackfill"
  }
  if ($SkipKeywordsAndTopics) {
    $runArgs += "-SkipKeywordsAndTopics"
  }

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & powershell.exe @runArgs 2>&1 |
      ForEach-Object { Write-LowFrequencyLog ([string]$_) }
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  if ($null -eq $exitCode) {
    $exitCode = 0
  }

  if ($exitCode -eq 0) {
    Write-LowFrequencyLog "Low-frequency news-platform sources finished." Green
  } else {
    Write-LowFrequencyLog "Low-frequency news-platform sources failed with exit code $exitCode; the fixed window will keep running." Red
  }

  return $exitCode
}

if ($PlanOnly) {
  Write-LowFrequencyLog "Plan only: low-frequency source fixed window would run from $ProjectRoot." Cyan
  Write-LowFrequencyLog "Cadence: every $EveryMinutes minutes, sources=$SourceIds, categories=$Categories"
  exit 0
}

$mutex = [System.Threading.Mutex]::new($false, "Global\NewsCollectorLowFrequencySourcesWindow")
if (-not $mutex.WaitOne(0)) {
  Write-LowFrequencyLog "Another low-frequency source fixed window is already running. Exiting duplicate launcher." Yellow
  exit 0
}

try {
  try {
    [Console]::Title = "NewsCollector low-frequency news sources"
  } catch {
  }

  Set-Location -LiteralPath $ProjectRoot
  Write-LowFrequencyLog "Low-frequency source fixed window started. Close this window to stop the local schedule." Green
  Write-LowFrequencyLog "Cadence: $EveryMinutes minutes."
  Write-LowFrequencyLog "Log file: $logFile"
  Write-LowFrequencyLog "Status file: $statusFile"

  $interval = New-TimeSpan -Minutes $EveryMinutes
  $now = Get-Date
  $nextRun = if ($NoInitialRun) { $now.Add($interval) } else { $now }
  Write-LowFrequencyState -LastJob "startup" -LastExitCode 0 -NextRun $nextRun

  do {
    $now = Get-Date
    if ($now -ge $nextRun) {
      $exitCode = Invoke-LowFrequencySources
      $nextRun = (Get-Date).Add($interval)
      Write-LowFrequencyState -LastJob "low_frequency_sources" -LastExitCode $exitCode -NextRun $nextRun
    }

    if ($Once) {
      break
    }

    Write-LowFrequencyLog ("Next low-frequency source run={0}" -f $nextRun.ToString("HH:mm:ss"))
    $sleepSeconds = [Math]::Max(5, [Math]::Min(30, [int][Math]::Ceiling(($nextRun - (Get-Date)).TotalSeconds)))
    Start-Sleep -Seconds $sleepSeconds
  } while ($true)
} finally {
  $mutex.ReleaseMutex()
  $mutex.Dispose()
}
