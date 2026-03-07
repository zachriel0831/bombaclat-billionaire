# 本地模擬 LINE webhook：使用 channel secret 產生簽章後送到 relay。
param(
  [string]$EnvFile = ".env",
  [string]$WebhookUrl = "http://127.0.0.1:18090/line/webhook",
  [string]$UserId = "U_LOCAL_TEST",
  [string]$GroupId = ""
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

$secret = Get-EnvValue -Path $EnvFile -Key "LINE_CHANNEL_SECRET"
if ([string]::IsNullOrWhiteSpace($secret)) {
  throw "Missing LINE_CHANNEL_SECRET in $EnvFile"
}

$source = if ([string]::IsNullOrWhiteSpace($GroupId)) {
  @{ type = "user"; userId = $UserId }
} else {
  @{ type = "group"; groupId = $GroupId; userId = $UserId }
}

$payload = @{
  destination = "local"
  events = @(
    @{
      type = "follow"
      timestamp = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
      source = $source
    }
  )
}

$body = $payload | ConvertTo-Json -Depth 8 -Compress
$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [Text.Encoding]::UTF8.GetBytes($secret)
$hashBytes = $hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($body))
$signature = [Convert]::ToBase64String($hashBytes)

$headers = @{ "x-line-signature" = $signature }
Write-Host "POST $WebhookUrl" -ForegroundColor Cyan
Write-Host "payload: $body" -ForegroundColor DarkGray

$resp = Invoke-RestMethod -Method Post -Uri $WebhookUrl -Headers $headers -Body $body -ContentType "application/json"
Write-Host "Webhook accepted." -ForegroundColor Green
$resp | ConvertTo-Json -Depth 8
