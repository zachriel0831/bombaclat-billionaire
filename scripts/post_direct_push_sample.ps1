# 測試 relay direct push：不經 t_relay_events，直接推送到指定使用者。
param(
  [string]$RelayDirectPushUrl = "http://127.0.0.1:18090/push/direct",
  [string]$Source = "manual_direct_test"
)

$ErrorActionPreference = "Stop"
$payload = @{
  source = $Source
  title = "direct push local test"
  text = "[US_INDEX_TEST] this is a direct push test\nhttps://finance.yahoo.com/quote/%5EDJI"
}

$body = $payload | ConvertTo-Json -Depth 8 -Compress
Write-Host "POST $RelayDirectPushUrl" -ForegroundColor Cyan

$resp = Invoke-RestMethod -Method Post -Uri $RelayDirectPushUrl -Body $body -ContentType "application/json"
$resp | ConvertTo-Json -Depth 8
