"""Scheduled market-analysis pipeline orchestrator.

Resolves the slot (us_close / pre_tw_open / tw_close), pulls the recent event
window + snapshot rows, runs the multi-stage pipeline (digest → transmission
→ tw_mapping → dual_view → critic → synthesis), persists summary +
structured payload into ``t_market_analyses``, and emits prompt snapshots
under ``runtime/prompts/``. Per REQ-018: collectors write source facts;
this module reads them and writes analysis output, never the reverse.
"""

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

from event_relay.analysis_stages import (
    PIPELINE_VERSION,
    StageContext,
    StageResult,
)
from event_relay.analysis_stages import (
    stage1_digest,
    stage2_transmission,
    stage3_tw_mapping,
    stage4_synthesis,
    stage_critic,
    stage_dual_view,
)
from event_relay.analysis_stages.schemas import assert_evidence_ids_covered
from event_relay.config import load_settings
from event_relay.event_enrichment import (
    EventAnnotation,
    annotate as rule_annotate,
    derive_news_impact,
)
from event_relay.rag import (
    DEFAULT_CANDIDATE_LIMIT as RAG_DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_EMBEDDING_DIMENSIONS as RAG_DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL as RAG_DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MIN_SIMILARITY as RAG_DEFAULT_MIN_SIMILARITY,
    DEFAULT_RAG_K,
    rag_enabled_from_env,
    retrieve_similar_events,
)
from event_relay.service import MarketAnalysisRecord, MySqlEventStore
from event_relay.weekly_summary import _call_llm, _load_secret_from_dpapi_file, _openai_web_search_enabled


logger = logging.getLogger(__name__)
PROMPT_VERSION = "market-analysis-v1"
MULTI_STAGE_PIPELINE_VERSION = PIPELINE_VERSION
SLOTS = {
    "us_close": (5, 0),
    "pre_tw_open": (8, 0),
    "tw_close": (15, 30),
}


@dataclass(frozen=True)
class MarketAnalysisConfig:
    """封裝 Market Analysis Config 相關資料與行為。"""
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
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(description="Generate scheduled market analysis")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--slot", default="auto", choices=["auto", "us_close", "pre_tw_open", "tw_close"])
    parser.add_argument("--force", action="store_true", help="Bypass schedule gate and run immediately")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _load_text(path: str) -> str:
    """載入 load text 對應的資料或結果。"""
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def _resolve_market_anthropic_settings() -> tuple[str, str, str, str, str | None]:
    """解析並決定 resolve market anthropic settings 對應的資料或結果。"""
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
    """解析並決定 resolve market openai settings 對應的資料或結果。"""
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
    """載入 load config 對應的資料或結果。"""
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
    """解析並決定 resolve slot 對應的資料或結果。"""
    if config.slot != "auto":
        return config.slot
    # Weekend slot filtering:
    #   Saturday (weekday=5): US close is valid (Friday US markets closed), but TW pre-open
    #                         and TW close are irrelevant — skip them.
    #   Sunday   (weekday=6): No market analysis — weekly summary runs separately via
    #                         weekly_summary.py; skip all market-analysis slots.
    weekday = now_local.weekday()  # 0=Mon … 5=Sat, 6=Sun
    weekend_skip: set[str] = set()
    if weekday == 5:   # Saturday
        weekend_skip = {"pre_tw_open", "tw_close"}
    elif weekday == 6:  # Sunday
        return None  # nothing to analyse today
    for slot_name, (hour, minute) in SLOTS.items():
        if slot_name in weekend_skip:
            continue
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
    """建立 build prompts 對應的資料或結果。"""
    macro_skill = _load_text(config.skill_macro_path)
    line_skill = _load_text(config.skill_line_format_path)
    slot_instruction = {
        "us_close": "Focus on what the U.S. close implies for Taiwan's next session.",
        "pre_tw_open": "Focus on Taiwan pre-open positioning and what matters before 09:00.",
        "tw_close": (
            "Focus on Taiwan close review after 13:30 and next-session preparation. "
            "Use same-day market_context:tw_close and flow/disclosure events when present."
        ),
    }[slot]
    audience_instruction = (
        "The audience wants actionable Taiwan close review and next-session risk tracking."
        if slot == "tw_close"
        else "The audience wants actionable Taiwan pre-open context from U.S. market moves."
    )
    required_sections = (
        "1) 台股收盤復盤：指數、成交量、權值股與盤勢情緒\n"
        "2) 法人/期權/融資券：三大法人、期貨選擇權、融資券與籌碼風險\n"
        "3) 類股輪動：強弱族群、題材延續性與資金移轉\n"
        "4) 隔日觀察與風險：明日盤前關注、國際變數、關鍵價位或事件\n"
        if slot == "tw_close"
        else (
            "1) 美股收盤重點\n"
            "2) 對台股的可能影響\n"
            "3) 需要留意的族群或事件\n"
            "4) 風險與資料缺口\n"
        )
    )
    system_prompt = (
        "You are a Taiwan market strategist writing in Traditional Chinese.\n"
        "Use plain text only. Be concise, concrete, and avoid fabricating facts.\n"
        f"{audience_instruction}\n\n"
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
        f"{required_sections}"
        "Total length 220-700 Chinese characters.\n"
        f"Now local time: {now_local.strftime('%Y-%m-%d %H:%M %Z')}\n"
        "Recent events JSON includes news and stored-only market_context facts from t_relay_events.\n"
        "This local context is not exhaustive; use web search when available to verify missing/current facts.\n"
        f"Recent events JSON:\n{events_json}\n\n"
        f"Recent market snapshot JSON:\n{market_json}\n"
    )
    return system_prompt, user_prompt


def _normalize_text(text: str) -> str:
    """正規化 normalize text 對應的資料或結果。"""
    return "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()[:4500]


def _write_prompt_snapshots(system_prompt: str, user_prompt: str, slot: str) -> None:
    """寫入 write prompt snapshots 對應的資料或結果。"""
    out_dir = Path("runtime/prompts")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"market_analysis_{slot}_system_prompt.txt").write_text(system_prompt, encoding="utf-8")
    (out_dir / f"market_analysis_{slot}_user_prompt.txt").write_text(user_prompt, encoding="utf-8")


def _compact_event_raw_json(source: str, value: str | None) -> Any:
    """執行 compact event raw json 的主要流程。"""
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

    # market_context 原始 payload 可能很大，這裡只保留 stage 推理真正需要的骨幹欄位，
    # 避免每次分析都把整包官方資料重新塞回 prompt。
    compact: dict[str, Any] = {}
    for key in (
        "event_type",
        "dimension",
        "slot",
        "scheduled_time_local",
        "generated_at",
        "trade_date",
        "dataset",
        "dataset_title",
        "source_family",
        "series_id",
        "year",
        "period",
        "periodName",
        "value",
        "normalized_metrics",
        "point_count",
        "event_count",
        "sources",
        "source_counts",
    ):
        if key in parsed:
            compact[key] = parsed[key]

    point = parsed.get("point")
    if isinstance(point, dict):
        compact["point"] = {key: value for key, value in point.items() if key != "raw"}

    failures = parsed.get("failures")
    if isinstance(failures, list) and failures:
        compact["failures"] = failures[:10]

    events = parsed.get("events")
    if isinstance(events, list) and events:
        compact["events"] = events[:20]

    return compact or None


def _inline_annotation(event: Any) -> dict[str, Any]:
    """執行 inline annotation 的主要流程。"""
    inline = rule_annotate(
        source=event.source,
        title=event.title,
        summary=event.summary,
        raw_json=getattr(event, "raw_json", None),
    )
    return {
        "entities": [dict(entity) for entity in inline.entities],
        "category": inline.category,
        "importance": inline.importance,
        "sentiment": inline.sentiment,
        "annotator": inline.annotator,
        "annotator_version": inline.annotator_version,
        "annotated_at": None,
    }


def _impact_dict_from_annotation(event: Any, annotation: dict[str, Any]) -> dict[str, Any]:
    """REQ-020: derive trade-impact tags from the (already-resolved) annotation."""
    entities = tuple(
        {"kind": str(e.get("kind", "")), "value": str(e.get("value", ""))}
        for e in (annotation.get("entities") or [])
        if isinstance(e, dict)
    )
    ann_obj = EventAnnotation(
        entities=entities,
        category=str(annotation.get("category") or "other"),
        importance=float(annotation.get("importance") or 0.0),
        sentiment=str(annotation.get("sentiment") or "neutral"),
        annotator=str(annotation.get("annotator") or "rule"),
        annotator_version=str(annotation.get("annotator_version") or "rule-v1"),
    )
    impact = derive_news_impact(
        annotation=ann_obj,
        title=event.title,
        summary=event.summary,
        raw_json=getattr(event, "raw_json", None),
    )
    return impact.to_dict()


def _build_events_payload(store: MySqlEventStore, recent_events: list) -> list[dict[str, Any]]:
    """建立 build events payload 對應的資料或結果。"""
    annotation_index = store.fetch_event_annotations([event.row_id for event in recent_events])
    stored_count = 0
    inline_count = 0
    payload: list[dict[str, Any]] = []
    for event in recent_events:
        annotation = annotation_index.get(int(event.row_id))
        if annotation is None:
            # annotation 表是加速層，不是硬依賴；缺資料時即時用 rule-based 補，
            # 讓分析流程不會因 enrichment worker 沒跑而整條失效。
            annotation = _inline_annotation(event)
            inline_count += 1
        else:
            stored_count += 1
        payload.append(
            {
                "id": event.row_id,
                "source": event.source,
                "title": event.title,
                "url": event.url,
                "summary": event.summary,
                "published_at": event.published_at,
                "created_at": event.created_at,
                "raw": _compact_event_raw_json(event.source, getattr(event, "raw_json", None)),
                "annotation": annotation,
                "impact": _impact_dict_from_annotation(event, annotation),
            }
        )
    logger.info(
        "[annotations] attached stored=%d inline_rule=%d total=%d",
        stored_count,
        inline_count,
        len(payload),
    )
    return payload


def _pipeline_mode_from_env() -> str:
    """執行 pipeline mode from env 的主要流程。"""
    raw = (os.getenv("MARKET_ANALYSIS_PIPELINE") or "multi_stage").strip().lower()
    if raw not in {"legacy", "multi_stage", "auto"}:
        return "multi_stage"
    return raw


def _run_multi_stage_pipeline(
    *,
    config: MarketAnalysisConfig,
    slot: str,
    now_local: datetime,
    events_payload: list[dict[str, Any]],
    market_payload: list[dict[str, Any]],
    rag_examples: list[dict[str, Any]] | None = None,
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any]]:
    """Run the four-stage pipeline.

    Returns ``(summary_text, structured_json, telemetry)``. ``summary_text`` is
    None if any stage failed. ``structured_json`` is the stage4 schema-validated
    dict when available, else None (fallback to text-only or stage failure).
    ``telemetry`` always contains per-stage metadata so the caller can record
    which stage broke and fall back safely.
    """
    import time as _time

    ctx = StageContext(
        provider=config.provider,
        api_base=config.api_base,
        api_key=config.api_key or "",
        model=config.model,
        slot=slot,
        now_local=now_local,
    )
    snapshot_dir = Path("runtime/prompts")
    telemetry: dict[str, Any] = {
        "pipeline_version": MULTI_STAGE_PIPELINE_VERSION,
        "rag_examples_count": len(rag_examples or []),
        "stages": {},
    }

    pipeline_started = _time.perf_counter()
    logger.info(
        "[pipeline] start slot=%s provider=%s model=%s events=%d market_rows=%d",
        slot,
        config.provider,
        config.model,
        len(events_payload),
        len(market_payload),
    )

    # 多階段流程採「任何 stage 失敗就整體回退」策略，
    # 但每段 telemetry 仍保留下來，方便日後知道到底是在哪一層斷掉。
    stage1 = stage1_digest.run(
        context=ctx,
        events_payload=events_payload,
        market_payload=market_payload,
        snapshot_dir=snapshot_dir,
    )
    telemetry["stages"]["stage1"] = _stage_telemetry(stage1)
    if not stage1.ok():
        logger.error(
            "[pipeline] aborted at stage1 elapsed=%.2fs error=%s",
            _time.perf_counter() - pipeline_started,
            stage1.error,
        )
        return None, None, telemetry

    stage2 = stage2_transmission.run(
        context=ctx,
        stage1_output=stage1.output,
        retrieved_examples=rag_examples or [],
        snapshot_dir=snapshot_dir,
    )
    telemetry["stages"]["stage2"] = _stage_telemetry(stage2)
    if not stage2.ok():
        logger.error(
            "[pipeline] aborted at stage2 elapsed=%.2fs error=%s",
            _time.perf_counter() - pipeline_started,
            stage2.error,
        )
        return None, None, telemetry

    stage3 = stage3_tw_mapping.run(
        context=ctx,
        stage1_output=stage1.output,
        stage2_output=stage2.output,
        snapshot_dir=snapshot_dir,
    )
    telemetry["stages"]["stage3"] = _stage_telemetry(stage3)
    if not stage3.ok():
        logger.error(
            "[pipeline] aborted at stage3 elapsed=%.2fs error=%s",
            _time.perf_counter() - pipeline_started,
            stage3.error,
        )
        return None, None, telemetry

    missing_evidence = assert_evidence_ids_covered(stage3.output, stage1.output)
    if missing_evidence:
        telemetry["stages"]["stage3"]["missing_evidence_ids"] = missing_evidence[:20]
        logger.warning(
            "[pipeline] stage3 referenced %d evidence_id(s) not in stage1: %s",
            len(missing_evidence),
            missing_evidence[:10],
        )

    dual_view = stage_dual_view.run(
        context=ctx,
        stage1_output=stage1.output,
        stage2_output=stage2.output,
        stage3_output=stage3.output,
        snapshot_dir=snapshot_dir,
    )
    telemetry["stages"]["stage_dual_view"] = _stage_telemetry(dual_view)
    dual_view_output = dual_view.output if dual_view.ok() else None
    if not dual_view.ok():
        telemetry["dual_view_skipped"] = True
        logger.warning(
            "[pipeline] stage_dual_view skipped error=%s; stage4 will run without bull/bear input",
            dual_view.error,
        )

    critic_output: dict[str, Any] | None = None
    if dual_view_output is not None:
        critic = stage_critic.run(
            context=ctx,
            stage1_output=stage1.output,
            stage3_output=stage3.output,
            dual_view_output=dual_view_output,
            snapshot_dir=snapshot_dir,
        )
        telemetry["stages"]["stage_critic"] = _stage_telemetry(critic)
        if critic.ok():
            critic_output = critic.output
        else:
            telemetry["critic_skipped"] = True
            logger.warning("[pipeline] stage_critic skipped error=%s; stage4 proceeds without critic", critic.error)
    else:
        telemetry["critic_skipped"] = True
        logger.info("[pipeline] stage_critic skipped because dual_view was unavailable")

    macro_skill = _load_text(config.skill_macro_path)
    line_skill = _load_text(config.skill_line_format_path)
    stage4 = stage4_synthesis.run(
        context=ctx,
        stage1_output=stage1.output,
        stage2_output=stage2.output,
        stage3_output=stage3.output,
        macro_skill=macro_skill,
        line_skill=line_skill,
        snapshot_dir=snapshot_dir,
        dual_view_output=dual_view_output,
        critic_output=critic_output,
    )
    telemetry["stages"]["stage4"] = _stage_telemetry(stage4)
    if not stage4.ok():
        logger.error(
            "[pipeline] aborted at stage4 elapsed=%.2fs error=%s",
            _time.perf_counter() - pipeline_started,
            stage4.error,
        )
        return None, None, telemetry

    stage4_payload = stage4.output if isinstance(stage4.output, dict) else {"summary_text": stage4.output, "structured": None}
    summary_text = _normalize_text(stage4_payload.get("summary_text") or "")
    structured_payload = stage4_payload.get("structured") if isinstance(stage4_payload.get("structured"), dict) else None
    telemetry["bull_case"] = (dual_view_output or {}).get("bull_case") if dual_view_output else None
    telemetry["bear_case"] = (dual_view_output or {}).get("bear_case") if dual_view_output else None
    telemetry["critique"] = critic_output

    pipeline_elapsed = _time.perf_counter() - pipeline_started
    telemetry["elapsed_sec"] = round(pipeline_elapsed, 3)
    logger.info(
        "[pipeline] done slot=%s elapsed=%.2fs summary_chars=%d structured=%s",
        slot,
        pipeline_elapsed,
        len(summary_text or ""),
        structured_payload is not None,
    )

    return summary_text, structured_payload, telemetry


def _stage_telemetry(result: StageResult) -> dict[str, Any]:
    """執行 stage telemetry 的主要流程。"""
    payload: dict[str, Any] = {
        "model": result.model,
        "ok": result.ok(),
    }
    if result.error:
        payload["error"] = result.error[:500]
    if result.extras:
        payload.update(result.extras)
    return payload


def _retrieve_rag_examples(store: MySqlEventStore, events_payload: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """檢索 retrieve rag examples 對應的資料或結果。"""
    if not rag_enabled_from_env():
        return [], {"enabled": False, "examples_count": 0}

    embedding_model = (os.getenv("RAG_EMBEDDING_MODEL") or RAG_DEFAULT_EMBEDDING_MODEL).strip()
    try:
        examples = retrieve_similar_events(
            store,
            events_payload,
            k=max(1, int(os.getenv("MARKET_ANALYSIS_RAG_K", str(DEFAULT_RAG_K)))),
            min_similarity=float(os.getenv("MARKET_ANALYSIS_RAG_MIN_SIMILARITY", str(RAG_DEFAULT_MIN_SIMILARITY))),
            candidate_limit=max(
                1,
                int(os.getenv("MARKET_ANALYSIS_RAG_CANDIDATE_LIMIT", str(RAG_DEFAULT_CANDIDATE_LIMIT))),
            ),
            embedding_model=embedding_model,
            dimensions=max(
                16,
                int(os.getenv("RAG_EMBEDDING_DIMENSIONS", str(RAG_DEFAULT_EMBEDDING_DIMENSIONS))),
            ),
        )
        prompt_examples = [example.to_prompt_dict() for example in examples]
        return prompt_examples, {
            "enabled": True,
            "embedding_model": embedding_model,
            "examples_count": len(prompt_examples),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG retrieval failed; continuing without historical examples: %s", exc)
        return [], {
            "enabled": True,
            "embedding_model": embedding_model,
            "examples_count": 0,
            "error": str(exc)[:500],
        }


def run_once(config: MarketAnalysisConfig) -> dict[str, Any]:
    """執行單次任務流程並回傳結果。"""
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

    events_payload = _build_events_payload(store, recent_events)
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
    rag_examples, rag_telemetry = _retrieve_rag_examples(store, events_payload)

    pipeline_mode = _pipeline_mode_from_env()
    pipeline_telemetry: dict[str, Any] | None = None
    summary_text: str | None = None
    structured_payload: dict[str, Any] | None = None

    if pipeline_mode in ("multi_stage", "auto"):
        summary_text, structured_payload, pipeline_telemetry = _run_multi_stage_pipeline(
            config=config,
            slot=slot,
            now_local=now_local,
            events_payload=events_payload,
            market_payload=market_payload,
            rag_examples=rag_examples,
        )
        if summary_text is None:
            logger.warning(
                "Multi-stage pipeline failed; falling back to legacy single-call. telemetry=%s",
                pipeline_telemetry,
            )

    used_multi_stage = summary_text is not None

    if summary_text is None:
        # legacy path 是最後保底：就算多階段 schema / stage 其中一段爆掉，
        # 仍嘗試用舊式單次 prompt 產出可閱讀報告，避免排程整天空白。
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

    logger.info(
        "[MARKET_ANALYSIS_STORED_ONLY] slot=%s model=%s pipeline=%s",
        slot,
        config.model,
        "multi_stage" if used_multi_stage else "legacy",
    )
    logger.info("[MARKET_ANALYSIS_TEXT]\n%s", summary_text)

    raw_dimension = "daily_tw_close" if slot == "tw_close" else "daily_market_analysis"
    push_enabled = slot != "tw_close"
    record = MarketAnalysisRecord(
        analysis_date=now_local.date().isoformat(),
        analysis_slot=slot,
        scheduled_time_local=f"{SLOTS[slot][0]:02d}:{SLOTS[slot][1]:02d}",
        model=config.model,
        prompt_version=PROMPT_VERSION,
        summary_text=summary_text,
        events_used=len(events_payload),
        market_rows_used=len(market_payload),
        push_enabled=push_enabled,
        pushed=False,
        raw_json=json.dumps(
            {
                # raw_json 保留的是「這次分析如何產生」的審計資訊：
                # 用了哪些上下文來源、走哪種 pipeline、是否有 structured 結果。
                "dimension": raw_dimension,
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
                "rag": rag_telemetry,
                "pipeline_mode": "multi_stage" if used_multi_stage else "legacy",
                "pipeline_stages": pipeline_telemetry,
                "structured": structured_payload,
            },
            ensure_ascii=False,
        ),
        structured_json=(
            json.dumps(structured_payload, ensure_ascii=False)
            if structured_payload is not None
            else None
        ),
    )
    store.upsert_market_analysis(record)
    return {
        "ok": True,
        "slot": slot,
        "analysis_date": record.analysis_date,
        "events_used": record.events_used,
        "market_rows_used": record.market_rows_used,
        "rag_examples_used": len(rag_examples),
        "push_enabled": push_enabled,
        "pushed": 0,
        "model": config.model,
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
        logger.info("Market analysis result: %s", result)
        return 0
    except Exception as exc:
        logger.error("Market analysis failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
