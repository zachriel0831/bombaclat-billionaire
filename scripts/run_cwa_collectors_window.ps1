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

function Write-CwaStatus {
  param(
    [string]$Message,
    [ConsoleColor]$Color = "Gray"
  )

  Write-Host ("[{0}] {1}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $Message) -ForegroundColor $Color
}

function Invoke-CwaScript {
  param(
    [string]$Name,
    [string]$ScriptPath,
    [int]$Limit
  )

  Write-CwaStatus "Starting $Name (limit=$Limit, log=$LogLevel)..." Cyan
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath -EnvFile $EnvFile -Limit $Limit -LogLevel $LogLevel
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

  $weatherInterval = New-TimeSpan -Minutes $WeatherEveryMinutes
  $earthquakeInterval = New-TimeSpan -Minutes $EarthquakeEveryMinutes
  $now = Get-Date
  $nextWeather = if ($NoInitialRun) { $now.Add($weatherInterval) } else { $now }
  $nextEarthquake = if ($NoInitialRun) { $now.Add($earthquakeInterval) } else { $now }

  do {
    $now = Get-Date
    if ($now -ge $nextWeather) {
      [void](Invoke-CwaScript -Name "CWA weather/typhoon" -ScriptPath $weatherScript -Limit $WeatherLimit)
      $afterRun = Get-Date
      $nextWeather = $afterRun.Add($weatherInterval)
      if ($nextEarthquake -le $afterRun) {
        $nextEarthquake = $afterRun.Add($earthquakeInterval)
      }
    } elseif ($now -ge $nextEarthquake) {
      [void](Invoke-CwaScript -Name "CWA earthquake" -ScriptPath $earthquakeScript -Limit $EarthquakeLimit)
      $nextEarthquake = (Get-Date).Add($earthquakeInterval)
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
