"""
Yahoo Finance Stock Price Scraper
Source: yfinance Python library (handles auth automatically)
Output:
  1. data/stocks/stocks_YYYYMMDD_HHMMSS.json  ← alert_workflow 需要此檔案
  2. POST → http://localhost:18090/quote-snapshots  ← 高頻報價快照寫專用表
  3. POST → http://localhost:18090/events           ← 僅顯著異動事件 (gap/sharp/volume_spike)

REQ-019 Phase B: 報價快照不再整批塞 t_relay_events，分流到
                  t_market_quote_snapshots；事件側只留 detect_movement_events
                  判定的有意義異動。

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
from relay_client import push_events, push_quote_snapshots
from event_relay.quote_movement import (
    MovementThresholds,
    QuoteContext,
    detect_movement_events,
)

try:
    import yfinance as yf
except ImportError as exc:
    yf = None
    _YFINANCE_IMPORT_ERROR = exc
else:
    _YFINANCE_IMPORT_ERROR = None

try:
    import pandas as pd  # yfinance 自帶依賴
except ImportError as exc:
    pd = None
    _PANDAS_IMPORT_ERROR = exc
else:
    _PANDAS_IMPORT_ERROR = None


def _require_optional_dependencies() -> None:
    """執行 require optional dependencies 的主要流程。"""
    missing = []
    if yf is None:
        missing.append("yfinance")
    if pd is None:
        missing.append("pandas")
    if missing:
        detail = "; ".join(str(exc) for exc in (_YFINANCE_IMPORT_ERROR, _PANDAS_IMPORT_ERROR) if exc)
        suffix = f" ({detail})" if detail else ""
        raise RuntimeError(f"Missing optional dependencies: {', '.join(missing)}. Run: pip install yfinance pandas{suffix}")

# ── 監控清單 ────────────────────────────────────────────
WATCHLIST = {
    "taiwan": [
        {"symbol": "2330.TW", "name": "台積電"},
        {"symbol": "2317.TW", "name": "鴻海"},
        {"symbol": "2454.TW", "name": "聯發科"},
        {"symbol": "2308.TW", "name": "台達電"},
        {"symbol": "2485.TW", "name": "兆赫"},
        {"symbol": "3535.TW", "name": "晶彩科"},
        {"symbol": "3715.TW", "name": "定穎投控"},
        {"symbol": "2351.TW", "name": "順德"},
        {"symbol": "4749.TWO", "name": "新應材"},
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
    "macro": [
        {"symbol": "^VIX",   "name": "VIX 恐慌指數"},
        {"symbol": "^TNX",   "name": "美10Y殖利率"},
        {"symbol": "^IRX",   "name": "美2Y殖利率"},
        {"symbol": "NKD=F",  "name": "日經期貨"},
    ],
    "forex_commodity": [
        {"symbol": "TWD=X",  "name": "USD/TWD"},
        {"symbol": "JPY=X",  "name": "USD/JPY"},
        {"symbol": "CL=F",   "name": "WTI原油"},
        {"symbol": "GC=F",   "name": "黃金"},
        {"symbol": "DX-Y.NYB", "name": "美元指數"},
    ],
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "stocks")


# ── 從 yf.download() 批次結果萃取單支 quote ───────────────
def _extract_field_series(df, field: str, symbol: str):
    """取出 extract field series 對應的資料或結果。"""
    if isinstance(df.columns, pd.MultiIndex):
        if field not in df.columns.get_level_values(0):
            return None
        try:
            return df[field][symbol].dropna()
        except KeyError:
            return None
    return df[field].dropna() if field in df.columns else None


def _extract_quote_from_download(df, symbol: str, name: str) -> dict | None:
    """Return latest quote dict + history context (n_day_avg_volume)."""
    try:
        if df is None or len(df) == 0:
            return None

        close_series  = _extract_field_series(df, "Close", symbol)
        open_series   = _extract_field_series(df, "Open", symbol)
        high_series   = _extract_field_series(df, "High", symbol)
        low_series    = _extract_field_series(df, "Low", symbol)
        volume_series = _extract_field_series(df, "Volume", symbol)

        if close_series is None or len(close_series) == 0:
            return None

        price       = float(close_series.iloc[-1])
        prev_close  = float(close_series.iloc[-2]) if len(close_series) >= 2 else None
        open_price  = float(open_series.iloc[-1])  if open_series  is not None and len(open_series) > 0 else None
        high_price  = float(high_series.iloc[-1])  if high_series  is not None and len(high_series) > 0 else None
        low_price   = float(low_series.iloc[-1])   if low_series   is not None and len(low_series) > 0 else None
        last_ts     = close_series.index[-1]

        volume_val: int | None = None
        n_day_avg_volume: float | None = None
        if volume_series is not None and len(volume_series) > 0:
            try:
                volume_val = int(volume_series.iloc[-1])
            except (ValueError, TypeError):
                volume_val = None
            # Average over the prior bars (exclude today to avoid self-comparison).
            prior = volume_series.iloc[:-1]
            if len(prior) > 0:
                try:
                    n_day_avg_volume = float(prior.mean())
                except (ValueError, TypeError):
                    n_day_avg_volume = None

        change     = (price - prev_close) if prev_close else 0
        change_pct = round((change / prev_close * 100) if prev_close else 0, 2)

        return {
            "symbol":           symbol,
            "name":             name,
            "currency":         "",
            "price":            round(price, 4),
            "open":             round(open_price, 4) if open_price is not None else None,
            "high":             round(high_price, 4) if high_price is not None else None,
            "low":              round(low_price, 4)  if low_price  is not None else None,
            "prev_close":       round(prev_close, 4) if prev_close is not None else None,
            "change":           round(float(change), 4),
            "change_pct":       change_pct,
            "volume":           volume_val,
            "n_day_avg_volume": n_day_avg_volume,
            "last_ts":          str(last_ts),
            "market_cap":       None,
            "exchange":         "",
        }
    except Exception as e:
        print(f"  [ERROR] {symbol}: extract failed: {e}")
        return None


# ── 抓取所有清單 ─────────────────────────────────────────
def fetch_all(watchlist: dict) -> dict:
    """抓取 fetch all 對應的資料或結果。"""
    _require_optional_dependencies()

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
    """執行 save json 的主要流程。"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"stocks_{timestamp}.json"
    filepath  = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


# ── 類別 → 市場代號 ───────────────────────────────────────
_CATEGORY_TO_MARKET = {
    "taiwan":          "TW",
    "us":              "US",
    "crypto":          "CRYPTO",
    "index":           "INDEX",
    "macro":           "MACRO",
    "forex_commodity": "FX",
}


def _build_snapshot_row(quote: dict, category: str, scraped_at: str, trade_date: str) -> dict:
    """建立 build snapshot row 對應的資料或結果。"""
    market = _CATEGORY_TO_MARKET.get(category, category.upper())
    return {
        "symbol":     quote["symbol"],
        "market":     market,
        "session":    "regular",
        "ts":         scraped_at[:19].replace("T", " "),
        "open_price": quote.get("open"),
        "high_price": quote.get("high"),
        "low_price":  quote.get("low"),
        "close_price": quote.get("price"),
        "prev_close": quote.get("prev_close"),
        "volume":     quote.get("volume"),
        "turnover":   None,
        "change_pct": quote.get("change_pct"),
        "source":     f"yfinance:{category}",
        "raw_json":   {
            "name":             quote.get("name"),
            "n_day_avg_volume": quote.get("n_day_avg_volume"),
            "last_ts":          quote.get("last_ts"),
            "category":         category,
            "trade_date":       trade_date,
        },
    }


def _build_movement_events(quote: dict, category: str, trade_date: str, scraped_at: str) -> list[dict]:
    """建立 build movement events 對應的資料或結果。"""
    market = _CATEGORY_TO_MARKET.get(category, category.upper())
    detected = detect_movement_events(
        symbol=quote["symbol"],
        market=market,
        session="regular",
        trade_date=trade_date,
        open_price=quote.get("open"),
        last_price=quote.get("price"),
        volume=quote.get("volume"),
        context=QuoteContext(
            prev_close=quote.get("prev_close"),
            n_day_avg_volume=quote.get("n_day_avg_volume"),
        ),
    )
    relay_events = []
    for evt in detected:
        url = f"https://finance.yahoo.com/quote/{quote['symbol']}"
        relay_events.append({
            "event_id":     evt["event_id"],
            "source":       evt["source"],
            "title":        evt["title"],
            "url":          url,
            "summary":      evt["summary"],
            "published_at": scraped_at,
            "raw_json":     evt["raw_json"],
        })
    return relay_events


# ── 推送：snapshots → /quote-snapshots；異動 → /events ──
def push_to_relay(stocks_data: dict, scraped_at: str) -> None:
    """執行 push to relay 的主要流程。"""
    trade_date = scraped_at[:10]
    snapshots: list[dict] = []
    move_events: list[dict] = []

    for category, quotes in stocks_data.items():
        for q in quotes:
            if not q:
                continue
            snapshots.append(_build_snapshot_row(q, category, scraped_at, trade_date))
            move_events.extend(_build_movement_events(q, category, trade_date, scraped_at))

    if snapshots:
        snap_result = push_quote_snapshots(snapshots)
        if snap_result["ok"]:
            print(f"  [relay] stored {snap_result.get('stored', len(snapshots))} quote snapshots")
        else:
            print(f"  [relay] snapshots skipped: {snap_result.get('error')}")
    else:
        print("  [relay] no quote snapshots")

    if move_events:
        evt_result = push_events(move_events)
        if evt_result["ok"]:
            print(f"  [relay] emitted {len(move_events)} movement events (gap/sharp/volume_spike)")
        else:
            print(f"  [relay] movement events skipped: {evt_result.get('error')}")
    else:
        print("  [relay] no significant moves to emit")


# ── 主程式 ─────────────────────────────────────────────
def main():
    """程式入口，負責執行此模組的主要流程。"""
    print("[Yahoo Finance] Fetching stock quotes via yfinance...")
    try:
        _require_optional_dependencies()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1

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
    print(f"\n[OK] {total} symbols saved to {filepath}")

    # 2. 推送：snapshots → /quote-snapshots；異動事件 → /events
    push_to_relay(stocks_data, scraped_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
