@echo off
setlocal
cd /d "%~dp0"

echo [%date% %time%] ===== Run Scrapers Start =====

:: 確認依賴
echo [%date% %time%] Checking dependencies...
pip install yfinance requests beautifulsoup4 lxml -q

:: 新聞爬蟲 → MySQL (via relay)
echo [%date% %time%] BBC Business...
python src\scrapers\bbc_business.py
if errorlevel 1 echo [WARN] bbc_business failed

echo [%date% %time%] Reuters RSS...
python src\scrapers\reuters_rss.py
if errorlevel 1 echo [WARN] reuters_rss failed

:: 股價爬蟲 → JSON + MySQL snapshot
echo [%date% %time%] Yahoo Finance Stocks (yfinance)...
python src\scrapers\yfinance_stocks.py
if errorlevel 1 echo [WARN] yfinance_stocks failed

echo [%date% %time%] ===== Run Scrapers Done =====
endlocal
