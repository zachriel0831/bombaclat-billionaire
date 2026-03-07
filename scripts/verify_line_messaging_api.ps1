# 本地驗證 LINE Messaging API：只檢查 token 可用性，不推送訊息。
param(
  [string]$EnvFile = ".env",
  [string]$AccessToken = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

function Get-EnvValue {
  param(
    [string]$Path,
    [string]$Key
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    return ""
  }

  $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
  if (-not $line) {
    return ""
  }
  return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

$token = $AccessToken
if ([string]::IsNullOrWhiteSpace($token)) {
  $token = Get-EnvValue -Path $EnvFile -Key "LINE_CHANNEL_ACCESS_TOKEN"
}

if ([string]::IsNullOrWhiteSpace($token)) {
  throw "Missing LINE access token. Provide -AccessToken or set LINE_CHANNEL_ACCESS_TOKEN in $EnvFile"
}

$headers = @{
  Authorization = "Bearer $token"
}

Write-Host "Checking LINE Messaging API token..." -ForegroundColor Cyan
$resp = Invoke-RestMethod -Method Get -Uri "https://api.line.me/v2/bot/info" -Headers $headers

Write-Host "LINE Messaging API is reachable." -ForegroundColor Green
$resp | ConvertTo-Json -Depth 6
