@echo off
title Data Collecting - Workers
cd /d "%~dp0"

echo ============================================
echo  Data Collecting - Worker Mode
echo  Workers: 認領 alert / 其他 workflow 任務
echo  ----------------------------------------
echo  爬蟲排程請使用 Windows Task Scheduler：
echo    執行 setup_scheduler.ps1 完成設定
echo    或手動執行 run_scrapers.bat
echo ============================================
echo.

start "Worker-1" cmd /k "cd /d %~dp0 && python src/worker.py --watch"
start "Worker-2" cmd /k "cd /d %~dp0 && python src/worker.py --watch"
start "Worker-3" cmd /k "cd /d %~dp0 && python src/worker.py --watch"

echo [OK] 3 workers started (price_alert / custom workflows)
echo News  → MySQL via LINE Relay Service (port 18090)
echo Stocks → data\stocks\ (JSON, for alert_workflow)
echo.
pause
