from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import sys
from typing import Any
from xml.etree import ElementTree as ET

from event_relay.config import load_settings
from event_relay.service import MySqlEventStore, RelayEvent
from news_collector.http_client import http_get_json, http_get_text


logger = logging.getLogger(__name__)

PROMPT_VERSION = "market-context-v1"
DEFAULT_ANALYSIS_SLOT = "market_context_pre_tw_open"
DEFAULT_SCHEDULED_TIME = "07:20"

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
)

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
    return MarketContextConfig(
        env_file=args.env_file,
        analysis_slot=(os.getenv("MARKET_CONTEXT_ANALYSIS_SLOT") or args.analysis_slot).strip() or DEFAULT_ANALYSIS_SLOT,
        scheduled_time_local=(os.getenv("MARKET_CONTEXT_SCHEDULED_TIME") or args.scheduled_time).strip()
        or DEFAULT_SCHEDULED_TIME,
        timeout_seconds=max(5, int(os.getenv("MARKET_CONTEXT_TIMEOUT_SECONDS") or args.timeout_seconds)),
        twse_codes=twse_codes,
    )


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
    for points, failures in (
        fetch_yahoo_market_points(config.timeout_seconds),
        fetch_treasury_points(config.timeout_seconds),
        fetch_twse_points(config.timeout_seconds, config.twse_codes),
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


def build_summary(points: list[MarketContextPoint], failures: list[SourceFailure], now_local: datetime) -> str:
    """建立 build summary 對應的資料或結果。"""
    ndx = _find(points, "NASDAQ 100")
    sox = _find(points, "PHLX Semiconductor")
    vix = _find(points, "VIX")
    us10 = _find(points, "US Treasury 10Y")
    spread = _find(points, "US10Y2Y")
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
    # collector summary event 是整包 context 的索引入口：
    # 單點資料看細節，summary event 看本輪抓了多少點、哪幾個來源失敗。
    events = [_point_to_event(point, config, generated_at) for point in points]
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
