@echo off
title LINE Event Relay (MySQL Store)
cd /d "%~dp0"

echo ============================================
echo  LINE Event Relay Service
echo  Port  : 18090
echo  MySQL : news_relay.t_relay_events
echo  Push  : DRY_RUN (LINE push disabled)
echo  POST /events  → store to MySQL only
echo ============================================
echo.

python -m event_relay.main --env-file .env
pause
