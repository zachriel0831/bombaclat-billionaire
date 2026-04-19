@echo off
title Summary Sender - LINE Dispatcher
cd /d "%~dp0"
echo [Summary Sender] Starting watch mode...
echo Waiting for summaries in data\summaries\pending\
echo.
python src/workflows/summary_sender.py --watch
pause
