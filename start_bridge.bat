@echo off
title News Collector Bridge (RSS + GDELT + Benzinga + X)
cd /d "%~dp0"

echo ============================================
echo  News Collector Bridge
echo  RSS/GDELT  : poll every 5 min
echo  Benzinga   : websocket stream (need API key)
echo  X (Twitter): @elonmusk, @realDonaldTrump
echo  US Index   : open/close tracker
echo  → all POST to http://127.0.0.1:18090/events
echo ============================================
echo.
echo [提醒] 請確認 .env 已填入：
echo   X_BEARER_TOKEN=xxxx
echo   BENZINGA_API_KEY=xxxx  (選填)
echo.

powershell -ExecutionPolicy Bypass -File ".\scripts\run_source_bridge.ps1" ^
    -EnvFile ".env" ^
    -PollIntervalSeconds 300 ^
    -Limit 10 ^
    -LogLevel INFO

pause
