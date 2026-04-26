from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
import re
import sys
from typing import Any

from event_relay.config import load_settings
from event_relay.service import MySqlEventStore, RelayEvent, SummaryEvent


logger = logging.getLogger(__name__)

PROMPT_VERSION = "tw-close-context-v1"
DEFAULT_SLOT = "tw_close"
DEFAULT_SCHEDULED_TIME = "15:20"
DEFAULT_LOOKBACK_DAYS = 2
DEFAULT_MAX_EVENTS = 200
DEFAULT_SOURCE_PREFIXES = (
    "market_context:twse_flow",
    "market_context:tpex_flow",
    "market_context:taifex_flow",
    "market_context:twse_openapi",
    "market_context:twse_mops",
    "twse_mops:",
)


@dataclass(frozen=True)
class TwCloseContextConfig:
    """封裝 Tw Close Context Config 相關資料與行為。"""
    env_file: str
    slot: str
    scheduled_time_local: str
    trade_date: str | None
    lookback_days: int
    max_events: int
    source_prefixes: tuple[str, ...]


def _build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(
        description="Build Taiwan close context from existing t_relay_events facts"
    )
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--slot", default=DEFAULT_SLOT, help="Context slot label")
    parser.add_argument("--scheduled-time", default=DEFAULT_SCHEDULED_TIME, help="Local schedule label")
    parser.add_argument("--trade-date", default="", help="Override trade date as YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS)
    parser.add_argument("--source-prefixes", default="", help="Comma-separated source prefixes")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _load_config(args: argparse.Namespace) -> TwCloseContextConfig:
    """載入 load config 對應的資料或結果。"""
    load_settings(args.env_file)
    env_prefixes = os.getenv("TW_CLOSE_CONTEXT_SOURCE_PREFIXES") or ""
    prefixes_text = args.source_prefixes or env_prefixes
    prefixes = tuple(
        prefix.strip()
        for prefix in (prefixes_text.split(",") if prefixes_text else DEFAULT_SOURCE_PREFIXES)
        if prefix.strip()
    )
    return TwCloseContextConfig(
        env_file=args.env_file,
        slot=(os.getenv("TW_CLOSE_CONTEXT_SLOT") or args.slot).strip() or DEFAULT_SLOT,
        scheduled_time_local=(
            os.getenv("TW_CLOSE_CONTEXT_SCHEDULED_TIME") or args.scheduled_time
        ).strip()
        or DEFAULT_SCHEDULED_TIME,
        trade_date=(args.trade_date or os.getenv("TW_CLOSE_CONTEXT_TRADE_DATE") or "").strip() or None,
        lookback_days=max(1, int(os.getenv("TW_CLOSE_CONTEXT_LOOKBACK_DAYS") or args.lookback_days)),
        max_events=max(1, int(os.getenv("TW_CLOSE_CONTEXT_MAX_EVENTS") or args.max_events)),
        source_prefixes=prefixes or DEFAULT_SOURCE_PREFIXES,
    )


def _resolve_trade_date(config: TwCloseContextConfig, now_local: datetime) -> str:
    """解析並決定 resolve trade date 對應的資料或結果。"""
    if config.trade_date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", config.trade_date):
            raise ValueError("trade_date must use YYYY-MM-DD")
        return config.trade_date
    return now_local.date().isoformat()


def _parse_raw_json(value: str | None) -> dict[str, Any]:
    """解析 parse raw json 對應的資料或結果。"""
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"raw_json_parse_error": True}
    return parsed if isinstance(parsed, dict) else {}


def _date_from_text(value: str | None) -> str | None:
    """執行 date from text 的主要流程。"""
    text = str(value or "").strip()
    match = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else None


def _event_trade_date(event: SummaryEvent, raw: dict[str, Any]) -> str | None:
    """執行 event trade date 的主要流程。"""
    raw_trade_date = raw.get("trade_date")
    if raw_trade_date:
        return _date_from_text(str(raw_trade_date))
    return _date_from_text(event.published_at) or _date_from_text(event.created_at)


def _source_matches(source: str, prefixes: tuple[str, ...]) -> bool:
    """執行 source matches 的主要流程。"""
    normalized = source.strip().lower()
    return any(normalized.startswith(prefix.strip().lower()) for prefix in prefixes)


def filter_tw_close_source_events(
    events: list[SummaryEvent],
    trade_date: str,
    source_prefixes: tuple[str, ...] = DEFAULT_SOURCE_PREFIXES,
) -> list[SummaryEvent]:
    """執行 filter tw close source events 的主要流程。"""
    selected: list[SummaryEvent] = []
    for event in events:
        if not _source_matches(event.source, source_prefixes):
            continue
        raw = _parse_raw_json(event.raw_json)
        if _event_trade_date(event, raw) == trade_date:
            selected.append(event)
    return selected


def _compact_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """執行 compact raw 的主要流程。"""
    keep_keys = (
        "stored_only",
        "event_type",
        "dimension",
        "slot",
        "trade_date",
        "market",
        "dataset",
        "scheduled_time_local",
        "generated_at",
        "point_count",
        "row_count",
        "record_count",
        "dataset",
        "dataset_title",
        "source_family",
        "series_id",
        "year",
        "period",
        "periodName",
        "value",
        "normalized_metrics",
        "source_counts",
        "stats",
        "totals",
        "flow",
        "flows",
        "failures",
    )
    compact = {key: raw[key] for key in keep_keys if key in raw}
    point = raw.get("point")
    if isinstance(point, dict):
        compact["point"] = {key: value for key, value in point.items() if key != "raw"}
    return compact


def _compact_event(event: SummaryEvent) -> dict[str, Any]:
    """執行 compact event 的主要流程。"""
    raw = _parse_raw_json(event.raw_json)
    compact: dict[str, Any] = {
        "id": event.row_id,
        "source": event.source,
        "title": event.title,
        "summary": event.summary[:700],
        "published_at": event.published_at,
        "created_at": event.created_at,
    }
    raw_compact = _compact_raw(raw)
    if raw_compact:
        compact["raw"] = raw_compact
    return compact


def _source_counts(events: list[SummaryEvent]) -> dict[str, int]:
    """執行 source counts 的主要流程。"""
    counts: dict[str, int] = {}
    for event in events:
        counts[event.source] = counts.get(event.source, 0) + 1
    return dict(sorted(counts.items()))


def build_summary(events: list[SummaryEvent], trade_date: str) -> str:
    """建立 build summary 對應的資料或結果。"""
    if not events:
        return f"Taiwan close context for {trade_date}: no same-day flow/disclosure events found."
    counts = _source_counts(events)
    source_text = ", ".join(f"{source}={count}" for source, count in counts.items())
    title_text = " | ".join(event.title for event in events[:5] if event.title)
    if len(title_text) > 900:
        title_text = f"{title_text[:897]}..."
    return (
        f"Taiwan close context for {trade_date}: {len(events)} relay events aggregated. "
        f"Sources: {source_text}. Highlights: {title_text}"
    )[:4500]


def _stable_event_id(slot: str, trade_date: str) -> str:
    """執行 stable event id 的主要流程。"""
    safe_slot = re.sub(r"[^a-z0-9_-]+", "-", slot.lower()).strip("-") or DEFAULT_SLOT
    return f"market-context-{safe_slot}-{trade_date}"


def build_tw_close_context_event(
    source_events: list[SummaryEvent],
    config: TwCloseContextConfig,
    now_local: datetime,
) -> RelayEvent:
    """建立 build tw close context event 對應的資料或結果。"""
    trade_date = _resolve_trade_date(config, now_local)
    generated_at = now_local.isoformat()
    source_counts = _source_counts(source_events)
    return RelayEvent(
        event_id=_stable_event_id(config.slot, trade_date),
        source="market_context:tw_close",
        title=f"Taiwan close context collected {trade_date}",
        url=f"internal://market_context/{config.slot}/{trade_date}",
        summary=build_summary(source_events, trade_date),
        published_at=generated_at,
        log_only=False,
        raw={
            "stored_only": True,
            "event_type": "market_context_collection",
            "dimension": "market_context",
            "slot": config.slot,
            "trade_date": trade_date,
            "scheduled_time_local": config.scheduled_time_local,
            "generated_at": generated_at,
            "prompt_version": PROMPT_VERSION,
            "event_count": len(source_events),
            "sources": sorted(source_counts),
            "source_counts": source_counts,
            "source_prefixes": list(config.source_prefixes),
            "events": [_compact_event(event) for event in source_events],
        },
    )


def run_once(config: TwCloseContextConfig) -> dict[str, Any]:
    """執行單次任務流程並回傳結果。"""
    relay_settings = load_settings(config.env_file)
    if not relay_settings.mysql_enabled:
        raise RuntimeError("Taiwan close context requires RELAY_MYSQL_ENABLED=true")

    now_local = datetime.now().astimezone()
    trade_date = _resolve_trade_date(config, now_local)
    store = MySqlEventStore(relay_settings)
    store.initialize()
    recent_events = store.fetch_recent_summary_events(days=config.lookback_days, limit=config.max_events)
    source_events = filter_tw_close_source_events(
        recent_events,
        trade_date=trade_date,
        source_prefixes=config.source_prefixes,
    )
    context_event = build_tw_close_context_event(source_events, config, now_local)
    stored = store.enqueue_event_if_new(context_event)
    logger.info(
        "Taiwan close context stored: trade_date=%s slot=%s events_used=%d stored=%s",
        trade_date,
        config.slot,
        len(source_events),
        stored,
    )
    return {
        "ok": True,
        "trade_date": trade_date,
        "slot": config.slot,
        "events_used": len(source_events),
        "stored": 1 if stored else 0,
        "duplicates": 0 if stored else 1,
        "event_id": context_event.event_id,
        "source": context_event.source,
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
        logger.info("Taiwan close context result: %s", result)
        return 0
    except Exception as exc:
        logger.error("Taiwan close context failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
