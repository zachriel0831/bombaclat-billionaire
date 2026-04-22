﻿# 送出一筆測試事件到 relay（僅記錄日誌，不入庫）。
param(
  [string]$RelayUrl = "http://127.0.0.1:18090/events"
)

$body = @{
  id = "sample-001"
  source = "manual_test"
  title = "Sample event from local script"
  url = "https://example.com/news/sample"
  summary = "This is a local test event for the event relay service."
  published_at = (Get-Date).ToString("o")
  test_only = $true
}

$payload = $body | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Post -Uri $RelayUrl -ContentType "application/json" -Body $payload
