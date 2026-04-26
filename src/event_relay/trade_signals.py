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
                name=_clean_text(item.get("name")),
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
    text = text.upper().replace(".TW", "").replace(".TWO", "")
    return text if _TICKER_RE.match(text) else None


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


if __name__ == "__main__":
    raise SystemExit(main())
