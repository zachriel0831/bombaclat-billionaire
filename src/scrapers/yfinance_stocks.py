"""
Yahoo Finance Stock Price Scraper
Source: yfinance Python library (handles auth automatically)
Output:
  1. data/stocks/stocks_YYYYMMDD_HHMMSS.json  ← alert_workflow 需要此檔案
  2. POST → http://localhost:18090/events     ← 市場快照推送至 MySQL

安裝依賴:
    pip install yfinance

執行:
    python scrapers/yfinance_stocks.py
"""

import json
import os
import sys
from datetime import datetime, timezone

# relay_client 在 src/ 下，確保可 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from relay_client import push_events

try:
    import yfinance as yf
except ImportError:
    print("[ERROR] yfinance 未安裝，執行: pip install yfinance")
    sys.exit(1)

try:
    import pandas as pd  # yfinance 自帶依賴
except ImportError:
    print("[ERROR] pandas 未安裝（yfinance 依賴），執行: pip install pandas")
    sys.exit(1)

# ── 監控清單 ────────────────────────────────────────────
WATCHLIST = {
    "taiwan": [
        {"symbol": "2330.TW", "name": "台積電"},
        {"symbol": "2317.TW", "name": "鴻海"},
        {"symbol": "2454.TW", "name": "聯發科"},
        {"symbol": "2308.TW", "name": "台達電"},
        {"symbol": "0050.TW", "name": "元大台灣50"},
    ],
    "us": [
        {"symbol": "NVDA",  "name": "Nvidia"},
        {"symbol": "AAPL",  "name": "Apple"},
        {"symbol": "MSFT",  "name": "Microsoft"},
        {"symbol": "TSLA",  "name": "Tesla"},
        {"symbol": "META",  "name": "Meta"},
    ],
    "crypto": [
        {"symbol": "BTC-USD", "name": "Bitcoin"},
        {"symbol": "ETH-USD", "name": "Ethereum"},
        {"symbol": "SOL-USD", "name": "Solana"},
    ],
    "index": [
        {"symbol": "^TWII",  "name": "台灣加權指數"},
        {"symbol": "^GSPC",  "name": "S&P 500"},
        {"symbol": "^IXIC",  "name": "Nasdaq"},
        {"symbol": "^DJI",   "name": "Dow Jones"},
    ],
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "stocks")


# ── 從 yf.download() 批次結果萃取單支 quote ───────────────
def _extract_quote_from_download(df, symbol: str, name: str) -> dict | None:
    """從 yf.download() 回傳的 DataFrame 萃取 symbol 的最新 quote。

    多 symbol 下載時 columns 為 MultiIndex (field, symbol)；
    單 symbol 下載時 columns 為單層。
    """
    try:
        if df is None or len(df) == 0:
            return None

        # 取出該 symbol 的 Close / Open / Volume 欄位
        if isinstance(df.columns, pd.MultiIndex):
            try:
                close_series  = df["Close"][symbol].dropna()
                volume_series = df["Volume"][symbol].dropna() if "Volume" in df.columns.get_level_values(0) else None
            except KeyError:
                return None
        else:
            # 單 symbol 情境
            close_series  = df["Close"].dropna() if "Close" in df.columns else None
            volume_series = df["Volume"].dropna() if "Volume" in df.columns else None

        if close_series is None or len(close_series) == 0:
            return None

        price       = float(close_series.iloc[-1])
        prev_close  = float(close_series.iloc[-2]) if len(close_series) >= 2 else None
        volume_val  = None
        if volume_series is not None and len(volume_series) > 0:
            try:
                volume_val = int(volume_series.iloc[-1])
            except (ValueError, TypeError):
                volume_val = None

        change     = (price - prev_close) if prev_close else 0
        change_pct = round((change / prev_close * 100) if prev_close else 0, 2)

        return {
            "symbol":     symbol,
            "name":       name,
            "currency":   "",
            "price":      round(price, 4),
            "prev_close": round(prev_close, 4) if prev_close is not None else None,
            "change":     round(float(change), 4),
            "change_pct": change_pct,
            "volume":     volume_val,
            "market_cap": None,
            "exchange":   "",
        }
    except Exception as e:
        print(f"  [ERROR] {symbol}: extract failed: {e}")
        return None


# ── 抓取所有清單 ─────────────────────────────────────────
def fetch_all(watchlist: dict) -> dict:
    # 批次下載（更快，減少 API 請求次數）
    all_symbols = [s["symbol"] for stocks in watchlist.values() for s in stocks]
    name_map    = {s["symbol"]: s["name"] for stocks in watchlist.values() for s in stocks}
    cat_map     = {s["symbol"]: cat for cat, stocks in watchlist.items() for s in stocks}

    print(f"  批次下載 {len(all_symbols)} 支標的 (yf.download, period=5d)...")
    df = None
    try:
        df = yf.download(
            tickers=" ".join(all_symbols),
            period="5d",
            interval="1d",
            group_by="column",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception as e:
        print(f"  [ERROR] 批次下載失敗: {e}")
        df = None

    result = {cat: [] for cat in watchlist}

    for symbol in all_symbols:
        name = name_map[symbol]
        cat  = cat_map[symbol]

        quote = _extract_quote_from_download(df, symbol, name) if df is not None else None
        if quote is None:
            print(f"  [SKIP] {symbol}: no price data")
            continue

        result[cat].append(quote)
        price = quote["price"]
        pct   = quote["change_pct"]
        sign  = "▲" if pct >= 0 else "▼"
        print(f"    {name:10s} ({symbol:10s})  {price:>10.2f}  {sign}{abs(pct):.2f}%")

    return result


# ── 儲存 JSON（alert_workflow 需要此檔） ──────────────────
def save_json(data: dict, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"stocks_{timestamp}.json"
    filepath  = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


# ── 推送市場快照到 Relay（供查詢 MySQL 使用）─────────────
def push_snapshot_to_relay(stocks_data: dict, scraped_at: str):
    events = []
    for category, quotes in stocks_data.items():
        for q in quotes:
            if not q:
                continue
            price = q.get("price")
            pct   = q.get("change_pct", 0)
            sign  = "▲" if pct >= 0 else "▼"
            ts_compact = scraped_at[:16].replace("T", " ")
            title = (
                f"[{ts_compact}] {q['name']} ({q['symbol']}) "
                f"{price:.2f} {sign}{abs(pct):.2f}%"
            )
            url = f"https://finance.yahoo.com/quote/{q['symbol']}"
            events.append({
                "source":       f"yfinance_{category}",
                "title":        title,
                "url":          url,
                "summary":      json.dumps(q, ensure_ascii=False),
                "published_at": scraped_at,
            })

    if not events:
        print("  [relay] 無股價資料可推送")
        return

    result = push_events(events)
    if result["ok"]:
        print(f"  [relay] ✅ 股價快照 {len(events)} 筆 → MySQL")
    else:
        print(f"  [relay] ⚠️  {result.get('error')} — 略過股價快照推送")


# ── 主程式 ─────────────────────────────────────────────
def main():
    print("[Yahoo Finance] Fetching stock quotes via yfinance...")
    scraped_at  = datetime.now(timezone.utc).isoformat()
    stocks_data = fetch_all(WATCHLIST)
    total       = sum(len(v) for v in stocks_data.values())

    output = {
        "scraped_at":    scraped_at,
        "total_symbols": total,
        "data":          stocks_data,
    }

    # 1. 寫入 JSON（alert_workflow 使用）
    filepath = save_json(output, OUTPUT_DIR)
    print(f"\n[OK] {total} symbols saved → {filepath}")

    # 2. 推送快照到 Relay → MySQL
    push_snapshot_to_relay(stocks_data, scraped_at)


if __name__ == "__main__":
    main()
