"""US index quote tracker (Dow, S&P 500, Nasdaq).

Pulls regular-session OHLC from a public quote endpoint and produces
snapshot rows used by the pre-open and US-close summaries. Predates
REQ-019 ``t_market_quote_snapshots`` and remains for legacy summaries."""

from __future__ import annotations

# 美股指數追蹤器：抓道瓊與 S&P500，提供開盤/收盤推播內容。
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from news_collector.http_client import http_get_json


@dataclass(frozen=True)
class IndexQuote:
    """封裝 Index Quote 相關資料與行為。"""
    symbol: str
    label: str
    url: str
    trade_date: date
    regular_start_epoch: int
    regular_end_epoch: int
    open_price: float
    last_price: float


class UsIndexTracker:
    """封裝 Us Index Tracker 相關資料與行為。"""
    symbols = (
        ("%5EDJI", "DJIA", "https://finance.yahoo.com/quote/%5EDJI"),
        ("%5EGSPC", "S&P 500", "https://finance.yahoo.com/quote/%5EGSPC"),
    )

    def __init__(self, timeout_seconds: int = 12) -> None:
        """初始化物件狀態與必要依賴。"""
        self._timeout_seconds = max(timeout_seconds, 5)

    def fetch_snapshot(self) -> tuple[date | None, dict[str, IndexQuote]]:
        """抓取 fetch snapshot 對應的資料或結果。"""
        quotes: dict[str, IndexQuote] = {}
        trade_dates: set[date] = set()

        for encoded_symbol, label, url in self.symbols:
            endpoint = f"https://query2.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
            payload = http_get_json(endpoint, params={"interval": "1m", "range": "1d"}, timeout=self._timeout_seconds)
            result = ((payload.get("chart") or {}).get("result") or [None])[0]
            if not isinstance(result, dict):
                continue

            quote = self._parse_quote(result=result, label=label, url=url)
            if quote is None:
                continue

            quotes[quote.symbol] = quote
            trade_dates.add(quote.trade_date)

        # 需要兩個指數且同一交易日才回傳，避免混到舊盤資料。
        if len(quotes) != len(self.symbols) or len(trade_dates) != 1:
            return None, {}

        return next(iter(trade_dates)), quotes

    def format_open_message(self, trade_date: date, quotes: dict[str, IndexQuote]) -> str:
        """格式化 format open message 對應的資料或結果。"""
        dji = quotes["DJIA"]
        gspc = quotes["S&P 500"]
        return "\n".join(
            [
                f"[US_INDEX_OPEN] {trade_date.isoformat()} (America/New_York)",
                f"DJIA 開盤: {self._fmt_price(dji.open_price)}",
                f"S&P 500 開盤: {self._fmt_price(gspc.open_price)}",
                dji.url,
                gspc.url,
            ]
        )

    def format_close_message(self, trade_date: date, quotes: dict[str, IndexQuote]) -> str:
        """格式化 format close message 對應的資料或結果。"""
        dji = quotes["DJIA"]
        gspc = quotes["S&P 500"]
        return "\n".join(
            [
                f"[US_INDEX_CLOSE] {trade_date.isoformat()} (America/New_York)",
                f"DJIA 收盤: {self._fmt_price(dji.last_price)}",
                f"S&P 500 收盤: {self._fmt_price(gspc.last_price)}",
                dji.url,
                gspc.url,
            ]
        )

    def _parse_quote(self, result: dict[str, Any], label: str, url: str) -> IndexQuote | None:
        """解析 parse quote 對應的資料或結果。"""
        meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
        symbol = str(meta.get("symbol") or "").strip()
        if not symbol:
            return None

        indicators = result.get("indicators") if isinstance(result.get("indicators"), dict) else {}
        quote_obj = ((indicators.get("quote") or [None])[0]) if isinstance(indicators.get("quote"), list) else None
        if not isinstance(quote_obj, dict):
            return None

        opens = [x for x in (quote_obj.get("open") or []) if isinstance(x, (int, float))]
        closes = [x for x in (quote_obj.get("close") or []) if isinstance(x, (int, float))]
        if not opens or not closes:
            return None

        current_trading_period = meta.get("currentTradingPeriod") if isinstance(meta.get("currentTradingPeriod"), dict) else {}
        regular = current_trading_period.get("regular") if isinstance(current_trading_period.get("regular"), dict) else {}
        start_epoch = regular.get("start")
        end_epoch = regular.get("end")
        if not isinstance(start_epoch, (int, float)) or not isinstance(end_epoch, (int, float)):
            return None

        trade_date = datetime.fromtimestamp(int(start_epoch), tz=timezone.utc).date()

        return IndexQuote(
            symbol=label,
            label=label,
            url=url,
            trade_date=trade_date,
            regular_start_epoch=int(start_epoch),
            regular_end_epoch=int(end_epoch),
            open_price=float(opens[0]),
            last_price=float(closes[-1]),
        )

    @staticmethod
    def _fmt_price(value: float) -> str:
        """格式化 fmt price 對應的資料或結果。"""
        return f"{value:,.2f}"
