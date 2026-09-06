# Restart relay, source bridge, and news-platform loop as hidden service wrappers.
param(
  [string]$EnvFile = ".env",
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

# Stop existing relay/bridge/news-platform wrappers and python children first.
$processes = @(Get-CimInstance Win32_Process)
$targetPids = [System.Collections.Generic.HashSet[int]]::new()

function Test-LiveWorkerPython {
  param(
    [string]$Name,
    [string]$CommandLine
  )

  if ([string]::IsNullOrWhiteSpace($CommandLine) -or $Name -notmatch '^python(3\.\d+)?(\.exe)?$') {
    return $false
  }

  return (
    $CommandLine -match 'event_relay\.main' -or
    $CommandLine -match 'news_collector\.relay_bridge' -or
    ($CommandLine -match 'news_platform\.main' -and $CommandLine -match '--loop')
  )
}

function Test-LiveWorkerWrapper {
  param(
    [string]$Name,
    [string]$CommandLine
  )

  if ([string]::IsNullOrWhiteSpace($CommandLine) -or $Name -notmatch '^(powershell|pwsh)(\.exe)?$') {
    return $false
  }
  if (-not $CommandLine.Contains("-NoExit")) {
    return $false
  }

  $knownScript = (
    $CommandLine.Contains("run_event_relay.ps1") -or
    $CommandLine.Contains("run_source_bridge.ps1") -or
    $CommandLine.Contains("run_news_platform_loop.ps1") -or
    ($CommandLine.Contains("news_platform.main") -and $CommandLine.Contains("--loop"))
  )
  if (-not $knownScript) {
    return $false
  }

  return (
    $CommandLine.Contains($ProjectRoot) -or
    $CommandLine -match '(?i)-File\s+\.\\scripts\\run_(event_relay|source_bridge|news_platform_loop)\.ps1'
  )
}

function Add-ChildProcesses {
  param([int]$RootPid)

  $children = @($processes | Where-Object { [int]$_.ParentProcessId -eq $RootPid })
  foreach ($child in $children) {
    if ($targetPids.Add([int]$child.ProcessId)) {
      Add-ChildProcesses -RootPid ([int]$child.ProcessId)
    }
  }
}

$processes | Where-Object {
  (Test-LiveWorkerPython -Name $_.Name -CommandLine $_.CommandLine) -or
  (Test-LiveWorkerWrapper -Name $_.Name -CommandLine $_.CommandLine)
} | ForEach-Object {
  [void]$targetPids.Add([int]$_.ProcessId)
}

foreach ($targetPid in @($targetPids)) {
  Add-ChildProcesses -RootPid $targetPid
}

if ($targetPids.Count -gt 0) {
  $targetPids |
    Where-Object { $_ -ne $PID } |
    Sort-Object -Descending |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 1
}

# Run live workers in background wrappers. Operator-facing fixed windows are
# owned by the scheduled monitor/collector tasks instead.
$relayScript = Join-Path $PSScriptRoot "run_event_relay.ps1"
$bridgeScript = Join-Path $PSScriptRoot "run_source_bridge.ps1"
$platformScript = Join-Path $PSScriptRoot "run_news_platform_loop.ps1"

function Start-LiveWorker {
  param(
    [string]$ScriptPath,
    [string[]]$ExtraArguments = @()
  )

  $arguments = @(
    '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
    '-File', $ScriptPath
  )
  $arguments += $ExtraArguments

  Start-Process powershell -WorkingDirectory $ProjectRoot -ArgumentList $arguments -WindowStyle Hidden
}

Start-LiveWorker -ScriptPath $relayScript -ExtraArguments @(
  '-EnvFile', $EnvFile,
  '-LogLevel', $LogLevel
)
Start-LiveWorker -ScriptPath $bridgeScript -ExtraArguments @(
  '-EnvFile', $EnvFile,
  '-LogLevel', $LogLevel
)
Start-LiveWorker -ScriptPath $platformScript

Write-Host "Live service workers started in hidden background wrappers (relay + source bridge + news-platform loop)." -ForegroundColor Green
