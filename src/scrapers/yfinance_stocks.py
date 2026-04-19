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


# ── 抓取單支股票 ─────────────────────────────────────────
def fetch_quote(symbol: str, name: str) -> dict | None:
    try:
        ticker = yf.Ticker(symbol)
        info   = ticker.fast_info  # 輕量版，不需要完整 info

        price       = getattr(info, "last_price",          None)
        prev_close  = getattr(info, "previous_close",      None)
        market_cap  = getattr(info, "market_cap",          None)
        volume      = getattr(info, "three_month_average_volume", None)
        currency    = getattr(info, "currency",            "")
        exchange    = getattr(info, "exchange",            "")

        if price is None:
            print(f"  [SKIP] {symbol}: no price data")
            return None

        change     = (price - prev_close) if prev_close else 0
        change_pct = round((change / prev_close * 100) if prev_close else 0, 2)

        return {
            "symbol":       symbol,
            "name":         name,
            "currency":     currency,
            "price":        round(float(price), 4),
            "prev_close":   round(float(prev_close), 4) if prev_close else None,
            "change":       round(float(change), 4),
            "change_pct":   change_pct,
            "volume":       int(volume) if volume else None,
            "market_cap":   int(market_cap) if market_cap else None,
            "exchange":     exchange,
        }
    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}")
        return None


# ── 抓取所有清單 ─────────────────────────────────────────
def fetch_all(watchlist: dict) -> dict:
    # 批次下載（更快，減少 API 請求次數）
    all_symbols = [s["symbol"] for stocks in watchlist.values() for s in stocks]
    name_map    = {s["symbol"]: s["name"] for stocks in watchlist.values() for s in stocks}
    cat_map     = {s["symbol"]: cat for cat, stocks in watchlist.items() for s in stocks}

    print(f"  批次下載 {len(all_symbols)} 支標的...")
    try:
        tickers = yf.Tickers(" ".join(all_symbols))
    except Exception as e:
        print(f"  [ERROR] 批次下載失敗: {e}")
        tickers = None

    result = {cat: [] for cat in watchlist}

    for symbol in all_symbols:
        name = name_map[symbol]
        cat  = cat_map[symbol]

        quote = fetch_quote(symbol, name)
        if quote:
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
