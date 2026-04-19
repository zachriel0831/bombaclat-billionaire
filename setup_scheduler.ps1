<#
.SYNOPSIS
    向 Windows 工作排程器註冊 "Run Scrapers" 任務
    每 10 分鐘執行一次 run_scrapers.bat

.USAGE
    以系統管理員身份執行 PowerShell，然後：
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\setup_scheduler.ps1

    移除任務：
    .\setup_scheduler.ps1 -Unregister
#>

param(
    [switch]$Unregister
)

$TaskName   = "DataCollecting-RunScrapers"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$BatFile    = Join-Path $ScriptDir "run_scrapers.bat"
$LogFile    = Join-Path $ScriptDir "logs\scheduler.log"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[OK] Task '$TaskName' removed."
    exit 0
}

# ── 確認 bat 檔存在 ─────────────────────────────────────
if (-not (Test-Path $BatFile)) {
    Write-Error "找不到 run_scrapers.bat: $BatFile"
    exit 1
}

# ── 建立 logs 目錄 ────────────────────────────────────────
$LogDir = Join-Path $ScriptDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# ── 動作：每次觸發執行 run_scrapers.bat ──────────────────
$Action  = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatFile`" >> `"$LogFile`" 2>&1"

# ── 觸發：每 10 分鐘（從現在起），永不過期 ────────────────
$Trigger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration ([TimeSpan]::MaxValue) `
    -Once `
    -At (Get-Date)

# ── 設定：只在使用者登入時執行，允許隨需執行 ────────────
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

# ── 以當前使用者身份執行 ─────────────────────────────────
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Highest

# ── 註冊 ─────────────────────────────────────────────────
$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "每 10 分鐘執行 data-collecting 爬蟲，寫入 MySQL (news) 及 JSON (stocks)"

Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null

Write-Host ""
Write-Host "=============================================="
Write-Host "  [OK] Task '$TaskName' registered"
Write-Host "  Interval : every 10 minutes"
Write-Host "  Script   : $BatFile"
Write-Host "  Log      : $LogFile"
Write-Host "=============================================="
Write-Host ""
Write-Host "  立即測試執行："
Write-Host "    Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "  查看任務狀態："
Write-Host "    Get-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "  移除任務："
Write-Host "    .\setup_scheduler.ps1 -Unregister"
