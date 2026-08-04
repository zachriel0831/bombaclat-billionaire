# Run CWA typhoon/earthquake collectors in one persistent console window.
param(
  [string]$EnvFile = ".env",
  [int]$WeatherEveryMinutes = 30,
  [int]$EarthquakeEveryMinutes = 5,
  [int]$WeatherLimit = 20,
  [int]$EarthquakeLimit = 50,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [switch]$NoInitialRun,
  [switch]$Once,
  [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$weatherScript = Join-Path $PSScriptRoot "run_cwa_weather.ps1"
$earthquakeScript = Join-Path $PSScriptRoot "run_cwa_earthquake.ps1"
$logDir = Join-Path $ProjectRoot "runtime\logs"
$statusDir = Join-Path $ProjectRoot "runtime\status"
$logFile = Join-Path $logDir ("cwa-fixed-window-{0}.log" -f (Get-Date).ToString("yyyyMMdd"))
$statusFile = Join-Path $statusDir "cwa-fixed-window-status.json"

if ($WeatherEveryMinutes -lt 1) {
  throw "WeatherEveryMinutes must be at least 1."
}
if ($EarthquakeEveryMinutes -lt 1) {
  throw "EarthquakeEveryMinutes must be at least 1."
}
if (-not (Test-Path -LiteralPath $weatherScript)) {
  throw "run_cwa_weather.ps1 not found: $weatherScript"
}
if (-not (Test-Path -LiteralPath $earthquakeScript)) {
  throw "run_cwa_earthquake.ps1 not found: $earthquakeScript"
}

New-Item -ItemType Directory -Force -Path $logDir, $statusDir | Out-Null

function Write-CwaStatus {
  param(
    [string]$Message,
    [ConsoleColor]$Color = "Gray"
  )

  $line = "[{0}] {1}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $Message
  Write-Host $line -ForegroundColor $Color
  Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Write-CwaState {
  param(
    [string]$LastJob,
    [int]$LastExitCode,
    [datetime]$NextWeather,
    [datetime]$NextEarthquake
  )

  [ordered]@{
    updated_at = (Get-Date).ToString("o")
    pid = $PID
    last_job = $LastJob
    last_exit_code = $LastExitCode
    next_weather = $NextWeather.ToString("o")
    next_earthquake = $NextEarthquake.ToString("o")
    log_file = $logFile
  } | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8
}

function Invoke-CwaScript {
  param(
    [string]$Name,
    [string]$ScriptPath,
    [int]$Limit
  )

  Write-CwaStatus "Starting $Name (limit=$Limit, log=$LogLevel)..." Cyan
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath -EnvFile $EnvFile -Limit $Limit -LogLevel $LogLevel 2>&1 |
    ForEach-Object { Write-CwaStatus $_ }
  $exitCode = $LASTEXITCODE
  if ($null -eq $exitCode) {
    $exitCode = 0
  }

  if ($exitCode -eq 0) {
    Write-CwaStatus "$Name finished." Green
  } else {
    Write-CwaStatus "$Name failed with exit code $exitCode; the fixed window will keep running." Red
  }

  return $exitCode
}

if ($PlanOnly) {
  Write-CwaStatus "Plan only: CWA fixed window would run from $ProjectRoot." Cyan
  Write-CwaStatus "Weather: every $WeatherEveryMinutes minutes, limit=$WeatherLimit, script=$weatherScript"
  Write-CwaStatus "Earthquake: every $EarthquakeEveryMinutes minutes, limit=$EarthquakeLimit, script=$earthquakeScript"
  exit 0
}

$mutex = [System.Threading.Mutex]::new($false, "Global\NewsCollectorCwaFixedWindow")
if (-not $mutex.WaitOne(0)) {
  Write-CwaStatus "Another CWA fixed window is already running. Exiting duplicate launcher." Yellow
  exit 0
}

try {
  try {
    [Console]::Title = "NewsCollector CWA fixed window"
  } catch {
  }

  Set-Location -LiteralPath $ProjectRoot
  Write-CwaStatus "CWA fixed window started. Close this window to stop the local schedule." Green
  Write-CwaStatus "Weather cadence: $WeatherEveryMinutes minutes; earthquake cadence: $EarthquakeEveryMinutes minutes."
  Write-CwaStatus "Log file: $logFile"
  Write-CwaStatus "Status file: $statusFile"

  $weatherInterval = New-TimeSpan -Minutes $WeatherEveryMinutes
  $earthquakeInterval = New-TimeSpan -Minutes $EarthquakeEveryMinutes
  $now = Get-Date
  $nextWeather = if ($NoInitialRun) { $now.Add($weatherInterval) } else { $now }
  $nextEarthquake = if ($NoInitialRun) { $now.Add($earthquakeInterval) } else { $now }
  Write-CwaState -LastJob "startup" -LastExitCode 0 -NextWeather $nextWeather -NextEarthquake $nextEarthquake

  do {
    $now = Get-Date
    if ($now -ge $nextWeather) {
      $exitCode = Invoke-CwaScript -Name "CWA weather/typhoon" -ScriptPath $weatherScript -Limit $WeatherLimit
      $afterRun = Get-Date
      $nextWeather = $afterRun.Add($weatherInterval)
      if ($nextEarthquake -le $afterRun) {
        $nextEarthquake = $afterRun.Add($earthquakeInterval)
      }
      Write-CwaState -LastJob "weather" -LastExitCode $exitCode -NextWeather $nextWeather -NextEarthquake $nextEarthquake
    } elseif ($now -ge $nextEarthquake) {
      $exitCode = Invoke-CwaScript -Name "CWA earthquake" -ScriptPath $earthquakeScript -Limit $EarthquakeLimit
      $nextEarthquake = (Get-Date).Add($earthquakeInterval)
      Write-CwaState -LastJob "earthquake" -LastExitCode $exitCode -NextWeather $nextWeather -NextEarthquake $nextEarthquake
    }

    if ($Once) {
      break
    }

    $nextRun = @($nextWeather, $nextEarthquake) | Sort-Object | Select-Object -First 1
    Write-CwaStatus ("Next weather={0}; earthquake={1}" -f $nextWeather.ToString("HH:mm:ss"), $nextEarthquake.ToString("HH:mm:ss"))
    $sleepSeconds = [Math]::Max(5, [Math]::Min(30, [int][Math]::Ceiling(($nextRun - (Get-Date)).TotalSeconds)))
    Start-Sleep -Seconds $sleepSeconds
  } while ($true)
} finally {
  $mutex.ReleaseMutex()
  $mutex.Dispose()
}
