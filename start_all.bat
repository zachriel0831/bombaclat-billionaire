@echo off
title Data Collecting - Start All Services
cd /d "%~dp0"

echo ============================================
echo  Data Collecting - Full Stack Startup
echo  1. LINE Event Relay  (port 18090, MySQL)
echo  2. News Collector Bridge (RSS/GDELT/X)
echo  3. Stock/News Scrapers  (every 10 min via Task Scheduler)
echo ============================================
echo.
echo [注意] 請先確認：
echo   1. MySQL 已啟動 (127.0.0.1:3306)
echo   2. .env 已填入 X_BEARER_TOKEN
echo   3. Windows Task Scheduler 已設定 (setup_scheduler.ps1)
echo.
pause

:: 1. Relay 服務（接收事件並寫入 MySQL）
start "Relay (port 18090)" cmd /k "cd /d %~dp0 && .\start_relay.bat"
timeout /t 3 /nobreak >nul

:: 2. News Collector Bridge（RSS/GDELT/Benzinga/X）
start "Bridge (RSS+GDELT+X)" cmd /k "cd /d %~dp0 && .\start_bridge.bat"

echo.
echo [OK] 2 services started
echo.
echo 服務說明：
echo   Relay   → 接收 POST /events，存 MySQL
echo   Bridge  → RSS/GDELT 每 5 分鐘 + X stream 即時
echo   Scrapers → Windows Task Scheduler 每 10 分鐘執行 run_scrapers.bat
echo.
echo 手動觸發爬蟲測試：
echo   .\run_scrapers.bat
echo.
pause
