"""Stage 3: Taiwan-stock mapping.

Translates transmission chains into concrete Taiwan sector / ticker watch
lists. Every item must carry ``evidence_ids`` that reference stage 1 event
IDs, keeping the final report auditable.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from event_relay.analysis_stages.context import StageContext, StageResult
from event_relay.analysis_stages.llm_json import call_llm_json
from event_relay.analysis_stages.schemas import STAGE3_TW_MAPPING_SCHEMA


logger = logging.getLogger(__name__)
STAGE_NAME = "stage3_tw_mapping"
_SCHEMA_NAME = "market_analysis_stage3_tw_mapping"


def build_prompts(
    *,
    slot: str,
    now_local_iso: str,
    stage1_json: str,
    stage2_json: str,
) -> tuple[str, str]:
    """建立 build prompts 對應的資料或結果。"""
    system_prompt = (
        "You are a Taiwan equity analyst. Given normalised events and "
        "transmission chains, produce: sector_watch, stock_watch, risks, "
        "and data_gaps. Every sector_watch and stock_watch entry MUST carry "
        "evidence_ids that reference event IDs from the stage1 digest. Do not "
        "recommend names not supported by the evidence. Output is a single "
        "JSON object matching the schema; no prose, no markdown."
    )
    user_prompt = (
        f"Slot: {slot}\n"
        f"Now local: {now_local_iso}\n\n"
        "Rules:\n"
        "- evidence_ids must be a subset of stage1 event IDs.\n"
        "- sector labels should use Taiwan-market vocabulary "
        "(e.g. 半導體上游, AI 供應鏈, 金控, 航運, 中小型股).\n"
        "- stock_watch tickers use 4-digit TWSE codes when known; omit rather than guess.\n"
        "- For pre_tw_open, stock_watch should aim for five evidence-backed Taiwan tickers "
        "suited to short/medium-term long setups; if fewer than five are supported, list the gap.\n"
        "- When Fed path / liquidity / credit stress / sentiment-positioning events are present, "
        "map them into Taiwan sector tilt before picking tickers: semis/AI beta, financials, "
        "high-dividend defensives, cyclicals, and small-cap risk appetite.\n"
        "- For macro_daily, keep stock_watch empty and focus on macro risks / data gaps.\n"
        "- risks: concrete things that could invalidate the setup.\n"
        "- data_gaps: what you would want to confirm next (e.g. overnight ADR, OTC 融資餘額).\n"
        "- Keep each list 0-6 items; quality over quantity.\n\n"
        f"Stage1 digest JSON:\n{stage1_json}\n\n"
        f"Stage2 chains JSON:\n{stage2_json}\n"
    )
    return system_prompt, user_prompt


def run(
    *,
    context: StageContext,
    stage1_output: dict[str, Any],
    stage2_output: dict[str, Any],
    snapshot_dir: Path | None = None,
) -> StageResult:
    """執行 run 的主要流程。"""
    chains_in = len(stage2_output.get("chains") or [])
    logger.info(
        "[stage3_tw_mapping] start slot=%s model=%s chains_in=%d",
        context.slot,
        context.model,
        chains_in,
    )
    started = time.perf_counter()

    system_prompt, user_prompt = build_prompts(
        slot=context.slot,
        now_local_iso=context.now_local.isoformat(),
        stage1_json=json.dumps(stage1_output, ensure_ascii=False),
        stage2_json=json.dumps(stage2_output, ensure_ascii=False),
    )
    if snapshot_dir is not None:
        _write_prompt_snapshot(snapshot_dir, context.slot, system_prompt, user_prompt)

    try:
        parsed, raw_text, usage = call_llm_json(
            provider=context.provider,
            api_base=context.api_base,
            api_key=context.api_key,
            model=context.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=STAGE3_TW_MAPPING_SCHEMA,
            schema_name=_SCHEMA_NAME,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        logger.error("[stage3_tw_mapping] failed elapsed=%.2fs error=%s", elapsed, exc)
        return StageResult(
            name=STAGE_NAME,
            model=context.model,
            output=None,
            error=str(exc),
        )

    sectors_count = len(parsed.get("sector_watch") or [])
    stocks_count = len(parsed.get("stock_watch") or [])
    risks_count = len(parsed.get("risks") or [])
    gaps_count = len(parsed.get("data_gaps") or [])
    elapsed = time.perf_counter() - started
    logger.info(
        "[stage3_tw_mapping] ok elapsed=%.2fs sectors=%d stocks=%d risks=%d data_gaps=%d",
        elapsed,
        sectors_count,
        stocks_count,
        risks_count,
        gaps_count,
    )
    return StageResult(
        name=STAGE_NAME,
        model=context.model,
        output=parsed,
        raw_text=raw_text,
        extras={
            "sectors_count": sectors_count,
            "stocks_count": stocks_count,
            "risks_count": risks_count,
            "data_gaps_count": gaps_count,
            "elapsed_sec": round(elapsed, 3),
            "usage": usage.to_dict(),
        },
    )


def _write_prompt_snapshot(snapshot_dir: Path, slot: str, system_prompt: str, user_prompt: str) -> None:
    """寫入 write prompt snapshot 對應的資料或結果。"""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / f"market_analysis_{slot}_stage3_tw_mapping_system.txt").write_text(system_prompt, encoding="utf-8")
    (snapshot_dir / f"market_analysis_{slot}_stage3_tw_mapping_user.txt").write_text(user_prompt, encoding="utf-8")
