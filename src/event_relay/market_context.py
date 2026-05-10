"""Pre-open market-context collector.

Pulls overnight US market state (index closes, treasury yields, FX, oil)
and writes ``market_context:*`` stored-only events into ``t_relay_events``
so the pre_tw_open / us_close analysis pipelines can read it from the same
event window as news. No analysis is generated here — that is owned by
``market_analysis.py``."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
import os
import re
import sys
from typing import Any
from xml.etree import ElementTree as ET

from event_relay.config import load_settings
from event_relay.service import MySqlEventStore, RelayEvent
from news_collector.http_client import http_get_json, http_get_json_with_headers, http_get_text


logger = logging.getLogger(__name__)

PROMPT_VERSION = "market-context-v1"
DEFAULT_ANALYSIS_SLOT = "market_context_pre_tw_open"
DEFAULT_SCHEDULED_TIME = "07:20"
SCORECARD_VERSION = "market-scorecard-v1"
SCORECARD_SCALE = "-2=risk-off / stress, 0=mixed or insufficient, +2=supportive / risk-on"
SCORECARD_DIMENSIONS = (
    "breadth_health",
    "ai_capex_quality",
    "energy_shock_risk",
    "credit_stress",
    "liquidity_impulse",
)
AI_CAPEX_DEFAULT_TICKERS = ("MSFT", "GOOGL", "META", "AMZN")
SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
EIA_CRUDE_STOCKS_URL = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
EIA_CRUDE_STOCKS_SERIES = "WCESTUS1"

YAHOO_MARKET_SYMBOLS = (
    ("%5EIXIC", "NASDAQ Composite", "us_equity_index", "https://finance.yahoo.com/quote/%5EIXIC"),
    ("%5ENDX", "NASDAQ 100", "us_equity_index", "https://finance.yahoo.com/quote/%5ENDX"),
    ("%5ESOX", "PHLX Semiconductor", "semiconductor", "https://finance.yahoo.com/quote/%5ESOX"),
    ("%5EVIX", "VIX", "volatility", "https://finance.yahoo.com/quote/%5EVIX"),
    ("DX-Y.NYB", "U.S. Dollar Index", "fx", "https://finance.yahoo.com/quote/DX-Y.NYB"),
    ("CL=F", "WTI Crude Oil", "commodity", "https://finance.yahoo.com/quote/CL=F"),
    ("GC=F", "Gold Futures", "commodity", "https://finance.yahoo.com/quote/GC=F"),
    ("TSM", "TSM ADR", "semiconductor_stock", "https://finance.yahoo.com/quote/TSM"),
    ("NVDA", "NVIDIA", "semiconductor_stock", "https://finance.yahoo.com/quote/NVDA"),
    ("AMD", "AMD", "semiconductor_stock", "https://finance.yahoo.com/quote/AMD"),
    ("ASML", "ASML", "semiconductor_stock", "https://finance.yahoo.com/quote/ASML"),
    ("AVGO", "Broadcom", "semiconductor_stock", "https://finance.yahoo.com/quote/AVGO"),
    ("MU", "Micron", "semiconductor_stock", "https://finance.yahoo.com/quote/MU"),
    ("KRE", "SPDR S&P Regional Banking ETF", "bank_credit_proxy", "https://finance.yahoo.com/quote/KRE"),
    ("XLF", "Financial Select Sector SPDR Fund", "financials_proxy", "https://finance.yahoo.com/quote/XLF"),
    ("HYG", "iShares High Yield Corporate Bond ETF", "credit_proxy", "https://finance.yahoo.com/quote/HYG"),
    ("LQD", "iShares Investment Grade Corporate Bond ETF", "credit_proxy", "https://finance.yahoo.com/quote/LQD"),
    ("TLT", "iShares 20+ Year Treasury Bond ETF", "duration_proxy", "https://finance.yahoo.com/quote/TLT"),
    ("QQQ", "Invesco QQQ Trust", "growth_proxy", "https://finance.yahoo.com/quote/QQQ"),
    ("SPY", "SPDR S&P 500 ETF", "risk_proxy", "https://finance.yahoo.com/quote/SPY"),
    ("IWM", "iShares Russell 2000 ETF", "small_cap_proxy", "https://finance.yahoo.com/quote/IWM"),
)

BREADTH_YAHOO_SYMBOLS = (
    ("SPY", "SPDR S&P 500 ETF", "cap_weight_proxy", "https://finance.yahoo.com/quote/SPY"),
    ("RSP", "Invesco S&P 500 Equal Weight ETF", "equal_weight_proxy", "https://finance.yahoo.com/quote/RSP"),
    ("QQQ", "Invesco QQQ Trust", "nasdaq_cap_weight_proxy", "https://finance.yahoo.com/quote/QQQ"),
    ("QQEW", "First Trust Nasdaq-100 Equal Weighted Index Fund", "nasdaq_equal_weight_proxy", "https://finance.yahoo.com/quote/QQEW"),
    ("IWM", "iShares Russell 2000 ETF", "small_cap_proxy", "https://finance.yahoo.com/quote/IWM"),
)

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

TWSE_INDEX_NAMES = (
    "發行量加權股價指數",
    "電子類指數",
    "半導體類指數",
    "金融保險類指數",
)


@dataclass(frozen=True)
class MarketContextConfig:
    """封裝 Market Context Config 相關資料與行為。"""
    env_file: str
    analysis_slot: str
    scheduled_time_local: str
    timeout_seconds: int
    twse_codes: list[str]
    tw_yahoo_symbols: tuple["TaiwanYahooSymbol", ...] = ()
    fred_enabled: bool = True
    fred_series_ids: tuple[str, ...] = ()
    market_breadth_enabled: bool = True
    ai_capex_enabled: bool = True
    ai_capex_tickers: tuple[str, ...] = AI_CAPEX_DEFAULT_TICKERS
    oil_supply_enabled: bool = True
    scorecard_enabled: bool = True


@dataclass(frozen=True)
class TaiwanYahooSymbol:
    """Taiwan stock quote symbol used as Yahoo fallback for tracked stocks."""
    symbol: str
    name: str


@dataclass(frozen=True)
class FredSeriesSpec:
    """FRED public CSV series used as macro-regime context."""
    series_id: str
    name: str
    category: str
    unit: str


FRED_SERIES_SPECS: tuple[FredSeriesSpec, ...] = (
    FredSeriesSpec("DFEDTARU", "Fed Target Range Upper Limit", "fed_path", "percent"),
    FredSeriesSpec("DFEDTARL", "Fed Target Range Lower Limit", "fed_path", "percent"),
    FredSeriesSpec("SOFR", "Secured Overnight Financing Rate", "fed_path", "percent"),
    FredSeriesSpec("DGS2", "US Treasury 2Y Constant Maturity", "fed_path", "percent"),
    FredSeriesSpec("DGS10", "US Treasury 10Y Constant Maturity", "rates", "percent"),
    FredSeriesSpec("T10Y2Y", "10Y-2Y Treasury Spread", "rates_spread", "percent"),
    FredSeriesSpec("WALCL", "Federal Reserve Total Assets", "liquidity", "usd_millions"),
    FredSeriesSpec("RRPONTSYD", "Overnight Reverse Repo", "liquidity", "usd_billions"),
    FredSeriesSpec("WTREGEN", "Treasury General Account", "liquidity", "usd_millions"),
    FredSeriesSpec("WRESBAL", "Reserve Balances", "liquidity", "usd_millions"),
    FredSeriesSpec("NFCI", "Chicago Fed National Financial Conditions Index", "financial_conditions", "index"),
    FredSeriesSpec("STLFSI4", "St. Louis Fed Financial Stress Index", "financial_conditions", "index"),
    FredSeriesSpec("BAMLH0A0HYM2", "US High Yield Option-Adjusted Spread", "credit_stress", "percent"),
    FredSeriesSpec("BAMLC0A0CM", "US Corporate Option-Adjusted Spread", "credit_stress", "percent"),
    FredSeriesSpec("BAA10Y", "Moody's Baa Corporate Yield Spread vs 10Y", "credit_stress", "percent"),
    FredSeriesSpec("VIXCLS", "CBOE VIX Close", "sentiment_positioning", "index"),
)

FRED_SERIES_BY_ID = {spec.series_id: spec for spec in FRED_SERIES_SPECS}

ENERGY_FRED_SERIES_SPECS: tuple[FredSeriesSpec, ...] = (
    FredSeriesSpec("DCOILWTICO", "WTI crude oil spot price", "oil_price", "usd_per_barrel"),
    FredSeriesSpec("DCOILBRENTEU", "Brent crude oil spot price", "oil_price", "usd_per_barrel"),
)

SEC_CAPEX_CONCEPTS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
)
SEC_OPERATING_CASH_FLOW_CONCEPTS = (
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
)


@dataclass(frozen=True)
class MarketContextPoint:
    """封裝 Market Context Point 相關資料與行為。"""
    source: str
    category: str
    name: str
    symbol: str
    value: float | None
    previous_value: float | None
    change: float | None
    change_percent: float | None
    unit: str
    as_of: str | None
    url: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class SourceFailure:
    """封裝 Source Failure 相關資料與行為。"""
    source: str
    error: str


def _build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(description="Collect market context and store it as event-only facts in t_relay_events")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--analysis-slot", default=DEFAULT_ANALYSIS_SLOT, help="t_market_analyses analysis_slot")
    parser.add_argument("--scheduled-time", default=DEFAULT_SCHEDULED_TIME, help="Local schedule label, e.g. 07:20")
    parser.add_argument("--timeout-seconds", type=int, default=15, help="Per-source HTTP timeout")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _load_config(args: argparse.Namespace) -> MarketContextConfig:
    """載入 load config 對應的資料或結果。"""
    load_settings(args.env_file)
    code_text = os.getenv("MARKET_CONTEXT_TWSE_CODES") or os.getenv("TWSE_MOPS_TRACKED_CODES") or ""
    twse_codes = [x.strip() for x in code_text.split(",") if x.strip()]
    fred_series_ids = _parse_csv_env(os.getenv("MARKET_CONTEXT_FRED_SERIES_IDS"))
    ai_capex_tickers = tuple(
        ticker
        for ticker in (
            _normalize_us_ticker(item) for item in _parse_csv_env(os.getenv("MARKET_CONTEXT_AI_CAPEX_TICKERS"))
        )
        if ticker
    ) or AI_CAPEX_DEFAULT_TICKERS
    return MarketContextConfig(
        env_file=args.env_file,
        analysis_slot=(os.getenv("MARKET_CONTEXT_ANALYSIS_SLOT") or args.analysis_slot).strip() or DEFAULT_ANALYSIS_SLOT,
        scheduled_time_local=(os.getenv("MARKET_CONTEXT_SCHEDULED_TIME") or args.scheduled_time).strip()
        or DEFAULT_SCHEDULED_TIME,
        timeout_seconds=max(5, int(os.getenv("MARKET_CONTEXT_TIMEOUT_SECONDS") or args.timeout_seconds)),
        twse_codes=twse_codes,
        tw_yahoo_symbols=_parse_tw_yahoo_symbols(os.getenv("MARKET_CONTEXT_TW_YAHOO_SYMBOLS")),
        fred_enabled=_env_bool("MARKET_CONTEXT_FRED_ENABLED", True),
        fred_series_ids=tuple(fred_series_ids),
        market_breadth_enabled=_env_bool("MARKET_CONTEXT_BREADTH_ENABLED", True),
        ai_capex_enabled=_env_bool("MARKET_CONTEXT_AI_CAPEX_ENABLED", True),
        ai_capex_tickers=ai_capex_tickers,
        oil_supply_enabled=_env_bool("MARKET_CONTEXT_OIL_SUPPLY_ENABLED", True),
        scorecard_enabled=_env_bool("MARKET_CONTEXT_SCORECARD_ENABLED", True),
    )


def _env_bool(name: str, default: bool) -> bool:
    """Read a bool env var without making missing config fatal."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _parse_csv_env(text: str | None) -> list[str]:
    """Parse comma-separated env values."""
    return [item.strip() for item in str(text or "").split(",") if item.strip()]


def _normalize_us_ticker(raw: str | None) -> str | None:
    """Normalize a U.S. ticker symbol for SEC/Yahoo lookups."""
    text = (raw or "").strip().upper()
    if not text or not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", text):
        return None
    return text


def _tw_yahoo_symbol_code(symbol: str) -> str:
    """Extract the 4-digit Taiwan ticker code from a Yahoo Taiwan symbol."""
    return str(symbol or "").strip().upper().split(".", 1)[0]


def _parse_tw_yahoo_symbols(text: str | None) -> tuple[TaiwanYahooSymbol, ...]:
    """Parse MARKET_CONTEXT_TW_YAHOO_SYMBOLS entries like 4749.TWO:新應材."""
    items: list[TaiwanYahooSymbol] = []
    for raw in str(text or "").split(","):
        entry = raw.strip()
        if not entry:
            continue
        symbol, name = entry, ""
        for separator in (":", "|", "="):
            if separator in entry:
                symbol, name = entry.split(separator, 1)
                break
        symbol = symbol.strip().upper()
        if not symbol:
            continue
        if symbol.isdigit():
            symbol = f"{symbol}.TW"
        code = _tw_yahoo_symbol_code(symbol)
        items.append(TaiwanYahooSymbol(symbol=symbol, name=name.strip() or code))
    return tuple(items)


def _to_float(value: Any) -> float | None:
    """轉換 to float 對應的資料或結果。"""
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if not text or text in {"--", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _roc_date_to_iso(value: str | None) -> str | None:
    """執行 roc date to iso 的主要流程。"""
    text = (value or "").strip()
    if len(text) != 7 or not text.isdigit():
        return None
    year = int(text[:3]) + 1911
    return f"{year:04d}-{int(text[3:5]):02d}-{int(text[5:7]):02d}"


def _epoch_to_iso(value: Any) -> str | None:
    """執行 epoch to iso 的主要流程。"""
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()


def _parse_yahoo_chart_payload(
    payload: dict[str, Any],
    label: str,
    category: str,
    url: str,
) -> MarketContextPoint | None:
    """解析 parse yahoo chart payload 對應的資料或結果。"""
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        return None
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    symbol = str(meta.get("symbol") or label).strip()
    value = _to_float(meta.get("regularMarketPrice"))
    previous = _to_float(meta.get("chartPreviousClose") or meta.get("previousClose"))
    if value is None or previous is None:
        indicators = result.get("indicators") if isinstance(result.get("indicators"), dict) else {}
        quote_obj = ((indicators.get("quote") or [None])[0]) if isinstance(indicators.get("quote"), list) else None
        if isinstance(quote_obj, dict):
            closes = [_to_float(x) for x in (quote_obj.get("close") or [])]
            closes = [x for x in closes if x is not None]
            if value is None and closes:
                value = closes[-1]
    if value is None:
        return None

    change = value - previous if previous is not None else None
    change_percent = (change / previous * 100.0) if change is not None and previous not in {None, 0} else None
    return MarketContextPoint(
        source="yahoo_chart",
        category=category,
        name=label,
        symbol=symbol,
        value=value,
        previous_value=previous,
        change=change,
        change_percent=change_percent,
        unit=str(meta.get("currency") or "points"),
        as_of=_epoch_to_iso(meta.get("regularMarketTime")),
        url=url,
        raw={"meta": meta},
    )


def _parse_yahoo_daily_series(payload: dict[str, Any], label: str, url: str) -> dict[str, Any] | None:
    """Parse a Yahoo daily chart payload into clean close-price history."""
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        return None

    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    timestamps = result.get("timestamp") if isinstance(result.get("timestamp"), list) else []
    indicators = result.get("indicators") if isinstance(result.get("indicators"), dict) else {}
    quote_obj = ((indicators.get("quote") or [None])[0]) if isinstance(indicators.get("quote"), list) else None
    if not isinstance(quote_obj, dict):
        return None

    closes: list[tuple[int | None, float]] = []
    for index, raw_close in enumerate(quote_obj.get("close") or []):
        close = _to_float(raw_close)
        if close is None:
            continue
        timestamp = timestamps[index] if index < len(timestamps) and isinstance(timestamps[index], int) else None
        closes.append((timestamp, close))

    if not closes:
        return None

    symbol = str(meta.get("symbol") or label).strip()
    return {
        "symbol": symbol,
        "label": label,
        "url": url,
        "currency": str(meta.get("currency") or "USD"),
        "as_of": _epoch_to_iso(closes[-1][0] or meta.get("regularMarketTime")),
        "closes": closes,
    }


def _series_return_percent(series: dict[str, Any], sessions: int) -> float | None:
    """Return percent change over an approximate number of trading sessions."""
    closes = series.get("closes") if isinstance(series, dict) else None
    if not isinstance(closes, list) or len(closes) < 2:
        return None
    latest = _to_float(closes[-1][1])
    start_index = max(0, len(closes) - max(int(sessions), 1) - 1)
    start = _to_float(closes[start_index][1])
    if latest is None or start in {None, 0}:
        return None
    return (latest - start) / start * 100.0


def _market_breadth_spread_point(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    symbol: str,
    name: str,
) -> MarketContextPoint | None:
    """Build a relative breadth proxy from two ETF return series."""
    left_1d = _series_return_percent(left, 1)
    right_1d = _series_return_percent(right, 1)
    if left_1d is None or right_1d is None:
        return None

    left_1m = _series_return_percent(left, 21)
    right_1m = _series_return_percent(right, 21)
    left_3m = _series_return_percent(left, 63)
    right_3m = _series_return_percent(right, 63)
    one_month_spread = (left_1m - right_1m) if left_1m is not None and right_1m is not None else None
    three_month_spread = (left_3m - right_3m) if left_3m is not None and right_3m is not None else None
    value = left_1d - right_1d

    return MarketContextPoint(
        source="market_breadth",
        category="market_breadth",
        name=name,
        symbol=symbol,
        value=value,
        previous_value=one_month_spread,
        change=three_month_spread,
        change_percent=None,
        unit="pct_point",
        as_of=str(left.get("as_of") or right.get("as_of") or ""),
        url=str(left.get("url") or right.get("url") or ""),
        raw={
            "left_symbol": left.get("symbol"),
            "right_symbol": right.get("symbol"),
            "left_1d_return_pct": left_1d,
            "right_1d_return_pct": right_1d,
            "one_day_spread_pct_point": value,
            "one_month_spread_pct_point": one_month_spread,
            "three_month_spread_pct_point": three_month_spread,
            "interpretation": "Positive means broader/equal-weight or smaller-cap participation is outperforming the cap-weight benchmark.",
        },
    )


def fetch_market_breadth_points(timeout_seconds: int) -> tuple[list[MarketContextPoint], list[SourceFailure]]:
    """Fetch ETF relative-return proxies for market breadth health."""
    series_by_symbol: dict[str, dict[str, Any]] = {}
    failures: list[SourceFailure] = []
    for symbol, label, _category, url in BREADTH_YAHOO_SYMBOLS:
        try:
            payload = http_get_json(
                f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "3mo"},
                timeout=timeout_seconds,
            )
            series = _parse_yahoo_daily_series(payload, label, url)
            if series is None:
                failures.append(SourceFailure(source=f"market_breadth:{symbol}", error="empty daily chart payload"))
            else:
                series_by_symbol[symbol] = series
        except Exception as exc:
            failures.append(SourceFailure(source=f"market_breadth:{symbol}", error=str(exc)))

    points: list[MarketContextPoint] = []
    pairs = (
        ("RSP", "SPY", "RSP-SPY", "S&P 500 equal-weight participation spread"),
        ("QQEW", "QQQ", "QQEW-QQQ", "Nasdaq 100 equal-weight participation spread"),
        ("IWM", "SPY", "IWM-SPY", "Small-cap relative participation spread"),
    )
    for left_symbol, right_symbol, symbol, name in pairs:
        left = series_by_symbol.get(left_symbol)
        right = series_by_symbol.get(right_symbol)
        if not left or not right:
            failures.append(SourceFailure(source=f"market_breadth:{symbol}", error="missing component series"))
            continue
        point = _market_breadth_spread_point(left, right, symbol=symbol, name=name)
        if point is None:
            failures.append(SourceFailure(source=f"market_breadth:{symbol}", error="not enough close history"))
        else:
            points.append(point)
    return points, failures


def fetch_yahoo_market_points(timeout_seconds: int) -> tuple[list[MarketContextPoint], list[SourceFailure]]:
    """抓取 fetch yahoo market points 對應的資料或結果。"""
    points: list[MarketContextPoint] = []
    failures: list[SourceFailure] = []
    for encoded_symbol, label, category, url in YAHOO_MARKET_SYMBOLS:
        try:
            payload = http_get_json(
                f"https://query2.finance.yahoo.com/v8/finance/chart/{encoded_symbol}",
                params={"interval": "1m", "range": "1d"},
                timeout=timeout_seconds,
            )
            point = _parse_yahoo_chart_payload(payload=payload, label=label, category=category, url=url)
            if point is not None:
                points.append(point)
            else:
                failures.append(SourceFailure(source=f"yahoo_chart:{label}", error="empty quote payload"))
        except Exception as exc:
                failures.append(SourceFailure(source=f"yahoo_chart:{label}", error=str(exc)))
    return points, failures


def fetch_yahoo_tracked_tw_points(
    timeout_seconds: int,
    symbols: tuple[TaiwanYahooSymbol, ...],
    *,
    skip_codes: set[str] | None = None,
) -> tuple[list[MarketContextPoint], list[SourceFailure]]:
    """Fetch Taiwan tracked-stock quotes from Yahoo when official TWSE rows are missing."""
    points: list[MarketContextPoint] = []
    failures: list[SourceFailure] = []
    skipped = {_tw_yahoo_symbol_code(code) for code in (skip_codes or set())}
    seen: set[str] = set()
    for item in symbols:
        symbol = item.symbol.strip().upper()
        code = _tw_yahoo_symbol_code(symbol)
        if not symbol or not code or code in skipped or symbol in seen:
            continue
        seen.add(symbol)
        url = f"https://finance.yahoo.com/quote/{symbol}"
        try:
            payload = http_get_json(
                f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "5d"},
                timeout=timeout_seconds,
            )
            point = _parse_yahoo_chart_payload(payload=payload, label=item.name, category="tw_tracked_stock", url=url)
            if point is not None:
                points.append(point)
            else:
                failures.append(SourceFailure(source=f"yahoo_chart:{symbol}", error="empty tracked Taiwan quote payload"))
        except Exception as exc:
            failures.append(SourceFailure(source=f"yahoo_chart:{symbol}", error=str(exc)))
    return points, failures


def _parse_treasury_yield_curve_xml(text: str) -> list[MarketContextPoint]:
    """解析 parse treasury yield curve xml 對應的資料或結果。"""
    root = ET.fromstring(text)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
        "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
    }
    latest: dict[str, str] | None = None
    # Treasury XML 會帶整年的多筆 entry，這裡只挑日期最新的一筆，
    # 再拆成 2Y / 10Y / 30Y / 10Y-2Y spread 四種 context point。
    for entry in root.findall("atom:entry", ns):
        props = entry.find("atom:content/m:properties", ns)
        if props is None:
            continue
        data = {child.tag.rsplit("}", 1)[-1]: child.text or "" for child in list(props)}
        if not data.get("NEW_DATE"):
            continue
        if latest is None or data["NEW_DATE"] > latest.get("NEW_DATE", ""):
            latest = data
    if latest is None:
        return []

    as_of = latest.get("NEW_DATE")
    url = "https://home.treasury.gov/treasury-daily-interest-rate-xml-feed"
    field_map = (
        ("BC_2YEAR", "US Treasury 2Y"),
        ("BC_10YEAR", "US Treasury 10Y"),
        ("BC_30YEAR", "US Treasury 30Y"),
    )
    points: list[MarketContextPoint] = []
    values: dict[str, float] = {}
    for field, name in field_map:
        value = _to_float(latest.get(field))
        if value is None:
            continue
        values[field] = value
        points.append(
            MarketContextPoint(
                source="us_treasury",
                category="rates",
                name=name,
                symbol=field,
                value=value,
                previous_value=None,
                change=None,
                change_percent=None,
                unit="percent",
                as_of=as_of,
                url=url,
                raw={"field": field, "record": latest},
            )
        )
    if "BC_10YEAR" in values and "BC_2YEAR" in values:
        spread_bp = (values["BC_10YEAR"] - values["BC_2YEAR"]) * 100.0
        points.append(
            MarketContextPoint(
                source="us_treasury",
                category="rates_spread",
                name="US Treasury 10Y-2Y Spread",
                symbol="US10Y2Y",
                value=spread_bp,
                previous_value=None,
                change=None,
                change_percent=None,
                unit="bp",
                as_of=as_of,
                url=url,
                raw={"ten_year": values["BC_10YEAR"], "two_year": values["BC_2YEAR"]},
            )
        )
    return points


def fetch_treasury_points(timeout_seconds: int) -> tuple[list[MarketContextPoint], list[SourceFailure]]:
    """抓取 fetch treasury points 對應的資料或結果。"""
    year = datetime.now().year
    try:
        text = http_get_text(
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml",
            params={"data": "daily_treasury_yield_curve", "field_tdr_date_value": year},
            timeout=max(timeout_seconds, 20),
        )
        points = _parse_treasury_yield_curve_xml(text)
        if not points:
            return [], [SourceFailure(source="us_treasury", error="empty yield curve payload")]
        return points, []
    except Exception as exc:
        return [], [SourceFailure(source="us_treasury", error=str(exc))]


def _parse_fred_csv(text: str, spec: FredSeriesSpec) -> MarketContextPoint | None:
    """Parse one FRED graph CSV response into the latest observation point."""
    rows = csv.DictReader(io.StringIO(text))
    observations: list[tuple[str, float]] = []
    for row in rows:
        as_of = str(row.get("observation_date") or "").strip()
        value = _to_float(row.get(spec.series_id))
        if as_of and value is not None:
            observations.append((as_of, value))
    if not observations:
        return None

    as_of, value = observations[-1]
    previous = observations[-2][1] if len(observations) >= 2 else None
    change = (value - previous) if previous is not None else None
    change_percent = (change / previous * 100.0) if change is not None and previous not in {None, 0} else None
    return MarketContextPoint(
        source="fred",
        category=spec.category,
        name=spec.name,
        symbol=spec.series_id,
        value=value,
        previous_value=previous,
        change=change,
        change_percent=change_percent,
        unit=spec.unit,
        as_of=as_of,
        url=f"https://fred.stlouisfed.org/series/{spec.series_id}",
        raw={"series_id": spec.series_id, "csv_url": FRED_CSV_URL},
    )


def fetch_fred_points(
    timeout_seconds: int,
    series_ids: tuple[str, ...] | None = None,
) -> tuple[list[MarketContextPoint], list[SourceFailure]]:
    """Fetch Fed/FRED public CSV facts for macro regime context."""
    points: list[MarketContextPoint] = []
    failures: list[SourceFailure] = []
    specs: list[FredSeriesSpec] = []
    requested = tuple(series_ids or ())
    if requested:
        for series_id in requested:
            spec = FRED_SERIES_BY_ID.get(series_id)
            if spec is None:
                failures.append(SourceFailure(source=f"fred:{series_id}", error="unknown FRED series id"))
            else:
                specs.append(spec)
    else:
        specs = list(FRED_SERIES_SPECS)

    for spec in specs:
        try:
            text = http_get_text(
                FRED_CSV_URL,
                params={"id": spec.series_id},
                timeout=max(timeout_seconds, 15),
            )
            point = _parse_fred_csv(text, spec)
            if point is not None:
                points.append(point)
            else:
                failures.append(SourceFailure(source=f"fred:{spec.series_id}", error="empty FRED CSV payload"))
        except Exception as exc:
            failures.append(SourceFailure(source=f"fred:{spec.series_id}", error=str(exc)))
    return points, failures


def _point_with_source(point: MarketContextPoint, source: str) -> MarketContextPoint:
    """Clone a context point while preserving the existing event payload contract."""
    return MarketContextPoint(
        source=source,
        category=point.category,
        name=point.name,
        symbol=point.symbol,
        value=point.value,
        previous_value=point.previous_value,
        change=point.change,
        change_percent=point.change_percent,
        unit=point.unit,
        as_of=point.as_of,
        url=point.url,
        raw=point.raw,
    )


def _parse_eia_crude_stocks_payload(payload: dict[str, Any]) -> MarketContextPoint | None:
    """Parse EIA v2 weekly crude stocks response into one inventory point."""
    response = payload.get("response") if isinstance(payload, dict) else None
    rows = response.get("data") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        return None

    observations: list[tuple[str, float, dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        period = str(row.get("period") or "").strip()
        value = _to_float(row.get("value"))
        if period and value is not None:
            observations.append((period, value, row))
    observations.sort(key=lambda item: item[0])
    if not observations:
        return None

    as_of, value, raw = observations[-1]
    previous = observations[-2][1] if len(observations) >= 2 else None
    change = (value - previous) if previous is not None else None
    change_percent = (change / previous * 100.0) if change is not None and previous not in {None, 0} else None
    return MarketContextPoint(
        source="eia",
        category="oil_inventory",
        name="U.S. crude oil stocks excluding SPR",
        symbol=EIA_CRUDE_STOCKS_SERIES,
        value=value,
        previous_value=previous,
        change=change,
        change_percent=change_percent,
        unit="thousand_barrels",
        as_of=as_of,
        url="https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=W&n=PET&s=WCESTUS1",
        raw={"series": EIA_CRUDE_STOCKS_SERIES, "record": raw},
    )


def fetch_eia_crude_stocks_point(timeout_seconds: int) -> tuple[list[MarketContextPoint], list[SourceFailure]]:
    """Fetch EIA weekly crude stocks when a free EIA API key is configured."""
    api_key = (os.getenv("EIA_API_KEY") or "").strip()
    if not api_key:
        return [], [SourceFailure(source=f"eia:{EIA_CRUDE_STOCKS_SERIES}", error="EIA_API_KEY is required for crude inventory context")]
    try:
        payload = http_get_json(
            EIA_CRUDE_STOCKS_URL,
            params={
                "api_key": api_key,
                "frequency": "weekly",
                "data[0]": "value",
                "facets[series][]": EIA_CRUDE_STOCKS_SERIES,
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "length": 2,
            },
            timeout=max(timeout_seconds, 15),
        )
        point = _parse_eia_crude_stocks_payload(payload)
        if point is None:
            return [], [SourceFailure(source=f"eia:{EIA_CRUDE_STOCKS_SERIES}", error="empty EIA crude stocks payload")]
        return [point], []
    except Exception as exc:
        return [], [SourceFailure(source=f"eia:{EIA_CRUDE_STOCKS_SERIES}", error=str(exc))]


def fetch_oil_supply_demand_points(timeout_seconds: int) -> tuple[list[MarketContextPoint], list[SourceFailure]]:
    """Fetch FRED/EIA oil price and inventory facts for energy-shock scoring."""
    points: list[MarketContextPoint] = []
    failures: list[SourceFailure] = []
    for spec in ENERGY_FRED_SERIES_SPECS:
        try:
            text = http_get_text(
                FRED_CSV_URL,
                params={"id": spec.series_id},
                timeout=max(timeout_seconds, 15),
            )
            point = _parse_fred_csv(text, spec)
            if point is None:
                failures.append(SourceFailure(source=f"fred_energy:{spec.series_id}", error="empty FRED CSV payload"))
            else:
                points.append(_point_with_source(point, "fred_energy"))
        except Exception as exc:
            failures.append(SourceFailure(source=f"fred_energy:{spec.series_id}", error=str(exc)))

    eia_points, eia_failures = fetch_eia_crude_stocks_point(timeout_seconds)
    points.extend(eia_points)
    failures.extend(eia_failures)

    brent = _find(points, "DCOILBRENTEU")
    wti = _find(points, "DCOILWTICO")
    if brent and wti and brent.value is not None and wti.value is not None:
        spread = brent.value - wti.value
        previous_spread = (
            brent.previous_value - wti.previous_value
            if brent.previous_value is not None and wti.previous_value is not None
            else None
        )
        change = (spread - previous_spread) if previous_spread is not None else None
        points.append(
            MarketContextPoint(
                source="fred_energy",
                category="oil_supply_demand",
                name="Brent-WTI spread",
                symbol="BRENT-WTI",
                value=spread,
                previous_value=previous_spread,
                change=change,
                change_percent=None,
                unit="usd_per_barrel",
                as_of=brent.as_of or wti.as_of,
                url="https://fred.stlouisfed.org/series/DCOILBRENTEU",
                raw={
                    "brent_value": brent.value,
                    "wti_value": wti.value,
                    "brent_as_of": brent.as_of,
                    "wti_as_of": wti.as_of,
                    "interpretation": "Wider Brent-WTI spread can flag regional supply tightness or logistics stress.",
                },
            )
        )
    return points, failures


def _load_sec_ticker_map(user_agent: str, timeout_seconds: int) -> dict[str, dict[str, str]]:
    """Load SEC's official ticker-to-CIK mapping."""
    payload = http_get_json_with_headers(
        SEC_TICKER_MAP_URL,
        timeout=timeout_seconds,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    result: dict[str, dict[str, str]] = {}
    for value in payload.values():
        if not isinstance(value, dict):
            continue
        ticker = _normalize_us_ticker(str(value.get("ticker") or ""))
        cik = str(value.get("cik_str") or "").strip()
        title = str(value.get("title") or "").strip()
        if ticker and cik and title:
            result[ticker] = {"cik": cik.zfill(10), "title": title}
    return result


def _sec_usd_fact_records(payload: dict[str, Any], concept_names: tuple[str, ...]) -> list[dict[str, Any]]:
    """Extract normalized USD XBRL facts for one or more us-gaap concepts."""
    us_gaap = ((payload.get("facts") or {}).get("us-gaap") or {}) if isinstance(payload.get("facts"), dict) else {}
    records: list[dict[str, Any]] = []
    for concept in concept_names:
        concept_obj = us_gaap.get(concept) if isinstance(us_gaap, dict) else None
        units = concept_obj.get("units") if isinstance(concept_obj, dict) else None
        entries = units.get("USD") if isinstance(units, dict) else None
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            form = str(entry.get("form") or "").upper()
            if form not in {"10-Q", "10-K", "20-F", "40-F"}:
                continue
            value = _to_float(entry.get("val"))
            end = str(entry.get("end") or "").strip()
            filed = str(entry.get("filed") or "").strip()
            if value is None or not end:
                continue
            records.append(
                {
                    "concept": concept,
                    "value": value,
                    "end": end,
                    "filed": filed,
                    "fy": entry.get("fy"),
                    "fp": entry.get("fp"),
                    "form": form,
                    "frame": entry.get("frame"),
                }
            )
    records.sort(key=lambda row: (str(row.get("end") or ""), str(row.get("filed") or "")), reverse=True)
    return records


def _latest_sec_fact(payload: dict[str, Any], concept_names: tuple[str, ...]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return latest and previous SEC USD fact records."""
    records = _sec_usd_fact_records(payload, concept_names)
    if not records:
        return None, None
    latest = records[0]
    previous = next((row for row in records[1:] if row.get("end") != latest.get("end")), None)
    return latest, previous


def _build_ai_capex_point(
    ticker: str,
    company_title: str,
    cik: str,
    payload: dict[str, Any],
) -> MarketContextPoint | None:
    """Build one AI-capex proxy point from SEC companyfacts."""
    capex, previous_capex = _latest_sec_fact(payload, SEC_CAPEX_CONCEPTS)
    if capex is None:
        return None

    ocf, _previous_ocf = _latest_sec_fact(payload, SEC_OPERATING_CASH_FLOW_CONCEPTS)
    value = abs(float(capex["value"]))
    previous_value = abs(float(previous_capex["value"])) if previous_capex is not None else None
    change = (value - previous_value) if previous_value is not None else None
    change_percent = (change / previous_value * 100.0) if change is not None and previous_value not in {None, 0} else None
    operating_cash_flow = float(ocf["value"]) if ocf is not None else None
    free_cash_flow = (operating_cash_flow - value) if operating_cash_flow is not None else None

    return MarketContextPoint(
        source="sec_companyfacts",
        category="ai_capex",
        name=f"{ticker} AI capex proxy",
        symbol=ticker,
        value=value,
        previous_value=previous_value,
        change=change,
        change_percent=change_percent,
        unit="usd",
        as_of=str(capex.get("filed") or capex.get("end") or ""),
        url=SEC_COMPANY_FACTS_URL_TEMPLATE.format(cik=cik),
        raw={
            "ticker": ticker,
            "company_title": company_title,
            "cik": cik,
            "capex_fact": capex,
            "previous_capex_fact": previous_capex,
            "operating_cash_flow_fact": ocf,
            "operating_cash_flow": operating_cash_flow,
            "free_cash_flow_proxy": free_cash_flow,
            "guardrail": "This is a companyfacts capex proxy, not a perfect AI-only capex split.",
        },
    )


def fetch_ai_capex_points(
    timeout_seconds: int,
    tickers: tuple[str, ...],
) -> tuple[list[MarketContextPoint], list[SourceFailure]]:
    """Fetch hyperscaler capex proxies from SEC companyfacts."""
    user_agent = (os.getenv("SEC_USER_AGENT") or "").strip()
    if not user_agent:
        return [], [SourceFailure(source="sec_companyfacts:ai_capex", error="SEC_USER_AGENT is required for SEC EDGAR access")]

    try:
        ticker_map = _load_sec_ticker_map(user_agent, timeout_seconds)
    except Exception as exc:
        return [], [SourceFailure(source="sec_companyfacts:ticker_map", error=str(exc))]

    points: list[MarketContextPoint] = []
    failures: list[SourceFailure] = []
    seen: set[str] = set()
    for raw_ticker in tickers:
        ticker = _normalize_us_ticker(raw_ticker)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        company = ticker_map.get(ticker)
        if company is None:
            failures.append(SourceFailure(source=f"sec_companyfacts:{ticker}", error="ticker not found in SEC mapping"))
            continue
        cik = company["cik"]
        try:
            payload = http_get_json_with_headers(
                SEC_COMPANY_FACTS_URL_TEMPLATE.format(cik=cik),
                timeout=max(timeout_seconds, 15),
                headers={"User-Agent": user_agent, "Accept": "application/json"},
            )
            point = _build_ai_capex_point(ticker, company["title"], cik, payload)
            if point is None:
                failures.append(SourceFailure(source=f"sec_companyfacts:{ticker}", error="capex fact not found"))
            else:
                points.append(point)
        except Exception as exc:
            failures.append(SourceFailure(source=f"sec_companyfacts:{ticker}", error=str(exc)))
    return points, failures


def _twse_index_point(row: dict[str, Any]) -> MarketContextPoint | None:
    """執行 twse index point 的主要流程。"""
    name = str(row.get("指數") or "").strip()
    if name not in TWSE_INDEX_NAMES:
        return None
    value = _to_float(row.get("收盤指數"))
    if value is None:
        return None
    sign = -1.0 if str(row.get("漲跌") or "").strip() == "-" else 1.0
    change = _to_float(row.get("漲跌點數"))
    if change is not None:
        change *= sign
    change_percent = _to_float(row.get("漲跌百分比"))
    return MarketContextPoint(
        source="twse_openapi",
        category="tw_equity_index",
        name=name,
        symbol=name,
        value=value,
        previous_value=None,
        change=change,
        change_percent=change_percent,
        unit="points",
        as_of=_roc_date_to_iso(str(row.get("日期") or "")),
        url="https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX",
        raw=row,
    )


def _twse_stock_point(row: dict[str, Any]) -> MarketContextPoint | None:
    """執行 twse stock point 的主要流程。"""
    code = str(row.get("Code") or "").strip()
    close = _to_float(row.get("ClosingPrice"))
    if not code or close is None:
        return None
    change = _to_float(row.get("Change"))
    return MarketContextPoint(
        source="twse_openapi",
        category="tw_tracked_stock",
        name=str(row.get("Name") or code).strip(),
        symbol=code,
        value=close,
        previous_value=None,
        change=change,
        change_percent=None,
        unit="TWD",
        as_of=_roc_date_to_iso(str(row.get("Date") or "")),
        url="https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
        raw=row,
    )


def _twse_margin_point(row: dict[str, Any]) -> MarketContextPoint | None:
    """執行 twse margin point 的主要流程。"""
    code = str(row.get("股票代號") or "").strip()
    if not code:
        return None
    today = _to_float(row.get("融資今日餘額"))
    previous = _to_float(row.get("融資前日餘額"))
    short_today = _to_float(row.get("融券今日餘額"))
    short_previous = _to_float(row.get("融券前日餘額"))
    if today is None and short_today is None:
        return None
    raw = dict(row)
    raw["short_balance"] = short_today
    raw["short_previous_balance"] = short_previous
    return MarketContextPoint(
        source="twse_openapi",
        category="tw_margin",
        name=str(row.get("股票名稱") or code).strip(),
        symbol=code,
        value=today,
        previous_value=previous,
        change=(today - previous) if today is not None and previous is not None else None,
        change_percent=None,
        unit="shares",
        as_of=None,
        url="https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN",
        raw=raw,
    )


def fetch_twse_points(timeout_seconds: int, tracked_codes: list[str]) -> tuple[list[MarketContextPoint], list[SourceFailure]]:
    """抓取 fetch twse points 對應的資料或結果。"""
    points: list[MarketContextPoint] = []
    failures: list[SourceFailure] = []
    tracked = {code.strip() for code in tracked_codes if code.strip()}

    # 指數資料固定會抓；個股收盤與融資券則只抓追蹤名單，避免把整包 TWSE 明細都灌進 context。
    try:
        payload = http_get_json("https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX", timeout=timeout_seconds)
        for row in payload.get("data") or []:
            if isinstance(row, dict):
                point = _twse_index_point(row)
                if point is not None:
                    points.append(point)
    except Exception as exc:
        failures.append(SourceFailure(source="twse_openapi:MI_INDEX", error=str(exc)))

    if tracked:
        try:
            payload = http_get_json("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=timeout_seconds)
            for row in payload.get("data") or []:
                if isinstance(row, dict) and str(row.get("Code") or "").strip() in tracked:
                    point = _twse_stock_point(row)
                    if point is not None:
                        points.append(point)
        except Exception as exc:
            failures.append(SourceFailure(source="twse_openapi:STOCK_DAY_ALL", error=str(exc)))

        try:
            payload = http_get_json("https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN", timeout=timeout_seconds)
            for row in payload.get("data") or []:
                if isinstance(row, dict) and str(row.get("股票代號") or "").strip() in tracked:
                    point = _twse_margin_point(row)
                    if point is not None:
                        points.append(point)
        except Exception as exc:
            failures.append(SourceFailure(source="twse_openapi:MI_MARGN", error=str(exc)))

    return points, failures


def collect_market_context(config: MarketContextConfig) -> tuple[list[MarketContextPoint], list[SourceFailure]]:
    """彙整 collect market context 對應的資料或結果。"""
    all_points: list[MarketContextPoint] = []
    all_failures: list[SourceFailure] = []
    yahoo_points, yahoo_failures = fetch_yahoo_market_points(config.timeout_seconds)
    treasury_points, treasury_failures = fetch_treasury_points(config.timeout_seconds)
    fred_points: list[MarketContextPoint] = []
    fred_failures: list[SourceFailure] = []
    if config.fred_enabled:
        fred_points, fred_failures = fetch_fred_points(config.timeout_seconds, config.fred_series_ids)
    breadth_points: list[MarketContextPoint] = []
    breadth_failures: list[SourceFailure] = []
    if config.market_breadth_enabled:
        breadth_points, breadth_failures = fetch_market_breadth_points(config.timeout_seconds)
    ai_capex_points: list[MarketContextPoint] = []
    ai_capex_failures: list[SourceFailure] = []
    if config.ai_capex_enabled:
        ai_capex_points, ai_capex_failures = fetch_ai_capex_points(config.timeout_seconds, config.ai_capex_tickers)
    oil_points: list[MarketContextPoint] = []
    oil_failures: list[SourceFailure] = []
    if config.oil_supply_enabled:
        oil_points, oil_failures = fetch_oil_supply_demand_points(config.timeout_seconds)
    twse_points, twse_failures = fetch_twse_points(config.timeout_seconds, config.twse_codes)
    official_twse_stock_codes = {
        point.symbol for point in twse_points if point.category == "tw_tracked_stock" and point.symbol
    }
    tw_yahoo_points, tw_yahoo_failures = fetch_yahoo_tracked_tw_points(
        config.timeout_seconds,
        config.tw_yahoo_symbols,
        skip_codes=official_twse_stock_codes,
    )

    for points, failures in (
        (yahoo_points, yahoo_failures),
        (treasury_points, treasury_failures),
        (fred_points, fred_failures),
        (breadth_points, breadth_failures),
        (ai_capex_points, ai_capex_failures),
        (oil_points, oil_failures),
        (twse_points, twse_failures),
        (tw_yahoo_points, tw_yahoo_failures),
    ):
        all_points.extend(points)
        all_failures.extend(failures)
    return all_points, all_failures


def _fmt_pct(value: float | None) -> str:
    """格式化 fmt pct 對應的資料或結果。"""
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def _find(points: list[MarketContextPoint], name: str) -> MarketContextPoint | None:
    """執行 find 的主要流程。"""
    for point in points:
        if point.name == name or point.symbol == name:
            return point
    return None


def _build_summary_legacy(points: list[MarketContextPoint], failures: list[SourceFailure], now_local: datetime) -> str:
    """建立 build summary 對應的資料或結果。"""
    ndx = _find(points, "NASDAQ 100")
    sox = _find(points, "PHLX Semiconductor")
    vix = _find(points, "VIX")
    us10 = _find(points, "US Treasury 10Y")
    spread = _find(points, "US10Y2Y")
    fed_upper = _find(points, "DFEDTARU")
    rrp = _find(points, "RRPONTSYD")
    reserves = _find(points, "WRESBAL")
    hy_oas = _find(points, "BAMLH0A0HYM2")
    nfci = _find(points, "NFCI")
    stlfsi = _find(points, "STLFSI4")
    taiex = _find(points, "發行量加權股價指數")
    semi = _find(points, "半導體類指數")
    tsm = _find(points, "2330")

    lines = [f"早盤市場情境資料包 {now_local.date().isoformat()}"]
    if ndx or sox or vix:
        lines.append(
            "美股風險: "
            f"NDX {_fmt_pct(ndx.change_percent if ndx else None)}, "
            f"SOX {_fmt_pct(sox.change_percent if sox else None)}, "
            f"VIX {vix.value:.2f}" if vix and vix.value is not None else "VIX n/a"
        )
    if us10 or spread:
        us10_text = f"{us10.value:.2f}%" if us10 and us10.value is not None else "n/a"
        spread_text = f"{spread.value:.0f}bp" if spread and spread.value is not None else "n/a"
        lines.append(f"利率: US10Y {us10_text}, 10Y-2Y {spread_text}")
    if fed_upper or rrp or reserves:
        fed_text = f"{fed_upper.value:.2f}%" if fed_upper and fed_upper.value is not None else "n/a"
        rrp_text = _format_number(rrp.value) if rrp else "n/a"
        reserves_text = _format_number(reserves.value) if reserves else "n/a"
        lines.append(f"Fed/liquidity: target upper {fed_text}, RRP {rrp_text}, reserves {reserves_text}")
    if hy_oas or nfci or stlfsi:
        hy_text = f"{hy_oas.value:.2f}%" if hy_oas and hy_oas.value is not None else "n/a"
        nfci_text = _format_number(nfci.value) if nfci else "n/a"
        stress_text = _format_number(stlfsi.value) if stlfsi else "n/a"
        lines.append(f"Credit/stress: HY OAS {hy_text}, NFCI {nfci_text}, STLFSI4 {stress_text}")
    if taiex or semi:
        lines.append(
            "台股收盤基準: "
            f"加權 {_fmt_pct(taiex.change_percent if taiex else None)}, "
            f"半導體 {_fmt_pct(semi.change_percent if semi else None)}"
        )
    if tsm:
        change_text = f"{tsm.change:+.2f}" if tsm.change is not None else "n/a"
        lines.append(f"追蹤股: 2330 收 {tsm.value:.2f} 變動 {change_text}")
    lines.append(f"資料點: {len(points)}；來源錯誤: {len(failures)}")
    return "\n".join(lines)[:4500]


def _fmt_pp(value: float | None) -> str:
    """Format percentage-point values for compact summaries."""
    if value is None:
        return "n/a"
    return f"{value:+.2f}pp"


def _fmt_usd_billion(value: float | None) -> str:
    """Format USD values as billions when possible."""
    if value is None:
        return "n/a"
    return f"${value / 1_000_000_000:.1f}B"


def _first_by_category(points: list[MarketContextPoint], category: str) -> MarketContextPoint | None:
    """Return the first point in a category."""
    for point in points:
        if point.category == category:
            return point
    return None


def build_summary(points: list[MarketContextPoint], failures: list[SourceFailure], now_local: datetime) -> str:
    """Build clean Traditional Chinese summary text for the analysis prompt."""
    ndx = _find(points, "NASDAQ 100")
    sox = _find(points, "PHLX Semiconductor")
    vix = _find(points, "VIX")
    us10 = _find(points, "US Treasury 10Y")
    spread = _find(points, "US10Y2Y")
    fed_upper = _find(points, "DFEDTARU")
    rrp = _find(points, "RRPONTSYD")
    reserves = _find(points, "WRESBAL")
    hy_oas = _find(points, "BAMLH0A0HYM2")
    nfci = _find(points, "NFCI")
    stlfsi = _find(points, "STLFSI4")
    rsp_spy = _find(points, "RSP-SPY")
    qqew_qqq = _find(points, "QQEW-QQQ")
    iwm_spy = _find(points, "IWM-SPY")
    wti = _find(points, "DCOILWTICO")
    brent = _find(points, "DCOILBRENTEU")
    brent_wti = _find(points, "BRENT-WTI")
    crude_stocks = _find(points, "WCESTUS1")
    tracked_tw_stock = _first_by_category(points, "tw_tracked_stock")
    ai_points = [point for point in points if point.category == "ai_capex"]

    lines = [f"市場情境資料 {now_local.date().isoformat()}"]
    if ndx or sox or vix:
        vix_text = f"{vix.value:.2f}" if vix and vix.value is not None else "n/a"
        lines.append(
            "美股/風險: "
            f"NDX {_fmt_pct(ndx.change_percent if ndx else None)}, "
            f"SOX {_fmt_pct(sox.change_percent if sox else None)}, "
            f"VIX {vix_text}"
        )
    if us10 or spread:
        us10_text = f"{us10.value:.2f}%" if us10 and us10.value is not None else "n/a"
        spread_text = f"{spread.value:.0f}bp" if spread and spread.value is not None else "n/a"
        lines.append(f"利率: US10Y {us10_text}, 10Y-2Y {spread_text}")
    if fed_upper or rrp or reserves:
        fed_text = f"{fed_upper.value:.2f}%" if fed_upper and fed_upper.value is not None else "n/a"
        rrp_text = _format_number(rrp.value) if rrp else "n/a"
        reserves_text = _format_number(reserves.value) if reserves else "n/a"
        lines.append(f"Fed/liquidity: target upper {fed_text}, RRP {rrp_text}, reserves {reserves_text}")
    if hy_oas or nfci or stlfsi:
        hy_text = f"{hy_oas.value:.2f}%" if hy_oas and hy_oas.value is not None else "n/a"
        nfci_text = _format_number(nfci.value) if nfci else "n/a"
        stress_text = _format_number(stlfsi.value) if stlfsi else "n/a"
        lines.append(f"Credit/stress: HY OAS {hy_text}, NFCI {nfci_text}, STLFSI4 {stress_text}")
    if rsp_spy or qqew_qqq or iwm_spy:
        lines.append(
            "市場廣度: "
            f"RSP-SPY {_fmt_pp(rsp_spy.value if rsp_spy else None)}, "
            f"QQEW-QQQ {_fmt_pp(qqew_qqq.value if qqew_qqq else None)}, "
            f"IWM-SPY {_fmt_pp(iwm_spy.value if iwm_spy else None)}"
        )
    if ai_points:
        sample = ", ".join(f"{point.symbol} {_fmt_usd_billion(point.value)}" for point in ai_points[:4])
        lines.append(f"AI capex: {sample}; SEC companyfacts capex proxy, not pure AI-only spend")
    if wti or brent or brent_wti or crude_stocks:
        wti_text = f"{wti.value:.2f}" if wti and wti.value is not None else "n/a"
        brent_text = f"{brent.value:.2f}" if brent and brent.value is not None else "n/a"
        spread_text = f"{brent_wti.value:.2f}" if brent_wti and brent_wti.value is not None else "n/a"
        stock_text = _format_number(crude_stocks.value) if crude_stocks else "n/a"
        lines.append(f"油價/供需: WTI {wti_text}, Brent {brent_text}, Brent-WTI {spread_text}, US crude stocks ex-SPR {stock_text}")
    if tracked_tw_stock:
        change_text = f"{tracked_tw_stock.change:+.2f}" if tracked_tw_stock.change is not None else "n/a"
        value_text = f"{tracked_tw_stock.value:.2f}" if tracked_tw_stock.value is not None else "n/a"
        lines.append(f"台股追蹤: {tracked_tw_stock.symbol} {tracked_tw_stock.name} 收盤 {value_text}, 變動 {change_text}")

    lines.append(f"資料點: {len(points)}; 資料缺口: {len(failures)}")
    if failures:
        sample_failures = "; ".join(f"{failure.source}: {failure.error}" for failure in failures[:3])
        lines.append(f"需補資料: {sample_failures}")
    return "\n".join(lines)[:4500]


def _clamp_score(value: int) -> int:
    """Clamp deterministic scorecard values to the documented -2..+2 scale."""
    return max(-2, min(2, int(value)))


def _threshold_score(value: float | None, *, pos2: float, pos1: float, neg1: float, neg2: float) -> int:
    """Convert one continuous indicator into a bounded score."""
    if value is None:
        return 0
    if value >= pos2:
        return 2
    if value >= pos1:
        return 1
    if value <= neg2:
        return -2
    if value <= neg1:
        return -1
    return 0


def _point_date(value: str | None):
    """Parse a point ``as_of`` value into a date without making bad data fatal."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    if len(text) >= 10:
        try:
            return datetime.fromisoformat(text[:10]).date()
        except ValueError:
            return None
    return None


def _freshness(points: list[MarketContextPoint], now_local: datetime) -> dict[str, Any]:
    """Summarise freshness for one scorecard dimension."""
    dates = [parsed for point in points if (parsed := _point_date(point.as_of)) is not None]
    if not dates:
        return {"status": "missing", "newest_as_of": None, "age_days": None}
    newest = max(dates)
    age_days = (now_local.date() - newest).days
    if age_days <= 1:
        status = "fresh"
    elif age_days <= 7:
        status = "recent"
    else:
        status = "stale"
    return {"status": status, "newest_as_of": newest.isoformat(), "age_days": age_days}


def _scorecard_dimension(
    *,
    name: str,
    score: int,
    label: str,
    meaning: str,
    points: list[MarketContextPoint],
    evidence: list[str],
    counter_evidence: list[str],
    missing_data: list[str],
    now_local: datetime,
) -> dict[str, Any]:
    """Build one deterministic scorecard dimension payload."""
    source_symbols = []
    for point in points:
        if point.symbol and point.symbol not in source_symbols:
            source_symbols.append(point.symbol)
    return {
        "name": name,
        "score": _clamp_score(score),
        "label": label,
        "meaning": meaning,
        "evidence": evidence[:8] or ["無足夠資料"],
        "counter_evidence": counter_evidence[:6] or ["未見明確反向訊號"],
        "missing_data": missing_data[:8],
        "freshness": _freshness(points, now_local),
        "source_symbols": source_symbols,
        "source_count": len(points),
    }


def _scorecard_points(points: list[MarketContextPoint], symbols: tuple[str, ...]) -> list[MarketContextPoint]:
    """Return scorecard input points by symbol, preserving requested order."""
    result: list[MarketContextPoint] = []
    for symbol in symbols:
        point = _find(points, symbol)
        if point is not None:
            result.append(point)
    return result


def _breadth_score(points: list[MarketContextPoint], now_local: datetime) -> dict[str, Any]:
    """Score market breadth: positive means broader participation."""
    breadth_points = _scorecard_points(points, ("RSP-SPY", "QQEW-QQQ", "IWM-SPY"))
    values = [point.value for point in breadth_points if point.value is not None]
    average = sum(values) / len(values) if values else None
    score = _threshold_score(average, pos2=0.75, pos1=0.25, neg1=-0.25, neg2=-0.75)
    evidence = [
        f"{point.symbol}: 1D {_fmt_pp(point.value)}, 1M {_fmt_pp(point.previous_value)}, 3M {_fmt_pp(point.change)}"
        for point in breadth_points
    ]
    counter = []
    if score > 0:
        counter = [f"{point.symbol} 仍收斂 {_fmt_pp(point.value)}" for point in breadth_points if point.value is not None and point.value < -0.25]
    elif score < 0:
        counter = [f"{point.symbol} 仍擴散 {_fmt_pp(point.value)}" for point in breadth_points if point.value is not None and point.value > 0.25]
    missing = [
        f"missing breadth proxy {symbol}"
        for symbol in ("RSP-SPY", "QQEW-QQQ", "IWM-SPY")
        if _find(points, symbol) is None
    ]
    return _scorecard_dimension(
        name="breadth_health",
        score=score,
        label="市場廣度擴散" if score > 0 else "市場廣度收斂" if score < 0 else "市場廣度中性",
        meaning="+2=等權/小型股明顯跟上，-2=漲勢高度集中",
        points=breadth_points,
        evidence=evidence,
        counter_evidence=counter,
        missing_data=missing,
        now_local=now_local,
    )


def _ai_capex_score(points: list[MarketContextPoint], now_local: datetime) -> dict[str, Any]:
    """Score AI capex quality: positive means spending is better funded by cash flow."""
    ai_points = [point for point in points if point.category == "ai_capex"]
    positive_fcf = 0
    negative_fcf = 0
    high_growth = 0
    evidence: list[str] = []
    counter: list[str] = []
    missing: list[str] = []
    for point in ai_points:
        free_cash_flow = _to_float(point.raw.get("free_cash_flow_proxy")) if isinstance(point.raw, dict) else None
        if free_cash_flow is not None and free_cash_flow >= 0:
            positive_fcf += 1
        elif free_cash_flow is not None:
            negative_fcf += 1
        if point.change_percent is not None and point.change_percent > 50:
            high_growth += 1
            counter.append(f"{point.symbol} capex 成長偏快 {point.change_percent:+.1f}%")
        if free_cash_flow is None:
            missing.append(f"{point.symbol} free_cash_flow_proxy missing")
        evidence.append(
            f"{point.symbol}: capex {_fmt_usd_billion(point.value)}, "
            f"YoY {_fmt_pct(point.change_percent)}, FCF proxy {_fmt_usd_billion(free_cash_flow)}"
        )

    if not ai_points:
        score = 0
        missing.append("SEC companyfacts AI capex proxy missing")
    else:
        score = 0
        if positive_fcf >= max(1, len(ai_points) - 1):
            score += 1
        if len(ai_points) >= 3 and positive_fcf == len(ai_points) and high_growth <= 1:
            score += 1
        if negative_fcf >= 2:
            score -= 2
        elif negative_fcf == 1:
            score -= 1
        if high_growth >= max(2, len(ai_points) // 2 + 1) and positive_fcf < len(ai_points):
            score -= 1
    return _scorecard_dimension(
        name="ai_capex_quality",
        score=score,
        label="AI capex 品質較佳" if score > 0 else "AI capex 資金壓力較高" if score < 0 else "AI capex 品質待確認",
        meaning="+2=capex 由營運現金流支撐，-2=支出成長快且現金流緩衝不足",
        points=ai_points,
        evidence=evidence,
        counter_evidence=counter,
        missing_data=missing,
        now_local=now_local,
    )


def _energy_score(points: list[MarketContextPoint], now_local: datetime) -> dict[str, Any]:
    """Score energy shock risk: positive means lower shock pressure."""
    energy_points = _scorecard_points(points, ("DCOILWTICO", "DCOILBRENTEU", "BRENT-WTI", EIA_CRUDE_STOCKS_SERIES))
    wti = _find(points, "DCOILWTICO")
    brent = _find(points, "DCOILBRENTEU")
    brent_wti = _find(points, "BRENT-WTI")
    crude_stocks = _find(points, EIA_CRUDE_STOCKS_SERIES)
    price_values = [point.value for point in (wti, brent) if point is not None and point.value is not None]
    high_price = max(price_values) if price_values else None
    score = 0
    if high_price is not None:
        if high_price >= 130 or (brent_wti and brent_wti.value is not None and brent_wti.value >= 15):
            score = -2
        elif high_price >= 100 or (brent_wti and brent_wti.value is not None and brent_wti.value >= 8):
            score = -1
        elif high_price <= 70:
            score = 2
        elif high_price <= 80 and (not brent_wti or brent_wti.value is None or brent_wti.value < 5):
            score = 1
    if crude_stocks and crude_stocks.change is not None:
        if crude_stocks.change < -5000 and high_price is not None and high_price >= 90:
            score -= 1
        elif crude_stocks.change > 5000 and (high_price is None or high_price < 100):
            score += 1
    evidence = [
        f"WTI {_format_number(wti.value)}" if wti else "WTI missing",
        f"Brent {_format_number(brent.value)}" if brent else "Brent missing",
        f"Brent-WTI {_format_number(brent_wti.value)}" if brent_wti else "Brent-WTI missing",
    ]
    if crude_stocks:
        evidence.append(f"US crude stocks ex-SPR {_format_number(crude_stocks.value)}, change {_format_number(crude_stocks.change)}")
    counter = []
    if score < 0 and crude_stocks and crude_stocks.change is not None and crude_stocks.change > 0:
        counter.append(f"庫存增加 {_format_number(crude_stocks.change)}，可部分緩衝油價壓力")
    if score > 0 and crude_stocks and crude_stocks.change is not None and crude_stocks.change < 0:
        counter.append(f"庫存下滑 {_format_number(crude_stocks.change)}，低油價訊號仍需保守")
    missing = [
        label
        for point, label in (
            (wti, "WTI price missing"),
            (brent, "Brent price missing"),
            (crude_stocks, "EIA crude inventory missing"),
        )
        if point is None
    ]
    return _scorecard_dimension(
        name="energy_shock_risk",
        score=score,
        label="能源衝擊風險較低" if score > 0 else "能源衝擊風險升高" if score < 0 else "能源衝擊風險中性",
        meaning="+2=油價/價差壓力低，-2=油價或供需緊張足以壓估值",
        points=energy_points,
        evidence=evidence,
        counter_evidence=counter,
        missing_data=missing,
        now_local=now_local,
    )


def _credit_score(points: list[MarketContextPoint], now_local: datetime) -> dict[str, Any]:
    """Score credit stress: positive means credit/financial conditions are calm."""
    credit_points = _scorecard_points(points, ("BAMLH0A0HYM2", "BAMLC0A0CM", "BAA10Y", "NFCI", "STLFSI4"))
    hy_oas = _find(points, "BAMLH0A0HYM2")
    corp_oas = _find(points, "BAMLC0A0CM")
    baa_spread = _find(points, "BAA10Y")
    nfci = _find(points, "NFCI")
    stlfsi = _find(points, "STLFSI4")
    score = 0
    if (hy_oas and hy_oas.value is not None and hy_oas.value >= 5.0) or (
        stlfsi and stlfsi.value is not None and stlfsi.value >= 1.0
    ) or (nfci and nfci.value is not None and nfci.value >= 0.5):
        score = -2
    elif (hy_oas and hy_oas.value is not None and hy_oas.value >= 3.5) or (
        stlfsi and stlfsi.value is not None and stlfsi.value > 0
    ) or (nfci and nfci.value is not None and nfci.value > 0):
        score = -1
    elif (
        hy_oas and hy_oas.value is not None and hy_oas.value <= 3.0
        and nfci and nfci.value is not None and nfci.value < 0
        and stlfsi and stlfsi.value is not None and stlfsi.value < 0
    ):
        score = 2 if stlfsi.value <= -0.5 else 1
    evidence = [
        f"HY OAS {_format_number(hy_oas.value)}%" if hy_oas else "HY OAS missing",
        f"Corp OAS {_format_number(corp_oas.value)}%" if corp_oas else "Corp OAS missing",
        f"BAA10Y {_format_number(baa_spread.value)}%" if baa_spread else "BAA10Y missing",
        f"NFCI {_format_number(nfci.value)}" if nfci else "NFCI missing",
        f"STLFSI4 {_format_number(stlfsi.value)}" if stlfsi else "STLFSI4 missing",
    ]
    counter = []
    if score > 0:
        counter = [item for item in evidence if "missing" not in item and any(token in item for token in ("BAA10Y", "Corp OAS"))]
    elif score < 0 and hy_oas and hy_oas.value is not None and hy_oas.value < 3.5:
        counter.append(f"HY OAS {_format_number(hy_oas.value)}% 尚未進入壓力區")
    missing = [item for item in evidence if item.endswith("missing")]
    return _scorecard_dimension(
        name="credit_stress",
        score=score,
        label="信用壓力低" if score > 0 else "信用壓力升高" if score < 0 else "信用壓力中性",
        meaning="+2=信用/金融條件寬鬆，-2=信用利差或壓力指數進入警戒",
        points=credit_points,
        evidence=evidence,
        counter_evidence=counter,
        missing_data=missing,
        now_local=now_local,
    )


def _liquidity_score(points: list[MarketContextPoint], now_local: datetime) -> dict[str, Any]:
    """Score liquidity impulse: positive means marginal liquidity support."""
    liquidity_points = _scorecard_points(points, ("RRPONTSYD", "WRESBAL", "WTREGEN", "WALCL"))
    raw_score = 0
    evidence: list[str] = []
    counter: list[str] = []
    for point in liquidity_points:
        change = point.change
        evidence.append(f"{point.symbol}: level {_format_number(point.value)}, change {_format_number(change)} {point.unit}")
        if change is None:
            continue
        if point.symbol == "RRPONTSYD":
            raw_score += 1 if change < 0 else -1 if change > 0 else 0
        elif point.symbol == "WTREGEN":
            raw_score += 1 if change < 0 else -1 if change > 0 else 0
        elif point.symbol in {"WRESBAL", "WALCL"}:
            raw_score += 1 if change > 0 else -1 if change < 0 else 0
    score = 2 if raw_score >= 2 else 1 if raw_score == 1 else -2 if raw_score <= -2 else -1 if raw_score == -1 else 0
    if score > 0:
        counter = [
            f"{point.symbol} 方向偏緊 change {_format_number(point.change)}"
            for point in liquidity_points
            if point.change is not None
            and ((point.symbol in {"WRESBAL", "WALCL"} and point.change < 0) or (point.symbol in {"RRPONTSYD", "WTREGEN"} and point.change > 0))
        ]
    elif score < 0:
        counter = [
            f"{point.symbol} 方向偏寬 change {_format_number(point.change)}"
            for point in liquidity_points
            if point.change is not None
            and ((point.symbol in {"WRESBAL", "WALCL"} and point.change > 0) or (point.symbol in {"RRPONTSYD", "WTREGEN"} and point.change < 0))
        ]
    missing = [
        f"missing liquidity series {symbol}"
        for symbol in ("RRPONTSYD", "WRESBAL", "WTREGEN", "WALCL")
        if _find(points, symbol) is None
    ]
    return _scorecard_dimension(
        name="liquidity_impulse",
        score=score,
        label="流動性脈衝偏寬" if score > 0 else "流動性脈衝偏緊" if score < 0 else "流動性脈衝中性",
        meaning="+2=準備金/資產負債表或 RRP/TGA 變化支持風險資產，-2=邊際流動性收縮",
        points=liquidity_points,
        evidence=evidence,
        counter_evidence=counter,
        missing_data=missing,
        now_local=now_local,
    )


def _scorecard_regime_hint(dimensions: dict[str, dict[str, Any]], overall_score: int) -> str:
    """Translate scorecard totals into a compact regime hint."""
    if overall_score >= 4:
        return "總體條件偏支持風險資產，但仍需檢查估值與個股基本面。"
    if overall_score <= -4:
        return "總體條件偏防守，分析應優先處理壓力來源與下行情境。"
    severe = [name for name, payload in dimensions.items() if int(payload.get("score") or 0) <= -2]
    if severe:
        return f"總分接近中性，但 {', '.join(severe)} 有單點壓力，需放進反證段落。"
    return "總體條件混合，應把支持與反證並列，不用單一新聞決定方向。"


def _scorecard_hash(scorecard: dict[str, Any]) -> str:
    """Hash stable scorecard content for relay-event idempotency."""
    basis = {
        "version": scorecard.get("schema_version"),
        "overall_score": scorecard.get("overall_score"),
        "dimensions": {
            name: {
                "score": payload.get("score"),
                "evidence": payload.get("evidence"),
                "freshness": payload.get("freshness"),
                "source_symbols": payload.get("source_symbols"),
            }
            for name, payload in (scorecard.get("dimensions") or {}).items()
            if isinstance(payload, dict)
        },
    }
    return hashlib.sha1(json.dumps(basis, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def build_market_scorecard(
    points: list[MarketContextPoint],
    failures: list[SourceFailure],
    now_local: datetime,
) -> dict[str, Any]:
    """Build the deterministic daily market-context scorecard."""
    dimensions = {
        "breadth_health": _breadth_score(points, now_local),
        "ai_capex_quality": _ai_capex_score(points, now_local),
        "energy_shock_risk": _energy_score(points, now_local),
        "credit_stress": _credit_score(points, now_local),
        "liquidity_impulse": _liquidity_score(points, now_local),
    }
    overall_score = sum(int(payload.get("score") or 0) for payload in dimensions.values())
    scorecard: dict[str, Any] = {
        "schema_version": SCORECARD_VERSION,
        "scale": SCORECARD_SCALE,
        "as_of": now_local.isoformat(),
        "overall_score": overall_score,
        "regime_hint": _scorecard_regime_hint(dimensions, overall_score),
        "dimensions": dimensions,
        "source_failures": [asdict(failure) for failure in failures[:20]],
    }
    scorecard["input_hash"] = _scorecard_hash(scorecard)
    return scorecard


def _scorecard_summary(scorecard: dict[str, Any]) -> str:
    """Render a compact Chinese scorecard summary for prompt input."""
    dimensions = scorecard.get("dimensions") if isinstance(scorecard.get("dimensions"), dict) else {}
    lines = [
        f"市場 scorecard 總分 {int(scorecard.get('overall_score') or 0):+d}; {scorecard.get('regime_hint') or ''}".strip()
    ]
    for name in SCORECARD_DIMENSIONS:
        payload = dimensions.get(name) if isinstance(dimensions, dict) else None
        if not isinstance(payload, dict):
            continue
        evidence = "; ".join(str(item) for item in (payload.get("evidence") or [])[:2])
        counter = "; ".join(str(item) for item in (payload.get("counter_evidence") or [])[:1])
        freshness = payload.get("freshness") if isinstance(payload.get("freshness"), dict) else {}
        lines.append(
            f"{name}: {int(payload.get('score') or 0):+d} | {payload.get('label')} | "
            f"依據: {evidence or 'n/a'} | 反證: {counter or 'n/a'} | 新鮮度: {freshness.get('status', 'n/a')}"
        )
    return "\n".join(lines)[:4500]


def _scorecard_to_event(
    scorecard: dict[str, Any],
    config: MarketContextConfig,
    generated_at: str,
    now_local: datetime,
) -> RelayEvent:
    """Convert the deterministic scorecard into a stored-only relay event."""
    overall_score = int(scorecard.get("overall_score") or 0)
    return RelayEvent(
        event_id=_stable_event_id(
            "scorecard",
            config.analysis_slot,
            now_local.date().isoformat(),
            scorecard.get("input_hash"),
        ),
        source="market_context:scorecard",
        title=f"Market scorecard {now_local.date().isoformat()} overall {overall_score:+d}",
        url=f"internal://market_context/scorecard/{config.analysis_slot}/{now_local.date().isoformat()}",
        summary=_scorecard_summary(scorecard),
        published_at=generated_at,
        log_only=False,
        raw={
            "stored_only": True,
            "event_type": "market_context_scorecard",
            "dimension": "market_context",
            "slot": config.analysis_slot,
            "scheduled_time_local": config.scheduled_time_local,
            "generated_at": generated_at,
            "scorecard": scorecard,
        },
    )


def _stable_event_id(*parts: Any) -> str:
    """執行 stable event id 的主要流程。"""
    key = "|".join(str(part) for part in parts if part is not None)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return f"market-context-{digest}"


def _format_number(value: float | None) -> str:
    """格式化 format number 對應的資料或結果。"""
    if value is None:
        return "n/a"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _point_title(point: MarketContextPoint) -> str:
    """執行 point title 的主要流程。"""
    value = _format_number(point.value)
    if point.change_percent is not None:
        return f"{point.name} {value} ({point.change_percent:+.2f}%)"
    if point.change is not None:
        return f"{point.name} {value} ({point.change:+.4f})"
    return f"{point.name} {value} {point.unit}".strip()


def _point_summary(point: MarketContextPoint) -> str:
    """執行 point summary 的主要流程。"""
    fields = [
        f"category={point.category}",
        f"symbol={point.symbol}",
        f"value={_format_number(point.value)}",
        f"unit={point.unit}",
    ]
    if point.previous_value is not None:
        fields.append(f"previous={_format_number(point.previous_value)}")
    if point.change is not None:
        fields.append(f"change={_format_number(point.change)}")
    if point.change_percent is not None:
        fields.append(f"change_percent={point.change_percent:+.2f}%")
    if point.as_of:
        fields.append(f"as_of={point.as_of}")
    return "; ".join(fields)


def _point_to_event(point: MarketContextPoint, config: MarketContextConfig, generated_at: str) -> RelayEvent:
    """執行 point to event 的主要流程。"""
    return RelayEvent(
        event_id=_stable_event_id(
            point.source,
            point.category,
            point.symbol,
            point.as_of,
            point.value,
            point.change,
            config.analysis_slot,
        ),
        source=f"market_context:{point.source}",
        title=_point_title(point),
        url=point.url,
        summary=_point_summary(point),
        published_at=point.as_of or generated_at,
        log_only=False,
        raw={
            "stored_only": True,
            "event_type": "market_context_point",
            "dimension": "market_context",
            "slot": config.analysis_slot,
            "scheduled_time_local": config.scheduled_time_local,
            "generated_at": generated_at,
            "point": asdict(point),
        },
    )


def build_market_context_events(
    points: list[MarketContextPoint],
    failures: list[SourceFailure],
    config: MarketContextConfig,
    now_local: datetime,
) -> list[RelayEvent]:
    """建立 build market context events 對應的資料或結果。"""
    generated_at = now_local.isoformat()
    scorecard = build_market_scorecard(points, failures, now_local) if config.scorecard_enabled else None
    # collector summary event 是整包 context 的索引入口：
    # 單點資料看細節，summary event 看本輪抓了多少點、哪幾個來源失敗。
    events = [_point_to_event(point, config, generated_at) for point in points]
    if scorecard is not None:
        events.append(_scorecard_to_event(scorecard, config, generated_at, now_local))
    events.append(
        RelayEvent(
            event_id=_stable_event_id("summary", config.analysis_slot, now_local.date().isoformat()),
            source="market_context:collector",
            title=f"Market context collected {now_local.date().isoformat()} {config.analysis_slot}",
            url=f"internal://market_context/{config.analysis_slot}/{now_local.date().isoformat()}",
            summary=build_summary(points, failures, now_local),
            published_at=generated_at,
            log_only=False,
            raw={
                "stored_only": True,
                "event_type": "market_context_collection",
                "dimension": "market_context",
                "slot": config.analysis_slot,
                "scheduled_time_local": config.scheduled_time_local,
                "generated_at": generated_at,
                "twse_codes": config.twse_codes,
                "tw_yahoo_symbols": [asdict(item) for item in config.tw_yahoo_symbols],
                "fred_enabled": config.fred_enabled,
                "fred_series_ids": list(config.fred_series_ids) or [spec.series_id for spec in FRED_SERIES_SPECS],
                "market_breadth_enabled": config.market_breadth_enabled,
                "ai_capex_enabled": config.ai_capex_enabled,
                "ai_capex_tickers": list(config.ai_capex_tickers),
                "oil_supply_enabled": config.oil_supply_enabled,
                "scorecard_enabled": config.scorecard_enabled,
                "scorecard_input_hash": scorecard.get("input_hash") if scorecard else None,
                "scorecard_overall_score": scorecard.get("overall_score") if scorecard else None,
                "scorecard_dimension_scores": {
                    name: payload.get("score")
                    for name, payload in ((scorecard or {}).get("dimensions") or {}).items()
                    if isinstance(payload, dict)
                },
                "oil_supply_series_ids": [spec.series_id for spec in ENERGY_FRED_SERIES_SPECS],
                "eia_crude_stocks_series": EIA_CRUDE_STOCKS_SERIES,
                "eia_api_key_configured": bool((os.getenv("EIA_API_KEY") or "").strip()),
                "point_count": len(points),
                "failures": [asdict(failure) for failure in failures],
            },
        )
    )
    return events


def run_once(config: MarketContextConfig) -> dict[str, Any]:
    """執行單次任務流程並回傳結果。"""
    relay_settings = load_settings(config.env_file)
    if not relay_settings.mysql_enabled:
        raise RuntimeError("Market context requires RELAY_MYSQL_ENABLED=true")

    now_local = datetime.now().astimezone()
    points, failures = collect_market_context(config)
    events = build_market_context_events(points, failures, config, now_local)
    store = MySqlEventStore(relay_settings)
    store.initialize()
    stored = 0
    duplicates = 0
    for event in events:
        if store.enqueue_event_if_new(event):
            stored += 1
        else:
            duplicates += 1
    logger.info(
        "Market context events stored: slot=%s points=%d events=%d stored=%d duplicates=%d failures=%d",
        config.analysis_slot,
        len(points),
        len(events),
        stored,
        duplicates,
        len(failures),
    )
    return {
        "ok": True,
        "analysis_date": now_local.date().isoformat(),
        "analysis_slot": config.analysis_slot,
        "points": len(points),
        "events": len(events),
        "stored": stored,
        "duplicates": duplicates,
        "failures": len(failures),
    }


def main() -> int:
    """程式入口，負責執行此模組的主要流程。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = _build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )
    try:
        config = _load_config(args)
        result = run_once(config)
        logger.info("Market context result: %s", result)
        return 0
    except Exception as exc:
        logger.error("Market context failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
