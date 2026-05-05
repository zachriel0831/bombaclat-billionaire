"""Convert structured market analyses into reviewable trade signals."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import hashlib
import json
import logging
import re
import sys
from typing import Any

from event_relay.config import load_settings
from event_relay.service import MySqlEventStore, TradeSignalRecord


logger = logging.getLogger(__name__)
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-_]{1,16}$")
_TW_MARKETS = {"TW", "TSE", "TWSE", "TPEx", "OTC"}
_DIRECTION_MAP = {
    "bullish": "long",
    "bearish": "short",
    "mixed": "watch",
    "neutral": "watch",
    "long": "long",
    "short": "short",
    "watch": "watch",
    "avoid": "avoid",
}
_DEFAULT_ENTRY_TIMING = "09:05後，確認價格落在進場區且量能未失守；不追開盤急拉"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TW_STOCK_NAME_BY_TICKER = {
    "0050": "元大台灣50",
    "2308": "台達電",
    "2317": "鴻海",
    "2330": "台積電",
    "2351": "順德",
    "2382": "廣達",
    "2454": "聯發科",
    "2485": "兆赫",
    "2881": "富邦金",
    "2882": "國泰金",
    "3231": "緯創",
    "3535": "晶彩科",
    "3711": "日月光投控",
    "3715": "定穎投控",
    "4749": "新應材",
}


def build_trade_signals_from_analysis(
    *,
    analysis_id: int,
    analysis_date: str,
    analysis_slot: str,
    structured_payload: dict[str, Any] | None,
    pipeline_telemetry: dict[str, Any] | None = None,
) -> list[TradeSignalRecord]:
    """Build pending-review trade signals from structured analysis JSON."""
    if not isinstance(structured_payload, dict):
        return []

    evidence_by_ticker = _stage3_evidence_by_ticker(pipeline_telemetry)
    global_confidence = _clean_text(structured_payload.get("confidence"))
    raw_items = _iter_signal_items(structured_payload)
    signals: list[TradeSignalRecord] = []
    seen_keys: set[str] = set()

    for item in raw_items:
        ticker = _normalize_ticker(item.get("ticker") or item.get("symbol"))
        if not ticker:
            continue
        market = _normalize_market(item.get("market"))
        if market not in _TW_MARKETS:
            continue
        direction = _normalize_direction(item.get("direction") or item.get("side"))
        strategy_type = _normalize_strategy_type(
            item.get("strategy_type") or item.get("setup_type") or item.get("holding_horizon")
        )
        idempotency_key = _build_idempotency_key(
            analysis_id=analysis_id,
            analysis_date=analysis_date,
            analysis_slot=analysis_slot,
            market=market,
            ticker=ticker,
            direction=direction,
            strategy_type=strategy_type,
        )
        signal_key = f"sig_{idempotency_key[:24]}"
        if signal_key in seen_keys:
            continue
        seen_keys.add(signal_key)

        source_event_ids = _coerce_list(
            item.get("source_event_ids")
            or item.get("evidence_ids")
            or item.get("evidence_refs")
            or evidence_by_ticker.get(ticker)
        )
        raw_json = {
            "source": "t_market_analyses.structured_json",
            "item": item,
            "trace": {
                "analysis_id": analysis_id,
                "analysis_date": analysis_date,
                "analysis_slot": analysis_slot,
                "source_event_ids": source_event_ids,
            },
            "guardrail": "LLM signal only; review/risk gate required before order intent.",
        }

        signals.append(
            TradeSignalRecord(
                signal_key=signal_key,
                idempotency_key=idempotency_key,
                analysis_id=analysis_id,
                analysis_date=analysis_date,
                analysis_slot=analysis_slot,
                market=market,
                ticker=ticker,
                name=_resolve_stock_name(ticker, item.get("name") or item.get("company_name") or item.get("company")),
                signal_type="analysis_stock_watch",
                strategy_type=strategy_type,
                direction=direction,
                confidence=_clean_text(item.get("confidence")) or global_confidence,
                entry_zone_json=_json_or_none(_first_present(item, "entry_zone", "entry", "entry_price_range")),
                invalidation_json=_json_or_none(_first_present(item, "invalidation", "stop_loss", "stop")),
                take_profit_zone_json=_json_or_none(
                    _first_present(item, "take_profit_zone", "tp_zone", "take_profit", "target_zone")
                ),
                holding_horizon=_clean_text(item.get("holding_horizon") or item.get("time_horizon")),
                rationale=_clean_text(item.get("rationale") or item.get("thesis") or item.get("reason")),
                risk_notes_json=_json_or_none(item.get("risk_notes") or item.get("risks")),
                source_event_ids_json=_json_or_none(source_event_ids),
                status="pending_review",
                raw_json=json.dumps(raw_json, ensure_ascii=False),
            )
        )
    return signals


def build_quote_event_trade_signals(
    *,
    analysis_id: int,
    analysis_date: str,
    analysis_slot: str,
    events: Iterable[Any],
    max_signals: int = 5,
    preferred_tickers: Iterable[Any] | None = None,
) -> list[TradeSignalRecord]:
    """Build fallback long signals from recent Taiwan quote/context events.

    This is only used when the LLM pipeline cannot produce structured
    ``stock_watch`` rows. Signals remain pending review; they are not orders.
    """
    if analysis_slot != "pre_tw_open":
        return []

    preferred = _normalize_ticker_set(preferred_tickers)
    candidates: dict[str, dict[str, Any]] = {}
    for event in events:
        candidate = _fallback_candidate_from_event(event)
        if candidate is None:
            continue
        ticker = str(candidate["ticker"])
        current = candidates.get(ticker)
        event_row_id = candidate.get("event_row_id")
        if current is None or _safe_int(event_row_id) > _safe_int(current.get("event_row_id")):
            candidates[ticker] = candidate

    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            1 if str(item.get("ticker") or "") in preferred else 0,
            float(item.get("change_pct") or 0),
            int(item.get("volume") or 0),
        ),
        reverse=True,
    )[: max(1, min(int(max_signals), 5))]

    signals: list[TradeSignalRecord] = []
    for item in ranked:
        ticker = str(item["ticker"])
        price = float(item["price"])
        change_pct = float(item["change_pct"])
        confidence = "medium" if change_pct >= 3 else "low"
        entry_zone = {
            "low": _round_tw_price(price * 0.985),
            "high": _round_tw_price(price * 1.005),
            "timing": _DEFAULT_ENTRY_TIMING,
            "basis": item.get("entry_basis") or "fallback_price_reference",
        }
        invalidation = {
            "price": _round_tw_price(price * 0.965),
            "basis": item.get("stop_basis") or "fallback_stop_reference",
        }
        take_profit = {
            "first": _round_tw_price(price * 1.04),
            "second": _round_tw_price(price * 1.08),
            "basis": item.get("target_basis") or "fallback_target_reference",
        }
        source_event_ids = [item["event_row_id"]] if item.get("event_row_id") is not None else []
        idempotency_key = _build_idempotency_key(
            analysis_id=analysis_id,
            analysis_date=analysis_date,
            analysis_slot=analysis_slot,
            market="TW",
            ticker=ticker,
            direction="long",
            strategy_type="swing",
        )
        raw_json = {
            "source": item.get("source_kind") or "fallback_stock_watch",
            "price": price,
            "change_pct": change_pct,
            "as_of": item.get("as_of"),
            "trace": {
                "analysis_id": analysis_id,
                "analysis_date": analysis_date,
                "analysis_slot": analysis_slot,
                "source_event_ids": source_event_ids,
            },
            "guardrail": "Quote fallback signal only; review/risk gate required before order intent.",
        }
        signals.append(
            TradeSignalRecord(
                signal_key=f"sig_{idempotency_key[:24]}",
                idempotency_key=idempotency_key,
                analysis_id=analysis_id,
                analysis_date=analysis_date,
                analysis_slot=analysis_slot,
                market="TW",
                ticker=ticker,
                name=_clean_text(item.get("name")),
                signal_type=str(item.get("signal_type") or "quote_fallback_stock_watch"),
                strategy_type="swing",
                direction="long",
                confidence=confidence,
                entry_zone_json=json.dumps(entry_zone, ensure_ascii=False),
                invalidation_json=json.dumps(invalidation, ensure_ascii=False),
                take_profit_zone_json=json.dumps(take_profit, ensure_ascii=False),
                holding_horizon="short_to_medium",
                rationale=_clean_fallback_rationale(item.get("rationale")),
                risk_notes_json=json.dumps(
                    [
                        "LLM structured output unavailable or fewer than five candidates",
                        "Must pass independent review and risk gate",
                    ],
                    ensure_ascii=False,
                ),
                source_event_ids_json=json.dumps(source_event_ids, ensure_ascii=False),
                status="pending_review",
                raw_json=json.dumps(raw_json, ensure_ascii=False),
            )
        )
    return signals


def _fallback_candidate_from_event(event: Any) -> dict[str, Any] | None:
    """Extract one fallback candidate from supported event-shaped inputs."""
    source = str(getattr(event, "source", "") or "")
    if source == "yfinance_taiwan":
        return _fallback_candidate_from_yfinance_event(event)
    if source.startswith("market_context:"):
        return _fallback_candidate_from_twse_context_event(event)
    return None


def _fallback_candidate_from_yfinance_event(event: Any) -> dict[str, Any] | None:
    """Extract Taiwan quote fallback candidate from legacy yfinance relay events."""
    payload = _json_object_or_none(getattr(event, "summary", None))
    if payload is None:
        raw = _json_object_or_none(getattr(event, "raw_json", None))
        payload = _json_object_or_none((raw or {}).get("summary")) if isinstance(raw, dict) else None
    if not isinstance(payload, dict):
        return None

    ticker = _normalize_ticker(payload.get("symbol"))
    if not ticker:
        return None
    price = _to_float(payload.get("price"))
    change_pct = _to_float(payload.get("change_pct"))
    if price is None or price <= 0 or change_pct is None:
        return None

    name = _resolve_stock_name(ticker, payload.get("name"))
    return {
        "ticker": ticker,
        "name": name,
        "price": price,
        "change_pct": change_pct,
        "volume": _safe_int(payload.get("volume")),
        "event_row_id": getattr(event, "row_id", None),
        "signal_type": "quote_fallback_stock_watch",
        "source_kind": "yfinance_taiwan_quote_fallback",
        "entry_basis": "latest_yfinance_taiwan_price",
        "as_of": payload.get("last_ts"),
        "rationale": (
            f"{name or ticker} 最新台股報價{_format_change_phrase(change_pct)}，"
            "搭配早盤偏多與AI/半導體主線觀察。"
        ),
    }


def _fallback_candidate_from_twse_context_event(event: Any) -> dict[str, Any] | None:
    """Extract fallback candidate from tracked-stock market context events."""
    raw = _json_object_or_none(getattr(event, "raw_json", None))
    point = raw.get("point") if isinstance(raw, dict) else None
    if not isinstance(point, dict) or point.get("category") != "tw_tracked_stock":
        return None

    raw_point = point.get("raw") if isinstance(point.get("raw"), dict) else {}
    ticker = _normalize_ticker(point.get("symbol") or raw_point.get("Code"))
    if not ticker:
        return None
    price = _to_float(point.get("value") or raw_point.get("ClosingPrice"))
    if price is None or price <= 0:
        return None

    change = _to_float(point.get("change") or raw_point.get("Change"))
    previous = _to_float(point.get("previous_value"))
    if previous is None and change is not None:
        previous = price - change
    change_pct = _to_float(point.get("change_percent"))
    if change_pct is None:
        change_pct = _calculate_change_pct(price=price, previous=previous)

    name = _resolve_stock_name(ticker, point.get("name") or raw_point.get("Name"))
    as_of = _clean_text(point.get("as_of") or raw_point.get("Date"))
    point_source = _clean_text(point.get("source")) or str(getattr(event, "source", "")).split(":", 1)[-1]
    source_label = "TWSE官方收盤基準" if point_source == "twse_openapi" else "市場情境報價"
    source_kind = (
        "twse_openapi_tracked_stock_fallback"
        if point_source == "twse_openapi"
        else f"{point_source}_tracked_stock_fallback"
    )
    entry_basis = (
        "official_twse_tracked_stock_close"
        if point_source == "twse_openapi"
        else "market_context_tracked_stock_price"
    )
    return {
        "ticker": ticker,
        "name": name,
        "price": price,
        "change_pct": change_pct if change_pct is not None else 0.0,
        "volume": _safe_int(raw_point.get("TradeVolume")),
        "event_row_id": getattr(event, "row_id", None),
        "signal_type": "context_fallback_stock_watch",
        "source_kind": source_kind,
        "entry_basis": entry_basis,
        "as_of": as_of,
        "rationale": (
            f"{name or ticker} {source_label}{_format_change_phrase(change_pct or 0.0)}"
            f"{f'（{as_of}）' if as_of else ''}；需開盤量價確認。"
        ),
    }


def _calculate_change_pct(*, price: float, previous: float | None) -> float | None:
    """Calculate percent change when TWSE context provides price/change only."""
    if previous in (None, 0):
        return None
    return round((price - previous) / previous * 100.0, 2)


def _clean_fallback_rationale(value: Any) -> str:
    """Keep fallback signal text short and remove repeated watchlist boilerplate."""
    text = str(value or "").strip()
    boilerplate = "作為早盤 " + "watchlist 補位"
    for phrase in (f"{boilerplate}；需開盤量價確認。", f"{boilerplate}；需開盤量價確認", boilerplate):
        text = text.replace(phrase, "需開盤量價確認。")
    text = text.replace("需開盤量價確認。；", "需開盤量價確認；")
    if text and "需開盤量價確認" not in text:
        text = f"{text.rstrip('。')}；需開盤量價確認。"
    return text or "需開盤量價確認。"


def sync_trade_signals_from_recent_analyses(
    store: MySqlEventStore, *, days: int = 14, limit: int = 50
) -> dict[str, int]:
    """Backfill signals from recent stored market analyses."""
    rows = store.fetch_recent_market_analyses_for_signals(days=days, limit=limit)
    analyses_processed = 0
    signals_stored = 0
    for row in rows:
        structured_payload = _json_object_or_none(row.structured_json)
        raw_payload = _json_object_or_none(row.raw_json)
        pipeline_telemetry = raw_payload.get("pipeline_stages") if isinstance(raw_payload, dict) else None
        signals = build_trade_signals_from_analysis(
            analysis_id=row.row_id,
            analysis_date=row.analysis_date,
            analysis_slot=row.analysis_slot,
            structured_payload=structured_payload,
            pipeline_telemetry=pipeline_telemetry,
        )
        signals_stored += store.replace_trade_signals_for_analysis(row.row_id, signals)
        analyses_processed += 1
    return {"analyses_processed": analyses_processed, "signals_stored": signals_stored}


def build_trade_signal_recommendation_section(recommendations: list[dict[str, Any]]) -> str:
    """Build a deterministic report section from stored trade-signal rows."""
    lines = ["## 今日個股觀察", "短中線推薦買進候選（t_trade_signals）"]
    if not recommendations:
        lines.append("資料缺口：目前沒有可用的 long swing/medium 候選；不可硬湊下單。")
        return "\n".join(lines)

    rendered = 0
    for idx, item in enumerate(recommendations[:5], start=1):
        ticker = str(item.get("ticker") or "").strip()
        if not ticker:
            continue
        rendered += 1
        name = _resolve_stock_name(ticker, item.get("name"))
        label = f"{ticker} {name}" if name else ticker
        strategy = _clean_text(item.get("strategy_type")) or "swing/medium"
        confidence = _clean_text(item.get("confidence")) or "unknown"
        entry = _format_zone(item.get("entry_zone")) or "待盤中確認"
        take_profit = _format_zone(item.get("take_profit_zone")) or "待盤中確認"
        invalidation = _format_zone(item.get("invalidation")) or "待盤中確認"
        rationale = _clean_text(item.get("rationale")) or "依早盤分析訊號"
        lines.append(
            f"{idx}. {label}｜{_format_action_label(strategy, confidence)}｜"
            f"進場 {entry}｜停利 {take_profit}｜停損 {invalidation}｜信心 {confidence}｜{rationale}"
        )
    if rendered == 0:
        lines.append("資料缺口：目前沒有可用的 long swing/medium 候選；不可硬湊下單。")
    elif rendered < 5:
        lines.append(f"資料缺口：目前符合 long swing/medium 的候選只有 {rendered} 檔，未硬湊滿 5 檔。")
    return "\n".join(lines) if len(lines) > 1 else ""


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for one-shot signal extraction."""
    parser = argparse.ArgumentParser(description="Extract t_trade_signals from recent t_market_analyses rows")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main() -> int:
    """Run one-shot trade-signal extraction."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )
    settings = load_settings(args.env_file)
    if not settings.mysql_enabled:
        raise RuntimeError("trade signal extraction requires RELAY_MYSQL_ENABLED=true")
    store = MySqlEventStore(settings)
    store.initialize()
    result = sync_trade_signals_from_recent_analyses(store, days=args.days, limit=args.limit)
    logger.info("Trade signal extraction result: %s", result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _iter_signal_items(structured_payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield supported stock recommendation arrays without reparsing prose."""
    for key in ("trade_ideas", "stock_watch"):
        value = structured_payload.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict):
                yield item


def _stage3_evidence_by_ticker(pipeline_telemetry: dict[str, Any] | None) -> dict[str, list[Any]]:
    """Extract ticker -> evidence_ids from stored stage3 telemetry if present."""
    if not isinstance(pipeline_telemetry, dict):
        return {}
    stage3 = pipeline_telemetry.get("tw_mapping") or pipeline_telemetry.get("stage3_output")
    if not isinstance(stage3, dict):
        return {}
    result: dict[str, list[Any]] = {}
    for item in stage3.get("stock_watch") or []:
        if not isinstance(item, dict):
            continue
        ticker = _normalize_ticker(item.get("ticker"))
        if ticker:
            result[ticker] = _coerce_list(item.get("evidence_ids"))
    return result


def _normalize_ticker(value: Any) -> str | None:
    """Normalize a ticker while rejecting prose-like values."""
    text = _clean_text(value)
    if not text:
        return None
    text = text.upper().replace(".TWO", "").replace(".TW", "")
    return text if _TICKER_RE.match(text) else None


def _normalize_ticker_set(values: Iterable[Any] | None) -> set[str]:
    """Normalize a caller-provided ticker list for ranking and matching."""
    result: set[str] = set()
    for value in values or []:
        ticker = _normalize_ticker(value)
        if ticker:
            result.add(ticker)
    return result


def _resolve_stock_name(ticker: Any, value: Any = None) -> str | None:
    """Prefer a Traditional Chinese stock name when the row only has a ticker."""
    provided = _clean_text(value)
    normalized = _normalize_ticker(ticker)
    canonical = _TW_STOCK_NAME_BY_TICKER.get(normalized or "")
    if canonical and (not provided or not _CJK_RE.search(provided)):
        return canonical
    return provided


def _normalize_market(value: Any) -> str:
    """Default analysis stock-watch output to Taiwan market."""
    text = _clean_text(value)
    if not text:
        return "TW"
    upper = text.upper()
    if upper in {"TW", "TSE", "TWSE"}:
        return "TW"
    if upper in {"TPEX", "OTC"}:
        return "TPEx"
    return upper


def _normalize_direction(value: Any) -> str:
    """Map analysis direction into execution-neutral signal direction."""
    text = (_clean_text(value) or "watch").lower()
    return _DIRECTION_MAP.get(text, "watch")


def _normalize_strategy_type(value: Any) -> str:
    """Keep strategy coarse; detailed rules belong to review/risk layers."""
    text = (_clean_text(value) or "").lower()
    if text in {"intraday", "daytrade", "day_trade", "當沖"} or "intraday" in text or "當沖" in text:
        return "intraday"
    if text in {"swing", "short_term", "短線"} or "swing" in text or "短" in text:
        return "swing"
    if text in {"medium", "medium_term", "中線"} or "medium" in text or "中" in text:
        return "medium"
    return "watch"


def _build_idempotency_key(
    *,
    analysis_id: int,
    analysis_date: str,
    analysis_slot: str,
    market: str,
    ticker: str,
    direction: str,
    strategy_type: str,
) -> str:
    """Stable duplicate guard for analysis-derived signals."""
    raw = "|".join(
        [
            str(int(analysis_id)),
            analysis_date.strip(),
            analysis_slot.strip(),
            market.strip().upper(),
            ticker.strip().upper(),
            direction.strip().lower(),
            strategy_type.strip().lower(),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    """Return the first present value among compatible field aliases."""
    for key in keys:
        if key in item and item.get(key) not in (None, ""):
            return item.get(key)
    return None


def _coerce_list(value: Any) -> list[Any]:
    """Return list-like values as a compact list."""
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _json_or_none(value: Any) -> str | None:
    """Serialize structured optional fields for MySQL JSON columns."""
    if value in (None, "", []):
        return None
    return json.dumps(value, ensure_ascii=False)


def _clean_text(value: Any) -> str | None:
    """Trim scalar values and drop empty strings."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_object_or_none(value: str | None) -> dict[str, Any] | None:
    """Parse a JSON object string and ignore arrays/scalars."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _to_float(value: Any) -> float | None:
    """Return a float when the quote payload contains a numeric value."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.replace(",", "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _safe_int(value: Any) -> int:
    """Best-effort int conversion for ranking and trace IDs."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.replace(",", "").strip()))
        except ValueError:
            return 0
    return 0


def _round_tw_price(value: float) -> float:
    """Round reference levels to common Taiwan stock tick sizes."""
    if value < 10:
        tick = 0.01
    elif value < 50:
        tick = 0.05
    elif value < 100:
        tick = 0.1
    elif value < 500:
        tick = 0.5
    elif value < 1000:
        tick = 1.0
    else:
        tick = 5.0
    rounded = round(value / tick) * tick
    return round(rounded, 2)


def _format_change_phrase(change_pct: float) -> str:
    """Format quote movement without implying weak names are rising."""
    if change_pct > 0:
        return f"上漲 {change_pct:.2f}%"
    if change_pct < 0:
        return f"下跌 {abs(change_pct):.2f}%"
    return "持平"


def _format_strategy_label(value: str) -> str:
    """Convert internal strategy labels into user-facing Chinese text."""
    normalized = (value or "").strip().lower()
    if normalized == "swing":
        return "波段"
    if normalized == "medium":
        return "中線"
    if normalized == "intraday":
        return "當沖"
    if normalized == "short_to_medium":
        return "短中線"
    return value or "短中線"


def _format_action_label(strategy: str, confidence: str) -> str:
    """Render a buy-side signal as a natural action phrase."""
    prefix = "建議觀察" if (confidence or "").strip().lower() == "low" else "可做"
    return f"{prefix}{_format_strategy_label(strategy)}"


def _format_zone(value: Any) -> str | None:
    """Format JSON/string price zones for human-readable analysis sections."""
    if value in (None, "", []):
        return None
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value.strip() or None
    if isinstance(parsed, dict):
        parts = [
            f"{key}:{_format_scalar(val)}"
            for key, val in parsed.items()
            if key not in {"basis", "source", "note", "timing", "time", "condition", "entry_timing"}
            and val not in (None, "")
        ]
        return ", ".join(parts) or None
    if isinstance(parsed, list):
        return ", ".join(str(item) for item in parsed if item not in (None, "")) or None
    return str(parsed).strip() or None


def _format_entry_timing(value: Any) -> str:
    """Return visible entry timing/condition for the recommendation line."""
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return _DEFAULT_ENTRY_TIMING
    if isinstance(parsed, dict):
        for key in ("timing", "entry_timing", "condition", "time"):
            text = _clean_text(parsed.get(key))
            if text:
                return text
    return _DEFAULT_ENTRY_TIMING


def _format_scalar(value: Any) -> str:
    """Format scalar values without noisy trailing decimals."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
