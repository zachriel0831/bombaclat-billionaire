# Restart relay and source bridge in two visible PowerShell windows.
param(
  [string]$EnvFile = ".env",
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

# Stop existing relay/bridge python processes first.
$targets = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^python(3\.12)?(\.exe)?$' -and (
    $_.CommandLine -match 'event_relay\.main' -or
    $_.CommandLine -match 'news_collector\.relay_bridge'
  )
}
if ($targets) {
  $targets | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}

# Run scripts directly in each opened window so logs stream live there.
$relayCmd = "Set-Location '$ProjectRoot'; & '.\scripts\run_event_relay.ps1' -EnvFile '$EnvFile' -LogLevel '$LogLevel'"
$bridgeCmd = "Set-Location '$ProjectRoot'; & '.\scripts\run_source_bridge.ps1' -EnvFile '$EnvFile' -LogLevel '$LogLevel'"

Start-Process powershell -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $relayCmd) -WindowStyle Normal
Start-Process powershell -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $bridgeCmd) -WindowStyle Normal

Write-Host "Live service windows started (relay + source bridge)." -ForegroundColor Green
