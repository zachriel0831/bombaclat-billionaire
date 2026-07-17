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
from dataclasses import dataclass, replace
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
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
    stage0_thesis_selector,
    stage4_synthesis,
    stage_critic,
    stage_dual_view,
)
from event_relay.claim_verifier import verify_claim_coverage
from event_relay.analysis_stages.schemas import assert_evidence_ids_covered
from event_relay.config import load_settings
from event_relay.context_pack_builder import CONTEXT_PACK_VERSION, build_context_pack
from event_relay.event_enrichment import (
    EventAnnotation,
    annotate as rule_annotate,
    derive_news_impact,
)
from event_relay.market_calendar import (
    MarketCalendarState,
    allowed_analysis_slots,
    resolve_market_calendar_state,
)
from event_relay.llm_quota_router import (
    LlmRouteCandidate,
    router_enabled_from_env,
    select_market_analysis_model,
)
from event_relay.prompt_assets import PROMPT_ASSETS_VERSION
from event_relay.rag import (
    DEFAULT_CANDIDATE_LIMIT as RAG_DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_EMBEDDING_DIMENSIONS as RAG_DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL as RAG_DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MIN_SIMILARITY as RAG_DEFAULT_MIN_SIMILARITY,
    DEFAULT_RAG_K,
    rag_enabled_from_env,
    retrieve_similar_events,
)
from event_relay.service import MarketAnalysisRecord, MySqlEventStore, TradeSignalRecord
from event_relay.trade_signals import (
    FIXED_MARKET_ANALYSIS_WATCH_POOL,
    build_prior_signal_reference_trade_signals,
    build_trade_signal_recommendation_section,
    build_quote_event_trade_signals,
    build_trade_signals_from_analysis,
    is_excluded_trade_signal_ticker,
    is_fixed_market_analysis_watch_ticker,
)
from event_relay.weekly_summary import _call_llm, _load_secret_from_dpapi_file, _openai_web_search_enabled


logger = logging.getLogger(__name__)
PROMPT_VERSION = "market-analysis-v1"
MULTI_STAGE_PIPELINE_VERSION = PIPELINE_VERSION
PROVIDER_CONTEXT_POLICY_VERSION = "provider-context-policy-v1"
TRUST_GATE_VERSION = "market-analysis-trust-gate-v1"
SLOTS = {
    "us_close": (5, 0),
    "pre_tw_open": (7, 30),
    "macro_daily": (8, 5),
    "tw_close": (15, 30),
}

MACRO_DAILY_OWNER_SLOT = "pre_tw_open"
FIXED_POOL_SIGNAL_SLOTS = {"pre_tw_open", "us_close"}
VISIBLE_RECOMMENDATION_SECTION_SLOTS: set[str] = set()


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
    context_pack_enabled: bool = True
    context_pack_candidate_limit: int = 0
    model_router: dict[str, Any] | None = None


@dataclass(frozen=True)
class SlotDecision:
    """Resolved analysis slot plus calendar routing metadata."""

    slot: str | None
    requested_slot: str | None
    skipped_reason: str | None
    calendar_state: MarketCalendarState

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "requested_slot": self.requested_slot,
            "skipped_reason": self.skipped_reason,
            "calendar": self.calendar_state.to_dict(),
        }


@dataclass(frozen=True)
class AnalysisGenerationResult:
    """One completed analysis generation attempt."""

    config: MarketAnalysisConfig
    requested_pipeline_mode: str
    pipeline_mode: str
    events_payload: list[dict[str, Any]]
    market_payload: list[dict[str, Any]]
    rag_examples: list[dict[str, Any]]
    provider_context_policy: dict[str, Any]
    summary_text: str
    structured_payload: dict[str, Any] | None
    pipeline_telemetry: dict[str, Any] | None
    legacy_token_usage: dict[str, Any] | None
    used_multi_stage: bool


def _build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(description="Generate scheduled market analysis")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument(
        "--slot",
        default="auto",
        choices=["auto", "us_close", "pre_tw_open", "tw_close", "macro_daily"],
    )
    parser.add_argument("--force", action="store_true", help="Bypass time-window gate, not market-calendar guard")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _load_text(path: str) -> str:
    """載入 load text 對應的資料或結果。"""
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def _env_bool(name: str, default: bool) -> bool:
    """Read a bool env var with permissive true/false handling."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


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


def _env_csv(name: str) -> list[str]:
    """Read comma-separated env values, preserving order."""
    raw = os.getenv(name) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _candidate_variants(
    *,
    provider: str,
    model: str,
    api_base: str,
    api_key_file: str,
    api_key: str | None,
    model_env_names: tuple[str, ...],
) -> list[LlmRouteCandidate]:
    """Build provider candidates from configured primary and fallback models."""
    models: list[str] = []
    for name in model_env_names:
        models.extend(_env_csv(name))
    if not models:
        models = [model]
    elif model not in models:
        models.insert(0, model)

    seen: set[str] = set()
    result: list[LlmRouteCandidate] = []
    for item in models:
        if item in seen:
            continue
        seen.add(item)
        result.append(
            LlmRouteCandidate(
                provider=provider,
                model=item,
                api_base=api_base,
                api_key_file=api_key_file,
                api_key=api_key,
            )
        )
    return result


def _primary_provider_for_market_analysis(provider_env: str) -> str:
    """Resolve the market-analysis primary provider before quota routing."""
    if not router_enabled_from_env():
        return provider_env
    raw_primary = (os.getenv("MARKET_ANALYSIS_PRIMARY_PROVIDER") or "").strip()
    if raw_primary:
        return raw_primary.lower()
    provider_order = _env_csv("MARKET_ANALYSIS_PROVIDER_ORDER")
    if provider_order:
        return provider_order[0].lower()
    normalized = (provider_env or "").strip().lower()
    if normalized in {"anthropic", "claude"}:
        return "anthropic"
    return "openai"


def _load_config(args: argparse.Namespace) -> MarketAnalysisConfig:
    """載入 load config 對應的資料或結果。"""
    load_settings(args.env_file)
    provider_env = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    openai_provider, openai_model, openai_api_base, openai_key_file, openai_api_key = _resolve_market_openai_settings()
    anthropic_provider, anthropic_model, anthropic_api_base, anthropic_key_file, anthropic_api_key = (
        _resolve_market_anthropic_settings()
    )
    primary_provider = _primary_provider_for_market_analysis(provider_env)
    if primary_provider == "anthropic":
        provider, model, api_base, api_key_file, api_key = (
            anthropic_provider,
            anthropic_model,
            anthropic_api_base,
            anthropic_key_file,
            anthropic_api_key,
        )
    else:
        provider, model, api_base, api_key_file, api_key = (
            openai_provider,
            openai_model,
            openai_api_base,
            openai_key_file,
            openai_api_key,
        )

    openai_candidates = _candidate_variants(
        provider=openai_provider,
        model=openai_model,
        api_base=openai_api_base,
        api_key_file=openai_key_file,
        api_key=openai_api_key,
        model_env_names=("MARKET_ANALYSIS_OPENAI_MODELS",),
    )
    anthropic_candidates = _candidate_variants(
        provider=anthropic_provider,
        model=anthropic_model,
        api_base=anthropic_api_base,
        api_key_file=anthropic_key_file,
        api_key=anthropic_api_key,
        model_env_names=("MARKET_ANALYSIS_ANTHROPIC_MODELS", "ANTHROPIC_MODELS"),
    )
    preferred_candidates = anthropic_candidates if primary_provider == "anthropic" else openai_candidates
    alternative_candidates = (
        [*openai_candidates, *anthropic_candidates]
        if primary_provider == "anthropic"
        else [*anthropic_candidates, *openai_candidates]
    )
    route = select_market_analysis_model(
        preferred=preferred_candidates[0],
        alternatives=alternative_candidates,
    )
    selected = route.selected
    provider, model, api_base, api_key_file, api_key = (
        selected.provider,
        selected.model,
        selected.api_base,
        selected.api_key_file,
        selected.api_key,
    )
    if route.enabled:
        logger.info(
            "Market analysis model router selected provider=%s model=%s fallback=%s",
            provider,
            model,
            route.fallback_reason,
        )
    max_events = max(20, int(os.getenv("MARKET_ANALYSIS_MAX_EVENTS", "120")))
    context_pack_candidate_limit = max(
        max_events,
        int(os.getenv("MARKET_ANALYSIS_CONTEXT_PACK_CANDIDATE_LIMIT", str(max_events * 3))),
    )
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
        max_events=max_events,
        max_market_rows=max(2, int(os.getenv("MARKET_ANALYSIS_MAX_MARKET_ROWS", "24"))),
        window_minutes=max(5, int(os.getenv("MARKET_ANALYSIS_WINDOW_MINUTES", "25"))),
        force=bool(args.force),
        slot=args.slot,
        provider=provider,
        context_pack_enabled=_env_bool("MARKET_ANALYSIS_CONTEXT_PACK_ENABLED", True),
        context_pack_candidate_limit=context_pack_candidate_limit,
        model_router=route.to_dict(),
    )


def _preferred_tw_fallback_tickers_from_env() -> set[str]:
    """Return tickers explicitly configured as Taiwan tracked-stock fallback."""
    result: set[str] = set()
    for raw in str(os.getenv("MARKET_CONTEXT_TW_YAHOO_SYMBOLS") or "").split(","):
        entry = raw.strip()
        if not entry:
            continue
        symbol = entry
        for separator in (":", "|", "="):
            if separator in symbol:
                symbol = symbol.split(separator, 1)[0]
                break
        code = symbol.strip().upper().split(".", 1)[0]
        if code.isdigit():
            result.add(code)
    return result


def _should_emit_recommendation_section(slot: str, *, pipeline_mode: str | None = None) -> bool:
    """Return whether stored signals should be appended to the report text."""
    if slot == "us_close" and pipeline_mode == "digest":
        return False
    return slot in VISIBLE_RECOMMENDATION_SECTION_SLOTS


def _should_build_fixed_pool_signals(slot: str, *, pipeline_mode: str | None = None) -> bool:
    """Return whether internal fixed-pool signals should still be maintained."""
    if slot == "us_close" and pipeline_mode == "digest":
        return False
    return slot in FIXED_POOL_SIGNAL_SLOTS


def _allowed_claim_tickers_for_slot(slot: str, *, pipeline_mode: str | None = None) -> set[str]:
    """Return structured tickers allowed by the fixed market-analysis contract."""
    if not _should_build_fixed_pool_signals(slot, pipeline_mode=pipeline_mode):
        return set()
    return set(FIXED_MARKET_ANALYSIS_WATCH_POOL)


def _merge_reference_levels_from_fallbacks(
    signals: list[TradeSignalRecord],
    fallback_signals: list[TradeSignalRecord],
) -> tuple[list[TradeSignalRecord], int]:
    """Fill missing price-reference levels on structured signals.

    LLM stock_watch rows often name the right ticker but leave entry/exit
    fields null. Quote/context fallback rows are deterministic reference
    levels from recent Taiwan prices, so copy only missing fields from the
    matching ticker while preserving the model's thesis and signal type.
    """
    fallback_by_ticker = {signal.ticker: signal for signal in fallback_signals}
    merged: list[TradeSignalRecord] = []
    filled = 0
    for signal in signals:
        fallback = fallback_by_ticker.get(signal.ticker)
        if fallback is None:
            merged.append(signal)
            continue

        updates: dict[str, Any] = {}
        if not signal.entry_zone_json and fallback.entry_zone_json:
            updates["entry_zone_json"] = fallback.entry_zone_json
        if not signal.invalidation_json and fallback.invalidation_json:
            updates["invalidation_json"] = fallback.invalidation_json
        if not signal.take_profit_zone_json and fallback.take_profit_zone_json:
            updates["take_profit_zone_json"] = fallback.take_profit_zone_json
        if not signal.holding_horizon and fallback.holding_horizon:
            updates["holding_horizon"] = fallback.holding_horizon
        if not signal.confidence and fallback.confidence:
            updates["confidence"] = fallback.confidence

        if updates:
            filled += 1
            merged.append(replace(signal, **updates))
        else:
            merged.append(signal)
    return merged, filled


def _resolve_time_slot_legacy_unused(config: MarketAnalysisConfig, now_local: datetime) -> str | None:
    """Old weekend-only resolver kept inert by the refreshed calendar resolver below."""
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


def _resolve_time_slot(config: MarketAnalysisConfig, now_local: datetime) -> str | None:
    """Resolve the requested slot from CLI args or the local schedule window."""
    if config.slot != "auto":
        return config.slot
    for slot_name, (hour, minute) in SLOTS.items():
        if slot_name == "macro_daily":
            continue
        target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta = abs((now_local - target).total_seconds()) / 60.0
        if delta <= float(config.window_minutes):
            return slot_name
    if config.force:
        return "pre_tw_open"
    return None


def _resolve_slot_decision(config: MarketAnalysisConfig, now_local: datetime) -> SlotDecision:
    """Apply schedule and TW / US holiday routing before any LLM call."""
    calendar_state = resolve_market_calendar_state(now_local)
    requested_slot = _resolve_time_slot(config, now_local)
    if requested_slot is None:
        return SlotDecision(None, None, "schedule", calendar_state)

    allowed = allowed_analysis_slots(calendar_state)
    # 中文：週日完全交給 weekly_summary，不讓 daily market-analysis 呼叫 LLM。
    if not allowed:
        return SlotDecision(None, requested_slot, "weekly_summary_only", calendar_state)

    if requested_slot in allowed:
        return SlotDecision(requested_slot, requested_slot, None, calendar_state)

    # 中文：TW/US 都休市時，只讓早盤任務轉成 macro_daily，避免 us_close / 台股分析混跑。
    if allowed == {"macro_daily"} and requested_slot == MACRO_DAILY_OWNER_SLOT:
        return SlotDecision("macro_daily", requested_slot, None, calendar_state)

    if requested_slot == "macro_daily":
        return SlotDecision(None, requested_slot, "macro_daily_not_required", calendar_state)

    return SlotDecision(None, requested_slot, "market_calendar", calendar_state)


def _resolve_slot(config: MarketAnalysisConfig, now_local: datetime) -> str | None:
    """Compatibility wrapper for tests and older callers."""
    return _resolve_slot_decision(config, now_local).slot


def _build_prompts(
    config: MarketAnalysisConfig,
    slot: str,
    now_local: datetime,
    events_json: str,
    market_json: str,
    upstream_analysis_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """建立 build prompts 對應的資料或結果。"""
    macro_skill = _load_text(config.skill_macro_path)
    line_skill = _load_text(config.skill_line_format_path)
    slot_instruction = {
        "us_close": "Focus on what the U.S. close implies for Taiwan's next session.",
        "pre_tw_open": "Focus on Taiwan pre-open positioning and what matters before 09:00.",
        "macro_daily": (
            "Focus on macro-only world context because both Taiwan and the relevant U.S. close session are closed."
        ),
        "tw_close": (
            "Focus on Taiwan close review after 13:30 and next-session preparation. "
            "Use same-day market_context:tw_close and flow/disclosure events when present."
        ),
    }[slot]
    audience_instruction = (
        "The audience wants actionable Taiwan close review and next-session risk tracking."
        if slot == "tw_close"
        else "The audience wants macro context only; avoid stock entry recommendations."
        if slot == "macro_daily"
        else "The audience wants actionable Taiwan pre-open context from U.S. market moves."
    )
    required_sections = _regime_flow_sections()
    section_guide = _regime_flow_guide()

    has_us_close_context = bool(
        slot == "pre_tw_open"
        and upstream_analysis_context
        and upstream_analysis_context.get("included")
    )
    upstream_instruction = (
        "For pre_tw_open, source=market_analysis:us_close is present; fold its key points into sections 1-2.\n"
        if has_us_close_context
        else "For pre_tw_open, do not infer U.S. close facts when the relevant U.S. session was closed or absent.\n"
        if slot == "pre_tw_open"
        else ""
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
        "- Distinguish local-event facts, externally verified facts, and inference.\n"
        "- Visible prose must translate internal source labels and numeric handles into plain Chinese implications; do not show labels such as market scorecard, market_context, t_relay_events, t_market_analyses, t_market_index_snapshots, analysis_slot, scheduled_time_local, raw_json, structured_json, claim_verifier, Codex guard, LLM API, or 07:20 market_context.\n\n"
        "[Macro Skill]\n"
        f"{macro_skill}\n\n"
        "[Mobile Chat Format Skill]\n"
        f"{line_skill}\n"
    )
    user_prompt = (
        f"Generate one {slot} market analysis in Traditional Chinese.\n"
        f"{slot_instruction}\n"
        "Do not include a bracketed title like [Market Analysis]; downstream title should be date-only.\n"
        "Required sections:\n"
        f"{required_sections}"
        f"{section_guide}"
        "Formatting rules:\n"
        "- Do not include internal event IDs, source row IDs, or citation-only numeric lists such as （128610,128539） in summary_text.\n"
        "- Do not expose internal pipeline labels, table names, API/guard implementation notes, or custom numeric handles such as market scorecard, market_context, t_relay_events, t_market_analyses, t_market_index_snapshots, 07:20 market_context, analysis_slot, scheduled_time_local, raw_json, structured_json, claim_verifier, Codex guard, or LLM API; translate them into plain Chinese market implications.\n"
        "- Keep evidence references implicit in raw_json/pipeline telemetry, not visible report text.\n"
        "- Section 1 今日主命題 should be one sentence, not a paragraph.\n"
        "- Section 2 三個證據 must contain exactly three bullets and each bullet must include the source fact and why it matters.\n"
        "- Section 3 市場正在定價什麼 should state what expectations are already in prices and what is not fully priced yet.\n"
        "- Section 4 台股傳導 should translate the thesis into Taiwan index, sector, and mega-cap transmission; it is not a stock-picking list.\n"
        "- Section 5 反證條件 should name the cleanest conditions that would break the thesis.\n"
        "- Section 6 風險與資料缺口 must be concise: three bullets maximum.\n"
        "- Do not include a dedicated 台股配置 section or any ## 今日個股觀察 section in daily reports.\n"
        "- Individual companies may appear only as mega-cap transmission examples, e.g. NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭; avoid entry, stop-loss, or target-price language.\n"
        "- Use the exact section titles listed above.\n"
        f"{_summary_length_instruction(slot)}\n"
        f"Now local time: {now_local.strftime('%Y-%m-%d %H:%M %Z')}\n"
        "Recent events JSON includes local news and stored-only market facts.\n"
        "This local context is not exhaustive; use web search when available to verify missing/current facts.\n"
        "Retail usefulness requirement: make the opening thesis, evidence, and pricing sections answer what Taiwan investors should watch today before moving into supporting detail.\n"
        "If evidence exists, explicitly cover Fed path, liquidity, credit stress, cycle data, and sentiment/positioning; "
        "keep data in bullets and keep paragraphs short.\n"
        f"{upstream_instruction}"
        f"Recent events JSON:\n{events_json}\n\n"
        f"Recent market snapshot JSON:\n{market_json}\n"
    )
    return system_prompt, user_prompt


def _build_us_close_digest_prompts(
    *,
    slot: str,
    now_local: datetime,
    events_json: str,
    market_json: str,
) -> tuple[str, str]:
    """Build a compact U.S. close digest prompt used as pre-open input."""
    system_prompt = (
        "You are a Taiwan market strategist writing a compact U.S. close digest in Traditional Chinese.\n"
        "This is an upstream input for the Taiwan pre-open trade brief, not the final trading recommendation.\n"
        "Use only evidence from the supplied local context unless you explicitly mark a data gap.\n"
        "Be concise, causal, and avoid stock entry recommendations.\n"
    )
    user_prompt = (
        f"Generate one compact {slot} digest in Traditional Chinese.\n"
        "Purpose: summarize the U.S. close so the later Taiwan pre-open analysis can decide sector tilt and fixed-pool stock setups.\n"
        "Do NOT recommend Taiwan stocks, do NOT provide entry/stop/take-profit levels, and do NOT write a full research report.\n"
        "Required sections:\n"
        "1) 美股收盤一句話\n"
        "2) 主要傳導因子\n"
        "3) 台股早盤要檢查的族群\n"
        "4) 資料缺口與反向風險\n"
        "Length: 350-750 Chinese characters. Use bullets for market facts.\n"
        f"Now local time: {now_local.strftime('%Y-%m-%d %H:%M %Z')}\n"
        f"Recent events JSON:\n{events_json}\n\n"
        f"Recent market snapshot JSON:\n{market_json}\n"
    )
    return system_prompt, user_prompt


def _summary_length_instruction(slot: str) -> str:
    """Return the prompt length budget for each daily analysis slot."""
    if slot == "pre_tw_open":
        return "Total length 900-1700 Chinese characters."
    if slot == "macro_daily":
        return "Total length 650-1100 Chinese characters."
    if slot == "tw_close":
        return "Total length 650-1200 Chinese characters."
    return "Total length 500-1100 Chinese characters."


def _regime_flow_sections() -> str:
    """Return the fixed product-editor daily section order."""
    return (
        "1) 今日主命題\n"
        "2) 三個證據\n"
        "3) 市場正在定價什麼\n"
        "4) 台股傳導\n"
        "5) 反證條件\n"
        "6) 風險與資料缺口\n"
    )


def _regime_flow_guide() -> str:
    """Explain how each section should reason without bloating the report."""
    return (
        "Reasoning flow:\n"
        "- 今日主命題: one plain sentence stating the investable thesis, Taiwan bias, and main uncertainty.\n"
        "- 三個證據: exactly three evidence bullets; each bullet must connect source fact -> mechanism -> why it matters now.\n"
        "- 市場正在定價什麼: explain what expectations are already reflected in prices and what still has room for repricing.\n"
        "- 台股傳導: translate the thesis into Taiwan index, sectors, and mega-cap proxies such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭; do not write a watchlist.\n"
        "- 反證條件: state the cleanest data or market moves that would make the thesis wrong.\n"
        "- 風險與資料缺口: max three bullets; list missing data, stale data, and event risks.\n"
    )


def _normalize_text(text: str) -> str:
    """正規化 normalize text 對應的資料或結果。"""
    return "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()[:4500]


_VISIBLE_INTERNAL_LABEL_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\bmarket\s+scorecard(?:\s+\d{4}-\d{2}-\d{2})?(?:\s+overall)?\s*(?:為|=|is|:)?\s*[+-]?\d+\b",
            re.IGNORECASE,
        ),
        "盤前市場環境綜合指標",
    ),
    (
        re.compile(r"\bscorecard(?:\s+overall)?\s*(?:為|=|is|:)?\s*[+-]?\d+\b", re.IGNORECASE),
        "市場環境綜合指標",
    ),
    (
        re.compile(r"\b\d{1,2}:\d{2}\s+market_context\b", re.IGNORECASE),
        "盤前市場環境資料",
    ),
    (
        re.compile(r"\bmarket_context(?::[A-Za-z0-9_.-]+)?\b", re.IGNORECASE),
        "市場環境資料",
    ),
    (
        re.compile(r"未呼叫(?:付費)?(?:外部\s*)?(?:OpenAI|Anthropic|Claude)?\s*LLM\s+API", re.IGNORECASE),
        "部分即時外部資料未納入",
    ),
    (re.compile(r"\bt_relay_events\b", re.IGNORECASE), "本地新聞與事件資料"),
    (re.compile(r"\bt_market_analyses\b", re.IGNORECASE), "分析資料"),
    (re.compile(r"\bt_market_index_snapshots\b", re.IGNORECASE), "行情快照"),
    (re.compile(r"\bt_trade_signals\b", re.IGNORECASE), "交易訊號資料"),
    (re.compile(r"\banalysis_slot\b", re.IGNORECASE), "分析時段"),
    (re.compile(r"\bscheduled_time_local\b", re.IGNORECASE), "預定產出時間"),
    (re.compile(r"\braw_json\b", re.IGNORECASE), "內部稽核資料"),
    (re.compile(r"\bstructured_json\b", re.IGNORECASE), "結構化稽核資料"),
    (re.compile(r"\bclaim_verifier\b", re.IGNORECASE), "事實查核流程"),
    (re.compile(r"\bCodex\s+guard\b", re.IGNORECASE), "分析品質檢查"),
    (re.compile(r"\b(?:OpenAI|Anthropic|Claude)?\s*LLM\s+API\b", re.IGNORECASE), "外部模型服務"),
    (re.compile(r"\bpipeline\s+telemetry\b", re.IGNORECASE), "內部稽核資料"),
    (
        re.compile(r"本次修復[^。；;\n]*(?:[。；;]|$)", re.IGNORECASE),
        "本次分析主要依據本地新聞、行情與公開資料；",
    ),
)


def _sanitize_visible_report_text(text: str) -> str:
    """Replace pipeline-only labels before a report becomes reader-visible."""
    sanitized = text or ""
    for pattern, replacement in _VISIBLE_INTERNAL_LABEL_REPLACEMENTS:
        sanitized = pattern.sub(replacement, sanitized)
    return _normalize_text(sanitized)


def _is_delivery_enabled_for_slot(slot: str, calendar_state: MarketCalendarState) -> bool:
    """判斷此分析時段是否允許 Java 做對外觸達。"""
    # 中文：push_enabled 只代表 Java 可推送，不代表 Python 會直接呼叫 LINE。
    if slot in {"pre_tw_open", "macro_daily"}:
        return True
    if slot == "us_close":
        # 中文：一般日 us_close 只當隔天台股早盤素材；只有 TW 休市且美股有交易時才開放推送。
        return (not calendar_state.tw.is_trading_day) and calendar_state.us.is_trading_day
    return False


def _apply_claim_verifier_trust_gate(
    *,
    base_delivery_eligible: bool,
    claim_verification: dict[str, Any],
) -> dict[str, Any]:
    """Return delivery/signal eligibility after the claim-verifier trust gate."""
    enabled = _env_bool("MARKET_ANALYSIS_CLAIM_GATE_ENABLED", True)
    verifier_ok = bool(claim_verification.get("ok"))
    failed = enabled and not verifier_ok
    delivery_eligible = bool(base_delivery_eligible and not failed)
    signals_allowed = not failed
    reason = (
        "disabled"
        if not enabled
        else "claim_verifier_ok"
        if verifier_ok
        else "claim_verifier_failed"
    )
    return {
        "version": TRUST_GATE_VERSION,
        "enabled": enabled,
        "reason": reason,
        "claim_verifier_ok": verifier_ok,
        "support_rate": claim_verification.get("support_rate"),
        "unsupported_counts": claim_verification.get("unsupported_counts") or {},
        "unsupported_sample": claim_verification.get("unsupported") or {},
        "original_delivery_eligible": bool(base_delivery_eligible),
        "delivery_eligible": delivery_eligible,
        "delivery_blocked": bool(base_delivery_eligible and failed),
        "signals_allowed": signals_allowed,
        "signals_blocked": failed,
    }


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
        "fred_enabled",
        "fred_series_ids",
        "market_breadth_enabled",
        "ai_capex_enabled",
        "oil_supply_enabled",
        "scorecard_enabled",
        "scorecard_input_hash",
        "scorecard_overall_score",
        "scorecard_dimension_scores",
    ):
        if key in parsed:
            compact[key] = parsed[key]

    scorecard = parsed.get("scorecard")
    if isinstance(scorecard, dict):
        compact["scorecard"] = scorecard

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


def _int_env(name: str, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None and raw.strip() != "" else default
    except ValueError:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _provider_context_mode(provider: str) -> str:
    if str(provider or "").strip().lower() != "anthropic":
        return "full"
    return (os.getenv("MARKET_ANALYSIS_ANTHROPIC_CONTEXT_MODE") or "compact").strip().lower()


def _apply_provider_context_policy(
    *,
    provider: str,
    events_payload: list[dict[str, Any]],
    market_payload: list[dict[str, Any]],
    rag_examples: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Shrink prompt context only for Anthropic fallback to avoid large-context limits."""
    mode = _provider_context_mode(provider)
    if mode in {"", "full", "off", "disabled"}:
        return events_payload, market_payload, rag_examples, {
            "version": PROVIDER_CONTEXT_POLICY_VERSION,
            "provider": provider,
            "mode": "full",
            "enabled": False,
            "events_input": len(events_payload),
            "events_output": len(events_payload),
            "market_rows_input": len(market_payload),
            "market_rows_output": len(market_payload),
            "rag_input": len(rag_examples),
            "rag_output": len(rag_examples),
        }

    max_events = _int_env("MARKET_ANALYSIS_ANTHROPIC_MAX_EVENTS", 55, minimum=10)
    max_market_rows = _int_env("MARKET_ANALYSIS_ANTHROPIC_MAX_MARKET_ROWS", 12, minimum=0)
    max_rag = _int_env("MARKET_ANALYSIS_ANTHROPIC_RAG_K", 2, minimum=0)
    summary_chars = _int_env("MARKET_ANALYSIS_ANTHROPIC_EVENT_SUMMARY_CHARS", 500, minimum=120, maximum=2000)

    selected_events = _select_events_for_compact_context(events_payload, max_events=max_events)
    compact_events = [_compact_event_for_anthropic(event, summary_chars=summary_chars) for event in selected_events]
    compact_market = [_compact_market_row_for_anthropic(row) for row in market_payload[:max_market_rows]]
    compact_rag = [_compact_rag_for_anthropic(example, summary_chars=summary_chars) for example in rag_examples[:max_rag]]
    telemetry = {
        "version": PROVIDER_CONTEXT_POLICY_VERSION,
        "provider": provider,
        "mode": "anthropic_compact",
        "enabled": True,
        "events_input": len(events_payload),
        "events_output": len(compact_events),
        "market_rows_input": len(market_payload),
        "market_rows_output": len(compact_market),
        "rag_input": len(rag_examples),
        "rag_output": len(compact_rag),
        "summary_chars": summary_chars,
        "preserve_rules": ["scorecard", "market_context", "official_sources", "high_importance"],
    }
    return compact_events, compact_market, compact_rag, telemetry


def _select_events_for_compact_context(
    events_payload: list[dict[str, Any]],
    *,
    max_events: int,
) -> list[dict[str, Any]]:
    ranked = sorted(
        enumerate(events_payload),
        key=lambda item: (_compact_event_rank(item[1]), item[0]),
    )
    selected_indices = sorted(index for index, _event in ranked[:max_events])
    return [events_payload[index] for index in selected_indices]


def _compact_event_rank(event: dict[str, Any]) -> tuple[int, float]:
    source = str(event.get("source") or "").lower()
    annotation = event.get("annotation") if isinstance(event.get("annotation"), dict) else {}
    try:
        importance = float(annotation.get("importance") or 0.0)
    except (TypeError, ValueError):
        importance = 0.0
    if source == "market_context:scorecard":
        return (0, -importance)
    if source.startswith("market_context:"):
        return (1, -importance)
    if source.startswith(("fed:", "bls:", "eia:", "treasury:", "sec:", "twse_mops:", "twse:", "tpex:", "taifex:")):
        return (2, -importance)
    if source.startswith("market_analysis:"):
        return (3, -importance)
    return (4, -importance)


def _compact_event_for_anthropic(event: dict[str, Any], *, summary_chars: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": event.get("id"),
        "source": event.get("source"),
        "title": _trim_text(event.get("title"), 240),
        "summary": _trim_text(event.get("summary"), summary_chars),
        "published_at": event.get("published_at"),
    }
    annotation = event.get("annotation") if isinstance(event.get("annotation"), dict) else None
    if annotation:
        out["annotation"] = {
            "category": annotation.get("category"),
            "sentiment": annotation.get("sentiment"),
            "importance": annotation.get("importance"),
            "entities": (annotation.get("entities") or [])[:8] if isinstance(annotation.get("entities"), list) else [],
        }
    raw = _compact_raw_for_anthropic(str(event.get("source") or ""), event.get("raw"))
    if raw:
        out["raw"] = raw
    impact = event.get("impact") if isinstance(event.get("impact"), dict) else None
    if impact:
        out["impact"] = {
            key: impact.get(key)
            for key in ("summary", "market_relevance", "tw_relevance", "confidence")
            if impact.get(key) is not None
        }
    return out


def _compact_raw_for_anthropic(source: str, raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    if source == "market_context:scorecard":
        return {
            "event_type": raw.get("event_type"),
            "dimension": raw.get("dimension"),
            "scorecard": _shrink_json(raw.get("scorecard"), max_depth=5),
        }
    keep_keys = (
        "event_type",
        "dimension",
        "category",
        "metric",
        "symbol",
        "label",
        "value",
        "change",
        "change_pct",
        "as_of",
        "generated_at",
        "source",
        "data_freshness",
    )
    compact = {key: _shrink_json(raw.get(key), max_depth=3) for key in keep_keys if key in raw}
    return compact or None


def _compact_market_row_for_anthropic(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": row.get("event_id"),
        "source": row.get("source"),
        "trade_date": row.get("trade_date"),
        "session": row.get("session"),
        "symbol": row.get("symbol"),
        "label": row.get("label"),
        "open_price": row.get("open_price"),
        "last_price": row.get("last_price"),
        "recorded_price": row.get("recorded_price"),
        "created_at": row.get("created_at"),
    }


def _compact_rag_for_anthropic(example: dict[str, Any], *, summary_chars: int) -> dict[str, Any]:
    return {
        "kind": example.get("kind"),
        "event_id": example.get("event_id"),
        "analysis_id": example.get("analysis_id"),
        "source": example.get("source"),
        "title": _trim_text(example.get("title"), 180),
        "summary": _trim_text(example.get("summary"), summary_chars),
        "similarity": example.get("similarity"),
        "metadata_score": example.get("metadata_score"),
        "outcome_score": example.get("outcome_score"),
        "hybrid_score": example.get("hybrid_score"),
    }


def _trim_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _shrink_json(value: Any, *, max_depth: int) -> Any:
    if max_depth <= 0:
        return _trim_text(value, 160)
    if isinstance(value, dict):
        return {str(key): _shrink_json(item, max_depth=max_depth - 1) for key, item in list(value.items())[:30]}
    if isinstance(value, list):
        return [_shrink_json(item, max_depth=max_depth - 1) for item in value[:10]]
    if isinstance(value, str):
        return _trim_text(value, 500)
    return value


def _build_upstream_analysis_context(
    store: MySqlEventStore,
    slot: str,
    calendar_state: MarketCalendarState,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Add stored analyses that should be treated as upstream context."""
    if slot != "pre_tw_open":
        return [], {"included": False, "reason": "slot_not_pre_tw_open"}
    if not calendar_state.us.is_trading_day:
        # 中文：US 休市、TW 有交易時，台股早盤仍要產生，但不能塞舊的 us_close 進 prompt。
        return [], {
            "included": False,
            "slot": "us_close",
            "reason": "us_close_session_closed",
            "us_close_session_date": calendar_state.us_close_session_date.isoformat(),
        }

    latest = store.fetch_latest_market_analysis("us_close")
    if latest is None:
        return [], {"included": False, "slot": "us_close", "reason": "not_found"}

    summary = _normalize_text(latest.summary_text)[:3000]
    context_meta = {
        "included": True,
        "slot": "us_close",
        "analysis_id": latest.row_id,
        "analysis_date": latest.analysis_date,
        "scheduled_time_local": latest.scheduled_time_local,
        "updated_at": latest.updated_at,
    }
    event = {
        "id": f"analysis:{latest.row_id}",
        "source": "market_analysis:us_close",
        "title": f"Latest stored U.S. close analysis for Taiwan pre-open ({latest.analysis_date})",
        "url": f"internal://market_analysis/{latest.row_id}",
        "summary": summary,
        "published_at": None,
        "created_at": latest.updated_at,
        "raw": context_meta,
        "annotation": {
            "entities": [{"kind": "market", "value": "US close"}],
            "category": "market_move",
            "importance": 0.95,
            "sentiment": "neutral",
            "annotator": "system",
            "annotator_version": "upstream-analysis-v1",
            "annotated_at": None,
        },
        "impact": {
            "topic": "us_close_context",
            "impact_region": "TW",
            "impact_scope": "market",
            "impact_direction": "mixed",
            "confidence": "medium",
            "data_gap": False,
        },
    }
    return [event], context_meta


def _slot_env_name(slot: str | None, suffix: str) -> str:
    safe_slot = "".join(ch if ch.isalnum() else "_" for ch in str(slot or "")).upper()
    return f"MARKET_ANALYSIS_{safe_slot}_{suffix}"


def _pipeline_mode_from_env(slot: str | None = None) -> str:
    """執行 pipeline mode from env 的主要流程。"""
    slot_override = os.getenv(_slot_env_name(slot, "PIPELINE")) if slot else None
    raw = (slot_override or os.getenv("MARKET_ANALYSIS_PIPELINE") or "multi_stage").strip().lower()
    if raw not in {"legacy", "multi_stage", "auto", "digest"}:
        return "multi_stage"
    return raw


def _analysis_intent(slot: str, pipeline_mode: str) -> str:
    if slot == "us_close" and pipeline_mode == "digest":
        return "us_close_digest_for_preopen"
    if slot == "pre_tw_open":
        return "preopen_trade_decision"
    if slot == "tw_close":
        return "tw_close_review"
    if slot == "macro_daily":
        return "macro_context_only"
    return "daily_market_analysis"


def _digest_limits(slot: str) -> tuple[int, int]:
    default_events = 45 if slot == "us_close" else 60
    default_market_rows = 8 if slot == "us_close" else 12
    max_events = _int_env(_slot_env_name(slot, "DIGEST_MAX_EVENTS"), default_events, minimum=5)
    max_market_rows = _int_env(_slot_env_name(slot, "DIGEST_MAX_MARKET_ROWS"), default_market_rows, minimum=0)
    return max_events, max_market_rows


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

    stage0 = stage0_thesis_selector.run(
        context=ctx,
        events_payload=events_payload,
        market_payload=market_payload,
        snapshot_dir=snapshot_dir,
    )
    telemetry["stages"]["stage0"] = _stage_telemetry(stage0)
    stage0_output = stage0.output if stage0.ok() and isinstance(stage0.output, dict) else {
        "core_tensions": [],
        "selection_notes": ["stage0 unavailable"],
    }
    telemetry["core_tensions"] = stage0_output.get("core_tensions") or []

    # 多階段流程採「任何關鍵 LLM stage 失敗就整體回退」策略；
    # deterministic stage0 失敗時降級為空 thesis，不阻塞整條分析。
    stage1 = stage1_digest.run(
        context=ctx,
        events_payload=events_payload,
        market_payload=market_payload,
        stage0_output=stage0_output,
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
        stage0_output=stage0_output,
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
        stage0_output=stage0_output,
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
    telemetry["tw_mapping"] = stage3.output

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


def _aggregate_token_usage(
    pipeline_telemetry: dict[str, Any] | None,
    legacy_token_usage: dict[str, Any] | None,
) -> dict[str, Any]:
    """REQ-016 — sum per-stage usage rows into a single token_usage block.

    Walks ``pipeline_telemetry["stages"]`` for stage-level ``usage`` extras
    (set by each stage's ``run()``) and adds the legacy fallback usage if the
    legacy path was taken. Returns a stable schema even when no LLM call ran.
    """
    stages_usage: list[dict[str, Any]] = []
    if isinstance(pipeline_telemetry, dict):
        stages = pipeline_telemetry.get("stages")
        if isinstance(stages, dict):
            for stage_name, stage_payload in stages.items():
                if not isinstance(stage_payload, dict):
                    continue
                usage = stage_payload.get("usage")
                if isinstance(usage, dict):
                    stages_usage.append({"stage": stage_name, **usage})
    if legacy_token_usage:
        stages_usage.append({"stage": "legacy_single_call", **legacy_token_usage})

    total_prompt = sum(int(u.get("prompt_tokens") or 0) for u in stages_usage)
    total_completion = sum(int(u.get("completion_tokens") or 0) for u in stages_usage)
    total_cached = sum(int(u.get("cached_tokens") or 0) for u in stages_usage)
    total_cache_creation = sum(int(u.get("cache_creation_tokens") or 0) for u in stages_usage)
    cache_hit_ratio = (total_cached / total_prompt) if total_prompt > 0 else 0.0

    return {
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "cached_tokens": total_cached,
        "cache_creation_tokens": total_cache_creation,
        "cache_hit_ratio": round(cache_hit_ratio, 3),
        "prompt_assets_version": PROMPT_ASSETS_VERSION,
        "stages": stages_usage,
    }


def _is_retryable_provider_error(exc: BaseException | str) -> bool:
    text = str(exc or "").lower()
    retry_markers = (
        "status=429",
        "insufficient_quota",
        "rate_limit",
        "rate limited",
        "too many requests",
        "quota",
        "status=500",
        "status=502",
        "status=503",
        "status=504",
        "overloaded",
        "temporarily unavailable",
    )
    return any(marker in text for marker in retry_markers)


def _runtime_failover_config(
    config: MarketAnalysisConfig,
    exc: BaseException | str,
) -> MarketAnalysisConfig | None:
    if not _env_bool("MARKET_ANALYSIS_RUNTIME_FAILOVER_ENABLED", True):
        return None
    if (config.provider or "").strip().lower() != "openai":
        return None
    if not _is_retryable_provider_error(exc):
        return None
    provider, model, api_base, api_key_file, api_key = _resolve_market_anthropic_settings()
    if not api_key:
        logger.warning("Runtime LLM failover skipped: missing Anthropic API key")
        return None
    router_payload = dict(config.model_router or {})
    router_payload["runtime_failover"] = {
        "from_provider": config.provider,
        "from_model": config.model,
        "to_provider": provider,
        "to_model": model,
        "reason": str(exc)[:500],
    }
    return replace(
        config,
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=api_key,
        api_key_file=api_key_file,
        model_router=router_payload,
    )


def _generate_analysis_once(
    *,
    config: MarketAnalysisConfig,
    slot: str,
    now_local: datetime,
    events_payload: list[dict[str, Any]],
    market_payload: list[dict[str, Any]],
    rag_examples: list[dict[str, Any]],
    upstream_analysis_context: dict[str, Any] | None,
) -> AnalysisGenerationResult:
    provider_events, provider_market, provider_rag, provider_context_policy = _apply_provider_context_policy(
        provider=config.provider,
        events_payload=events_payload,
        market_payload=market_payload,
        rag_examples=rag_examples,
    )

    requested_pipeline_mode = _pipeline_mode_from_env(slot)
    pipeline_mode = requested_pipeline_mode
    pipeline_telemetry: dict[str, Any] | None = None
    summary_text: str | None = None
    structured_payload: dict[str, Any] | None = None
    legacy_token_usage: dict[str, Any] | None = None
    used_multi_stage = False

    if pipeline_mode == "digest":
        digest_max_events, digest_max_market_rows = _digest_limits(slot)
        provider_events = provider_events[:digest_max_events]
        provider_market = provider_market[:digest_max_market_rows] if digest_max_market_rows else []
        provider_rag = []
        provider_context_policy = dict(provider_context_policy)
        provider_context_policy["digest_policy"] = {
            "enabled": True,
            "max_events": digest_max_events,
            "max_market_rows": digest_max_market_rows,
            "rag_examples": 0,
            "purpose": "upstream_preopen_context",
        }
        system_prompt, user_prompt = _build_us_close_digest_prompts(
            slot=slot,
            now_local=now_local,
            events_json=json.dumps(provider_events, ensure_ascii=False),
            market_json=json.dumps(provider_market, ensure_ascii=False),
        )
        _write_prompt_snapshots(system_prompt, user_prompt, slot)
        summary_text_raw, legacy_usage = _call_llm(
            provider=config.provider,
            api_base=config.api_base,
            api_key=config.api_key,
            model=config.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        summary_text = _normalize_text(summary_text_raw)
        legacy_token_usage = legacy_usage.to_dict()

    if summary_text is None and pipeline_mode in ("multi_stage", "auto"):
        summary_text, structured_payload, pipeline_telemetry = _run_multi_stage_pipeline(
            config=config,
            slot=slot,
            now_local=now_local,
            events_payload=provider_events,
            market_payload=provider_market,
            rag_examples=provider_rag,
        )
        if summary_text is not None:
            used_multi_stage = True
        else:
            logger.warning(
                "Multi-stage pipeline failed; falling back to legacy single-call. telemetry=%s",
                pipeline_telemetry,
            )
            pipeline_mode = "legacy"

    if summary_text is None:
        system_prompt, user_prompt = _build_prompts(
            config=config,
            slot=slot,
            now_local=now_local,
            events_json=json.dumps(provider_events, ensure_ascii=False),
            market_json=json.dumps(provider_market, ensure_ascii=False),
            upstream_analysis_context=upstream_analysis_context,
        )
        _write_prompt_snapshots(system_prompt, user_prompt, slot)
        summary_text_raw, legacy_usage = _call_llm(
            provider=config.provider,
            api_base=config.api_base,
            api_key=config.api_key,
            model=config.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        summary_text = _normalize_text(summary_text_raw)
        legacy_token_usage = legacy_usage.to_dict()

    return AnalysisGenerationResult(
        config=config,
        requested_pipeline_mode=requested_pipeline_mode,
        pipeline_mode="multi_stage" if used_multi_stage else pipeline_mode,
        events_payload=provider_events,
        market_payload=provider_market,
        rag_examples=provider_rag,
        provider_context_policy=provider_context_policy,
        summary_text=summary_text,
        structured_payload=structured_payload,
        pipeline_telemetry=pipeline_telemetry,
        legacy_token_usage=legacy_token_usage,
        used_multi_stage=used_multi_stage,
    )


def _retrieve_rag_examples(
    store: MySqlEventStore,
    events_payload: list[dict[str, Any]],
    *,
    slot: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """檢索 retrieve rag examples 對應的資料或結果。"""
    if not rag_enabled_from_env():
        return [], {"enabled": False, "examples_count": 0}

    embedding_model = (os.getenv("RAG_EMBEDDING_MODEL") or RAG_DEFAULT_EMBEDDING_MODEL).strip()
    vector_weight = float(os.getenv("MARKET_ANALYSIS_RAG_VECTOR_WEIGHT", "0.62"))
    metadata_weight = float(os.getenv("MARKET_ANALYSIS_RAG_METADATA_WEIGHT", "0.25"))
    outcome_weight = float(os.getenv("MARKET_ANALYSIS_RAG_OUTCOME_WEIGHT", "0.13"))
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
            metadata_filter_threshold=float(os.getenv("MARKET_ANALYSIS_RAG_METADATA_FILTER_THRESHOLD", "0.10")),
            vector_weight=vector_weight,
            metadata_weight=metadata_weight,
            outcome_weight=outcome_weight,
            include_analysis_examples=_env_bool("MARKET_ANALYSIS_RAG_INCLUDE_ANALYSES", True),
            analysis_slot=slot,
        )
        prompt_examples = [example.to_prompt_dict() for example in examples]
        return prompt_examples, {
            "enabled": True,
            "mode": "hybrid",
            "embedding_model": embedding_model,
            "examples_count": len(prompt_examples),
            "weights": {
                "vector": vector_weight,
                "metadata": metadata_weight,
                "outcome": outcome_weight,
            },
            "score_components": [
                {
                    "kind": item.get("kind"),
                    "event_id": item.get("event_id"),
                    "analysis_id": item.get("analysis_id"),
                    "similarity": item.get("similarity"),
                    "metadata_score": item.get("metadata_score"),
                    "outcome_score": item.get("outcome_score"),
                    "hybrid_score": item.get("hybrid_score"),
                }
                for item in prompt_examples
            ],
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
    slot_decision = _resolve_slot_decision(config, now_local)
    slot = slot_decision.slot
    if slot is None:
        logger.info(
            "Market analysis skipped reason=%s requested_slot=%s calendar=%s",
            slot_decision.skipped_reason,
            slot_decision.requested_slot,
            slot_decision.calendar_state.to_dict(),
        )
        return {
            "ok": True,
            "skipped": slot_decision.skipped_reason or "schedule",
            "requested_slot": slot_decision.requested_slot,
            "calendar": slot_decision.calendar_state.to_dict(),
        }

    if not config.api_key:
        raise RuntimeError(
            f"Missing {config.provider} API key. Checked env vars and file: {config.api_key_file}"
        )

    relay_settings = load_settings(config.env_file)
    if not relay_settings.mysql_enabled:
        raise RuntimeError("Market analysis requires RELAY_MYSQL_ENABLED=true")

    store = MySqlEventStore(relay_settings)
    store.initialize()
    context_pack_enabled = bool(getattr(config, "context_pack_enabled", True))
    context_candidate_limit = int(
        getattr(config, "context_pack_candidate_limit", 0) or config.max_events
    )
    recent_event_limit = max(config.max_events, context_candidate_limit) if context_pack_enabled else config.max_events
    recent_events = store.fetch_recent_summary_events(days=1, limit=recent_event_limit)
    recent_market_rows = store.fetch_recent_market_snapshots(hours=config.lookback_hours, limit=config.max_market_rows)

    events_payload = _build_events_payload(store, recent_events)
    upstream_analysis_events, upstream_analysis_context = _build_upstream_analysis_context(
        store,
        slot,
        slot_decision.calendar_state,
    )
    if upstream_analysis_events:
        events_payload.extend(upstream_analysis_events)
    if context_pack_enabled:
        events_payload, context_pack_telemetry = build_context_pack(events_payload, max_events=config.max_events)
    else:
        context_pack_telemetry = {
            "version": CONTEXT_PACK_VERSION,
            "enabled": False,
            "input_count": len(events_payload),
            "output_count": len(events_payload),
            "max_events": config.max_events,
        }
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
    rag_examples, rag_telemetry = _retrieve_rag_examples(store, events_payload, slot=slot)
    runtime_failover: dict[str, Any] | None = None
    try:
        generation = _generate_analysis_once(
            config=config,
            slot=slot,
            now_local=now_local,
            events_payload=events_payload,
            market_payload=market_payload,
            rag_examples=rag_examples,
            upstream_analysis_context=upstream_analysis_context,
        )
    except Exception as exc:
        failover_config = _runtime_failover_config(config, exc)
        if failover_config is None:
            raise
        runtime_failover = dict((failover_config.model_router or {}).get("runtime_failover") or {})
        logger.warning(
            "Market analysis runtime LLM failover from %s/%s to %s/%s after error=%s",
            config.provider,
            config.model,
            failover_config.provider,
            failover_config.model,
            str(exc)[:300],
        )
        generation = _generate_analysis_once(
            config=failover_config,
            slot=slot,
            now_local=now_local,
            events_payload=events_payload,
            market_payload=market_payload,
            rag_examples=rag_examples,
            upstream_analysis_context=upstream_analysis_context,
        )

    config = generation.config
    events_payload = generation.events_payload
    market_payload = generation.market_payload
    rag_examples = generation.rag_examples
    provider_context_policy = generation.provider_context_policy
    raw_summary_text = generation.summary_text
    summary_text = _sanitize_visible_report_text(raw_summary_text)
    visible_text_sanitized = summary_text != _normalize_text(raw_summary_text or "")
    structured_payload = generation.structured_payload
    if isinstance(structured_payload, dict) and isinstance(structured_payload.get("summary_text"), str):
        structured_payload = {
            **structured_payload,
            "summary_text": _sanitize_visible_report_text(structured_payload["summary_text"]),
        }
    pipeline_telemetry = generation.pipeline_telemetry
    legacy_token_usage = generation.legacy_token_usage
    used_multi_stage = generation.used_multi_stage
    requested_pipeline_mode = generation.requested_pipeline_mode
    effective_pipeline_mode = generation.pipeline_mode

    claim_verification = verify_claim_coverage(
        summary_text=summary_text or "",
        structured_payload=structured_payload,
        events_payload=events_payload,
        market_payload=market_payload,
        allowed_tickers=_allowed_claim_tickers_for_slot(
            slot,
            pipeline_mode=effective_pipeline_mode,
        ),
    )
    if pipeline_telemetry is not None:
        pipeline_telemetry["claim_verifier"] = claim_verification
        pipeline_telemetry["visible_text_sanitized"] = visible_text_sanitized

    token_usage = _aggregate_token_usage(
        pipeline_telemetry if used_multi_stage else None,
        legacy_token_usage,
    )

    logger.info(
        "[MARKET_ANALYSIS_STORED_ONLY] slot=%s model=%s pipeline=%s tokens prompt=%d cached=%d cache_hit=%.3f",
        slot,
        config.model,
        effective_pipeline_mode,
        token_usage.get("prompt_tokens", 0),
        token_usage.get("cached_tokens", 0),
        token_usage.get("cache_hit_ratio", 0.0),
    )
    logger.info("[MARKET_ANALYSIS_TEXT]\n%s", summary_text)

    raw_dimension = (
        "daily_tw_close"
        if slot == "tw_close"
        else "daily_macro"
        if slot == "macro_daily"
        else "daily_market_analysis"
    )
    base_push_enabled = _is_delivery_enabled_for_slot(slot, slot_decision.calendar_state)
    trust_gate = _apply_claim_verifier_trust_gate(
        base_delivery_eligible=base_push_enabled,
        claim_verification=claim_verification,
    )
    push_enabled = bool(trust_gate["delivery_eligible"])
    if trust_gate["signals_blocked"] or trust_gate["delivery_blocked"]:
        logger.warning(
            "[MARKET_ANALYSIS_TRUST_GATE] slot=%s blocked_delivery=%s blocked_signals=%s support_rate=%s unsupported=%s",
            slot,
            trust_gate["delivery_blocked"],
            trust_gate["signals_blocked"],
            trust_gate.get("support_rate"),
            trust_gate.get("unsupported_counts"),
        )
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
                "display_title": now_local.date().isoformat(),
                "generated_at": now_local.isoformat(),
                "calendar_decision": slot_decision.to_dict(),
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
                "delivery_eligible": push_enabled,
                "delivery_eligible_before_trust_gate": base_push_enabled,
                "delivery_policy": "daily_pre_tw_open_macro_or_tw_holiday_us_close",
                "delivery_owner": "java",
                "python_push_removed": True,
                "analysis_intent": _analysis_intent(slot, effective_pipeline_mode),
                "web_search_requested": config.provider == "openai" and _openai_web_search_enabled(),
                "model_router": getattr(config, "model_router", None),
                "runtime_failover": runtime_failover,
                "upstream_analysis_context": upstream_analysis_context,
                "context_pack": context_pack_telemetry,
                "provider_context_policy": provider_context_policy,
                "rag": rag_telemetry,
                "claim_verifier": claim_verification,
                "trust_gate": trust_gate,
                "requested_pipeline_mode": requested_pipeline_mode,
                "pipeline_mode": effective_pipeline_mode,
                "pipeline_stages": pipeline_telemetry,
                "structured": structured_payload,
                "token_usage": token_usage,
            },
            ensure_ascii=False,
        ),
        structured_json=(
            json.dumps(structured_payload, ensure_ascii=False)
            if structured_payload is not None
            else None
        ),
    )
    analysis_id = store.upsert_market_analysis(record)
    trade_signals_count = 0
    trade_signal_recommendations_count = 0
    prior_reference_added = 0
    if analysis_id and trust_gate["signals_allowed"]:
        trade_signals = []
        structured_signals_count = 0
        quote_fallback_added = 0
        if used_multi_stage:
            trade_signals = build_trade_signals_from_analysis(
                analysis_id=analysis_id,
                analysis_date=record.analysis_date,
                analysis_slot=record.analysis_slot,
                structured_payload=structured_payload,
                pipeline_telemetry=pipeline_telemetry,
            )
            structured_signals_count = len(trade_signals)
        reference_levels_filled = 0
        if _should_build_fixed_pool_signals(slot, pipeline_mode=effective_pipeline_mode):
            preferred_fallback_tickers = _preferred_tw_fallback_tickers_from_env()
            fallback_signals = build_quote_event_trade_signals(
                analysis_id=analysis_id,
                analysis_date=record.analysis_date,
                analysis_slot=record.analysis_slot,
                events=recent_events,
                max_signals=10,
                preferred_tickers=preferred_fallback_tickers,
            )
            trade_signals, reference_levels_filled = _merge_reference_levels_from_fallbacks(
                trade_signals,
                fallback_signals,
            )
            recommendation_tickers = {
                signal.ticker
                for signal in trade_signals
                if not is_excluded_trade_signal_ticker(signal.ticker)
                if signal.direction == "long" and signal.strategy_type in {"swing", "medium"}
            }
            existing_tickers = {signal.ticker for signal in trade_signals}
            for fallback_signal in fallback_signals:
                if is_excluded_trade_signal_ticker(fallback_signal.ticker):
                    continue
                if len(recommendation_tickers) >= 10 and fallback_signal.ticker not in preferred_fallback_tickers:
                    break
                if fallback_signal.ticker in existing_tickers:
                    continue
                trade_signals.append(fallback_signal)
                existing_tickers.add(fallback_signal.ticker)
                if fallback_signal.direction == "long" and fallback_signal.strategy_type in {"swing", "medium"}:
                    recommendation_tickers.add(fallback_signal.ticker)
                    quote_fallback_added += 1
            trade_signals = [
                signal
                for signal in trade_signals
                if not is_excluded_trade_signal_ticker(signal.ticker)
            ]
            existing_tickers = {signal.ticker for signal in trade_signals}
            missing_reference_tickers = [
                ticker
                for ticker in FIXED_MARKET_ANALYSIS_WATCH_POOL
                if ticker not in existing_tickers and not is_excluded_trade_signal_ticker(ticker)
            ]
            if missing_reference_tickers:
                prior_rows = store.fetch_recent_trade_signal_references(
                    tickers=missing_reference_tickers,
                    exclude_analysis_id=analysis_id,
                    days=_int_env("MARKET_ANALYSIS_PRIOR_SIGNAL_LOOKBACK_DAYS", 30, minimum=1, maximum=180),
                )
                prior_signals = build_prior_signal_reference_trade_signals(
                    analysis_id=analysis_id,
                    analysis_date=record.analysis_date,
                    analysis_slot=record.analysis_slot,
                    prior_rows=prior_rows,
                    missing_tickers=missing_reference_tickers,
                )
                trade_signals.extend(prior_signals)
                prior_reference_added = len(prior_signals)
        if used_multi_stage or trade_signals:
            trade_signals_count = store.replace_trade_signals_for_analysis(analysis_id, trade_signals)
            source_label = "structured"
            if prior_reference_added and (quote_fallback_added or structured_signals_count):
                source_label = "structured_plus_fallback_plus_prior"
            elif prior_reference_added:
                source_label = "prior_signal_reference"
            elif quote_fallback_added and structured_signals_count:
                source_label = "structured_plus_quote_fallback"
            elif quote_fallback_added:
                source_label = "quote_fallback"
            logger.info(
                "[TRADE_SIGNALS_STORED] analysis_id=%s slot=%s count=%d status=pending_review source=%s fallback_added=%d prior_reference_added=%d reference_levels_filled=%d",
                analysis_id,
                slot,
                trade_signals_count,
                source_label,
                quote_fallback_added,
                prior_reference_added,
                reference_levels_filled,
            )
        if _should_build_fixed_pool_signals(slot, pipeline_mode=effective_pipeline_mode):
            recommendations = [
                row
                for row in store.fetch_trade_signal_recommendations(analysis_id, limit=10)
                if not is_excluded_trade_signal_ticker(row.get("ticker"))
                and is_fixed_market_analysis_watch_ticker(row.get("ticker"))
            ]
            trade_signal_recommendations_count = min(len(recommendations), 10)
            if _should_emit_recommendation_section(slot, pipeline_mode=effective_pipeline_mode):
                recommendation_section = build_trade_signal_recommendation_section(recommendations)
                if recommendation_section:
                    summary_text = f"{summary_text.rstrip()}\n\n{recommendation_section}"
                    store.update_market_analysis_summary_text(analysis_id, summary_text)
                    logger.info(
                        "[TRADE_SIGNAL_RECOMMENDATIONS_APPENDED] analysis_id=%s count=%d",
                        analysis_id,
                        trade_signal_recommendations_count,
                    )
    elif analysis_id:
        logger.warning(
            "[TRADE_SIGNALS_SKIPPED_BY_TRUST_GATE] analysis_id=%s slot=%s reason=%s",
            analysis_id,
            slot,
            trust_gate.get("reason"),
        )
    return {
        "ok": True,
        "slot": slot,
        "requested_slot": slot_decision.requested_slot,
        "analysis_date": record.analysis_date,
        "provider": config.provider,
        "model": config.model,
        "events_used": record.events_used,
        "market_rows_used": record.market_rows_used,
        "rag_examples_used": len(rag_examples),
        "trade_signals_stored": trade_signals_count,
        "trade_signal_recommendations": trade_signal_recommendations_count,
        "prior_signal_references": prior_reference_added,
        "push_enabled": push_enabled,
        "pushed": 0,
        "trust_gate": trust_gate,
        "calendar": slot_decision.calendar_state.to_dict(),
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
