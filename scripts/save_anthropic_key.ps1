param(
  [string]$ApiKey = "",
  [string]$FromEnvFile = "",
  [string]$OutputFile = ".secrets/anthropic_api_key.dpapi"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TargetPath = Join-Path $ProjectRoot $OutputFile
$TargetDir = Split-Path -Parent $TargetPath
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

if ([string]::IsNullOrWhiteSpace($ApiKey) -and -not [string]::IsNullOrWhiteSpace($FromEnvFile) -and (Test-Path -LiteralPath $FromEnvFile)) {
  $lines = Get-Content -LiteralPath $FromEnvFile
  foreach ($line in $lines) {
    if ($line -match '^\s*ANTHROPIC_API_KEY\s*=\s*(.+)\s*$') {
      $ApiKey = $Matches[1].Trim().Trim('"').Trim("'")
      break
    }
  }
}

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
  $secure = Read-Host "Enter Anthropic API key" -AsSecureString
} else {
  $secure = ConvertTo-SecureString $ApiKey -AsPlainText -Force
}

$encrypted = ConvertFrom-SecureString $secure
Set-Content -LiteralPath $TargetPath -Value $encrypted -Encoding utf8 -NoNewline
Write-Host "Encrypted key saved to $TargetPath"
