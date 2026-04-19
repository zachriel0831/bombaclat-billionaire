# Start multi-source bridge and forward events to relay.
param(
  [string]$RelayUrl = "http://127.0.0.1:18090/events",
  [int]$PollIntervalSeconds = 300,
  [int]$Limit = 5,
  [int]$XStreamTimeoutSeconds = 90,
  [int]$XStreamReconnectMaxSeconds = 120,
  [int]$UsIndexPollIntervalSeconds = 30,
  [switch]$DisableUsIndex,
  [string]$EnvFile = ".env",
  [string]$PythonExe = "",
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"
$ResolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $ProjectRoot $EnvFile }

function Resolve-PythonExe {
  param([string]$RequestedPath)

  if (-not [string]::IsNullOrWhiteSpace($RequestedPath) -and (Test-Path -LiteralPath $RequestedPath)) {
    return $RequestedPath
  }

  $candidates = @(
    "C:\Users\Zack Ou\AppData\Local\Programs\Python\Python313\python.exe",
    "C:\Users\Zack Ou\AppData\Local\Programs\Python\Python312\python.exe",
    "C:\Users\Zack Ou\AppData\Local\Programs\Python\Python311\python.exe"
  )

  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return $candidate
    }
  }

  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCmd -and $pythonCmd.Source -notmatch 'WindowsApps\\python\.exe$') {
    return $pythonCmd.Source
  }

  throw "Unable to locate a real python.exe. Pass -PythonExe explicitly."
}

function Get-EnvFileMap {
  param([string]$Path)

  $map = @{}
  if (-not (Test-Path -LiteralPath $Path)) {
    return $map
  }

  foreach ($line in Get-Content -LiteralPath $Path) {
    $text = $line.Trim()
    if ([string]::IsNullOrWhiteSpace($text) -or $text.StartsWith('#') -or -not $text.Contains('=')) {
      continue
    }

    $parts = $text.Split('=', 2)
    $key = $parts[0].Trim()
    $value = $parts[1].Trim().Trim('"').Trim("'")
    if (-not [string]::IsNullOrWhiteSpace($key)) {
      $map[$key] = $value
    }
  }
  return $map
}

function Resolve-DpapiSecret {
  param([string]$SecretPath)

  if ([string]::IsNullOrWhiteSpace($SecretPath) -or -not (Test-Path -LiteralPath $SecretPath)) {
    return $null
  }

  try {
    $enc = Get-Content -Raw -LiteralPath $SecretPath
    $secure = ConvertTo-SecureString $enc
    return [System.Net.NetworkCredential]::new('', $secure).Password
  }
  catch {
    return $null
  }
}

function Resolve-SecretValue {
  param(
    [hashtable]$EnvMap,
    [string]$InlineKey,
    [string]$FileKey,
    [string]$DefaultRelativeFile
  )

  $inlineValue = [Environment]::GetEnvironmentVariable($InlineKey, 'Process')
  if ([string]::IsNullOrWhiteSpace($inlineValue) -and $EnvMap.ContainsKey($InlineKey)) {
    $inlineValue = $EnvMap[$InlineKey]
  }
  if (-not [string]::IsNullOrWhiteSpace($inlineValue)) {
    return $inlineValue
  }

  $secretFile = $null
  if ($EnvMap.ContainsKey($FileKey) -and -not [string]::IsNullOrWhiteSpace($EnvMap[$FileKey])) {
    $secretFile = $EnvMap[$FileKey]
  }
  elseif (-not [string]::IsNullOrWhiteSpace($DefaultRelativeFile)) {
    $secretFile = $DefaultRelativeFile
  }

  if ([string]::IsNullOrWhiteSpace($secretFile)) {
    return $null
  }
  if (-not [System.IO.Path]::IsPathRooted($secretFile)) {
    $secretFile = Join-Path $ProjectRoot $secretFile
  }

  return Resolve-DpapiSecret -SecretPath $secretFile
}

$OutputDir = Join-Path $ProjectRoot "runtime\logs"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$OutLogFile = Join-Path $OutputDir "source-bridge-$Timestamp.out.log"
$ErrLogFile = Join-Path $OutputDir "source-bridge-$Timestamp.err.log"
$ResolvedPythonExe = Resolve-PythonExe -RequestedPath $PythonExe
$EnvMap = Get-EnvFileMap -Path $ResolvedEnvFile

$resolvedXToken = Resolve-SecretValue -EnvMap $EnvMap -InlineKey "X_BEARER_TOKEN" -FileKey "X_BEARER_TOKEN_FILE" -DefaultRelativeFile ".secrets/x_bearer_token.dpapi"
if (-not [string]::IsNullOrWhiteSpace($resolvedXToken)) {
  $env:X_BEARER_TOKEN = $resolvedXToken
}

Write-Host "Starting source bridge (X stream + RSS polling + US index stored-only events -> LINE relay)..." -ForegroundColor Cyan
Write-Host "Python executable: $ResolvedPythonExe" -ForegroundColor DarkGray
Write-Host "Env file: $ResolvedEnvFile" -ForegroundColor DarkGray
Write-Host ("X token preflight: " + $(if ([string]::IsNullOrWhiteSpace($resolvedXToken)) { "missing" } else { "resolved" })) -ForegroundColor DarkGray
Write-Host "Output log: $OutLogFile" -ForegroundColor DarkGray
Write-Host "Error log: $ErrLogFile" -ForegroundColor DarkGray

$cmdArgs = @(
  "-m", "news_collector.relay_bridge",
  "--relay-url", $RelayUrl,
  "--poll-interval-seconds", "$PollIntervalSeconds",
  "--limit", "$Limit",
  "--env-file", $ResolvedEnvFile,
  "--x-stream-timeout-seconds", "$XStreamTimeoutSeconds",
  "--x-stream-reconnect-max-seconds", "$XStreamReconnectMaxSeconds",
  "--us-index-poll-interval-seconds", "$UsIndexPollIntervalSeconds",
  "--log-level", $LogLevel
)
if ($DisableUsIndex) {
  $cmdArgs += "--disable-us-index"
}

& $ResolvedPythonExe @cmdArgs 2> $ErrLogFile | Tee-Object -FilePath $OutLogFile
exit $LASTEXITCODE
