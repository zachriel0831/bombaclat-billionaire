﻿param(
  [string]$ApiKey = "",
  [string]$OutputFile = ".secrets/benzinga_api_key.dpapi"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TargetPath = Join-Path $ProjectRoot $OutputFile
$TargetDir = Split-Path -Parent $TargetPath
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
  # 不在命令列帶 key 時，可用安全輸入避免留在 shell history。
  $secure = Read-Host "Enter Benzinga API key" -AsSecureString
} else {
  $secure = ConvertTo-SecureString $ApiKey -AsPlainText -Force
}

$encrypted = ConvertFrom-SecureString $secure
Set-Content -LiteralPath $TargetPath -Value $encrypted -Encoding utf8 -NoNewline

Write-Host "Encrypted key saved to $TargetPath"
