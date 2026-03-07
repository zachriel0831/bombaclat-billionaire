﻿param(
  [string]$BearerToken = "",
  [string]$OutputFile = ".secrets/x_bearer_token.dpapi"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TargetPath = Join-Path $ProjectRoot $OutputFile
$TargetDir = Split-Path -Parent $TargetPath
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

if ([string]::IsNullOrWhiteSpace($BearerToken)) {
  # 互動式輸入可避免 token 出現在 shell history。
  $secure = Read-Host "Enter X Bearer token" -AsSecureString
} else {
  $secure = ConvertTo-SecureString $BearerToken -AsPlainText -Force
}

$encrypted = ConvertFrom-SecureString $secure
Set-Content -LiteralPath $TargetPath -Value $encrypted -Encoding utf8 -NoNewline

Write-Host "Encrypted token saved to $TargetPath"
