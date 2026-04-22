from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

from event_relay.config import load_settings
from event_relay.service import MarketAnalysisRecord, MySqlEventStore
from event_relay.weekly_summary import _call_llm, _load_secret_from_dpapi_file, _openai_web_search_enabled


logger = logging.getLogger(__name__)
PROMPT_VERSION = "market-analysis-v1"
SLOTS = {
    "us_close": (5, 0),
    "pre_tw_open": (7, 30),
}


@dataclass(frozen=True)
class MarketAnalysisConfig:
    env_file: str
    model: str
    api_base: str
    api_key: str | None
    api_key_file: str
    skill_macro_path: str
    skill_line_format_path: str
    lookback_hours: int
    max_events: int
    max_market_rows: int
    window_minutes: int
    force: bool
    slot: str
    provider: str = "openai"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate twice-daily market analysis")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--slot", default="auto", choices=["auto", "us_close", "pre_tw_open"])
    parser.add_argument("--force", action="store_true", help="Bypass schedule gate and run immediately")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _load_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def _resolve_market_anthropic_settings() -> tuple[str, str, str, str, str | None]:
    api_key_file = (os.getenv("ANTHROPIC_API_KEY_FILE") or ".secrets/anthropic_api_key.dpapi").strip()
    direct_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    api_key = direct_key or (_load_secret_from_dpapi_file(api_key_file) or "")
    return (
        "anthropic",
        (os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip(),
        (os.getenv("ANTHROPIC_API_BASE") or "https://api.anthropic.com").strip(),
        api_key_file,
        api_key or None,
    )


def _resolve_market_openai_settings() -> tuple[str, str, str, str, str | None]:
    api_key_file = (
        os.getenv("MARKET_ANALYSIS_OPENAI_API_KEY_FILE")
        or os.getenv("WEEKLY_SUMMARY_OPENAI_API_KEY_FILE")
        or ".secrets/openai_api_key.dpapi"
    ).strip()
    direct_key = (
        os.getenv("MARKET_ANALYSIS_OPENAI_API_KEY")
        or os.getenv("WEEKLY_SUMMARY_OPENAI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()
    api_key = direct_key or (_load_secret_from_dpapi_file(api_key_file) or "")
    model = (os.getenv("MARKET_ANALYSIS_MODEL") or os.getenv("WEEKLY_SUMMARY_MODEL") or "gpt-5").strip()
    api_base = (
        os.getenv("MARKET_ANALYSIS_OPENAI_API_BASE")
        or os.getenv("WEEKLY_SUMMARY_OPENAI_API_BASE")
        or "https://api.openai.com/v1"
    ).strip()
    return "openai", model, api_base, api_key_file, api_key or None


def _load_config(args: argparse.Namespace) -> MarketAnalysisConfig:
    load_settings(args.env_file)
    provider_env = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    if provider_env == "anthropic":
        provider, model, api_base, api_key_file, api_key = _resolve_market_anthropic_settings()
    else:
        provider, model, api_base, api_key_file, api_key = _resolve_market_openai_settings()
    return MarketAnalysisConfig(
        env_file=args.env_file,
        model=model,
        api_base=api_base,
        api_key=api_key,
        api_key_file=api_key_file,
        skill_macro_path=(
            os.getenv("MARKET_ANALYSIS_MACRO_SKILL_PATH")
            or os.getenv("WEEKLY_SUMMARY_MACRO_SKILL_PATH")
            or "skills/macro-weekly-summary-skill/SKILLS.md"
        ).strip(),
        skill_line_format_path=(
            os.getenv("MARKET_ANALYSIS_LINE_SKILL_PATH")
            or os.getenv("WEEKLY_SUMMARY_LINE_SKILL_PATH")
            or "skills/line-brief-format-skill/line-weekly-brief.md"
        ).strip(),
        lookback_hours=max(6, int(os.getenv("MARKET_ANALYSIS_LOOKBACK_HOURS", "24"))),
        max_events=max(20, int(os.getenv("MARKET_ANALYSIS_MAX_EVENTS", "120"))),
        max_market_rows=max(2, int(os.getenv("MARKET_ANALYSIS_MAX_MARKET_ROWS", "24"))),
        window_minutes=max(5, int(os.getenv("MARKET_ANALYSIS_WINDOW_MINUTES", "25"))),
        force=bool(args.force),
        slot=args.slot,
        provider=provider,
    )


def _resolve_slot(config: MarketAnalysisConfig, now_local: datetime) -> str | None:
    if config.slot != "auto":
        return config.slot
    for slot_name, (hour, minute) in SLOTS.items():
        target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta = abs((now_local - target).total_seconds()) / 60.0
        if delta <= float(config.window_minutes):
            return slot_name
    return None


def _build_prompts(
    config: MarketAnalysisConfig,
    slot: str,
    now_local: datetime,
    events_json: str,
    market_json: str,
) -> tuple[str, str]:
    macro_skill = _load_text(config.skill_macro_path)
    line_skill = _load_text(config.skill_line_format_path)
    slot_instruction = {
        "us_close": "Focus on what the U.S. close implies for Taiwan's next session.",
        "pre_tw_open": "Focus on Taiwan pre-open positioning and what matters before 09:00.",
    }[slot]
    system_prompt = (
        "You are a Taiwan market morning strategist writing in Traditional Chinese.\n"
        "Use plain text only. Be concise, concrete, and avoid fabricating facts.\n"
        "The audience wants actionable Taiwan pre-open context from U.S. market moves.\n\n"
        "Evidence policy:\n"
        "- Treat t_relay_events, market_context rows, and t_market_index_snapshots as primary local evidence.\n"
        "- Do not treat absence from local events as proof that nothing happened.\n"
        "- If web search is available, verify latest policy, price, war, macro, and earnings facts before using them.\n"
        "- If web search is unavailable or evidence is insufficient, explicitly label the data gap and lower confidence.\n"
        "- Distinguish local-event facts, externally verified facts, and inference.\n\n"
        "[Macro Skill]\n"
        f"{macro_skill}\n\n"
        "[Mobile Chat Format Skill]\n"
        f"{line_skill}\n"
    )
    user_prompt = (
        f"Generate one {slot} market analysis in Traditional Chinese.\n"
        f"{slot_instruction}\n"
        "Required sections:\n"
        "1) 美股收盤重點\n"
        "2) 對台股的可能影響\n"
        "3) 需要留意的族群或事件\n"
        "4) 風險與資料缺口\n"
        "Total length 220-700 Chinese characters.\n"
        f"Now local time: {now_local.strftime('%Y-%m-%d %H:%M %Z')}\n"
        "Recent events JSON includes news and stored-only market_context facts from t_relay_events.\n"
        "This local context is not exhaustive; use web search when available to verify missing/current facts.\n"
        f"Recent events JSON:\n{events_json}\n\n"
        f"Recent market snapshot JSON:\n{market_json}\n"
    )
    return system_prompt, user_prompt


def _normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()[:4500]


def _write_prompt_snapshots(system_prompt: str, user_prompt: str, slot: str) -> None:
    out_dir = Path("runtime/prompts")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"market_analysis_{slot}_system_prompt.txt").write_text(system_prompt, encoding="utf-8")
    (out_dir / f"market_analysis_{slot}_user_prompt.txt").write_text(user_prompt, encoding="utf-8")


def _compact_event_raw_json(source: str, value: str | None) -> Any:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"raw_json_parse_error": True}
    if not str(source or "").startswith("market_context:"):
        return None
    if not isinstance(parsed, dict):
        return None

    compact: dict[str, Any] = {}
    for key in ("event_type", "dimension", "slot", "scheduled_time_local", "generated_at", "point_count"):
        if key in parsed:
            compact[key] = parsed[key]

    point = parsed.get("point")
    if isinstance(point, dict):
        compact["point"] = {key: value for key, value in point.items() if key != "raw"}

    failures = parsed.get("failures")
    if isinstance(failures, list) and failures:
        compact["failures"] = failures[:10]

    return compact or None


def run_once(config: MarketAnalysisConfig) -> dict[str, Any]:
    now_local = datetime.now().astimezone()
    slot = _resolve_slot(config, now_local)
    if slot is None and not config.force:
        logger.info("Market analysis skipped by schedule now=%s", now_local.isoformat())
        return {"ok": True, "skipped": "schedule"}
    if slot is None:
        slot = "pre_tw_open"

    if not config.api_key:
        raise RuntimeError(
            f"Missing {config.provider} API key. Checked env vars and file: {config.api_key_file}"
        )

    relay_settings = load_settings(config.env_file)
    if not relay_settings.mysql_enabled:
        raise RuntimeError("Market analysis requires RELAY_MYSQL_ENABLED=true")

    store = MySqlEventStore(relay_settings)
    store.initialize()
    recent_events = store.fetch_recent_summary_events(days=1, limit=config.max_events)
    recent_market_rows = store.fetch_recent_market_snapshots(hours=config.lookback_hours, limit=config.max_market_rows)

    events_payload = [
        {
            "id": event.row_id,
            "source": event.source,
            "title": event.title,
            "url": event.url,
            "summary": event.summary,
            "published_at": event.published_at,
            "created_at": event.created_at,
            "raw": _compact_event_raw_json(event.source, getattr(event, "raw_json", None)),
        }
        for event in recent_events
    ]
    market_payload = [
        {
            "event_id": row.event_id,
            "source": row.source,
            "trade_date": row.trade_date,
            "session": row.market_session,
            "symbol": row.symbol,
            "label": row.label,
            "quote_url": row.quote_url,
            "open_price": row.open_price,
            "last_price": row.last_price,
            "recorded_price": row.recorded_price,
            "created_at": row.created_at,
        }
        for row in recent_market_rows
    ]

    system_prompt, user_prompt = _build_prompts(
        config=config,
        slot=slot,
        now_local=now_local,
        events_json=json.dumps(events_payload, ensure_ascii=False),
        market_json=json.dumps(market_payload, ensure_ascii=False),
    )
    _write_prompt_snapshots(system_prompt, user_prompt, slot)
    summary_text = _normalize_text(
        _call_llm(
            provider=config.provider,
            api_base=config.api_base,
            api_key=config.api_key,
            model=config.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    )

    logger.info("[MARKET_ANALYSIS_STORED_ONLY] slot=%s model=%s", slot, config.model)
    logger.info("[MARKET_ANALYSIS_TEXT]\n%s", summary_text)

    record = MarketAnalysisRecord(
        analysis_date=now_local.date().isoformat(),
        analysis_slot=slot,
        scheduled_time_local=f"{SLOTS[slot][0]:02d}:{SLOTS[slot][1]:02d}",
        model=config.model,
        prompt_version=PROMPT_VERSION,
        summary_text=summary_text,
        events_used=len(events_payload),
        market_rows_used=len(market_payload),
        push_enabled=True,
        pushed=False,
        raw_json=json.dumps(
            {
                "slot": slot,
                "generated_at": now_local.isoformat(),
                "events_used": len(events_payload),
                "market_rows_used": len(market_payload),
                "event_context_sources": sorted(
                    {
                        str(event.get("source"))
                        for event in events_payload
                        if str(event.get("source") or "").startswith("market_context:")
                    }
                ),
                "direct_push_disabled": True,
                "delivery_owner": "java",
                "python_push_removed": True,
                "web_search_requested": config.provider == "openai" and _openai_web_search_enabled(),
            },
            ensure_ascii=False,
        ),
    )
    store.upsert_market_analysis(record)
    return {
        "ok": True,
        "slot": slot,
        "analysis_date": record.analysis_date,
        "events_used": record.events_used,
        "market_rows_used": record.market_rows_used,
        "push_enabled": True,
        "pushed": 0,
        "model": config.model,
    }


def main() -> int:
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
        logger.info("Market analysis result: %s", result)
        return 0
    except Exception as exc:
        logger.error("Market analysis failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
