"""Stage 2: causal transmission chains.

Consumes stage 1 output only (not the original raw events) and asks the model
to link events into transmission chains that explain how global moves reach
Taiwan equity risk. Each chain lists trigger event IDs, a terse path string,
an overall direction, a strength 0-1, and the assumptions the chain relies on.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from event_relay.analysis_stages.context import StageContext, StageResult
from event_relay.analysis_stages.llm_json import call_llm_json
from event_relay.analysis_stages.schemas import STAGE2_TRANSMISSION_SCHEMA


logger = logging.getLogger(__name__)
STAGE_NAME = "stage2_transmission"
_SCHEMA_NAME = "market_analysis_stage2_transmission"


def build_prompts(
    *,
    slot: str,
    now_local_iso: str,
    stage1_json: str,
    retrieved_examples_json: str = "[]",
) -> tuple[str, str]:
    """建立 build prompts 對應的資料或結果。"""
    slot_focus = {
        "us_close": "how the U.S. close transmits to the Taiwan next session.",
        "pre_tw_open": "what matters before 09:00 Taiwan open.",
        "macro_daily": "macro-only world context when Taiwan and the relevant U.S. session are closed.",
        "tw_close": "how today's Taiwan close + US overnight context transmits to tomorrow.",
    }.get(slot, "market transmission to Taiwan equities.")

    system_prompt = (
        "You are a macro transmission-chain analyst. "
        "Given a normalised event digest, draw explicit cause->effect chains "
        "ending in Taiwan equity risk. Each chain must list the trigger event "
        "IDs it depends on, a compact arrow path, an overall direction, a "
        "strength score 0-1, and the key assumptions that would invalidate it "
        "if false. Do not invent events that are absent from the digest. "
        "Output is a single JSON object matching the schema; no prose."
    )
    user_prompt = (
        f"Slot focus: {slot_focus}\n"
        f"Now local: {now_local_iso}\n\n"
        "Rules:\n"
        "- Use only event IDs present in the stage1 digest.\n"
        "- path uses short arrows, e.g. 'FOMC dovish -> US 10y down -> tech lead -> TW semi beta'.\n"
        "- Prefer explicit macro-regime paths when evidence exists: inflation/labor -> Fed path -> yields; "
        "Fed balance sheet/RRP/TGA/reserves -> liquidity; credit spreads/banks -> risk appetite; "
        "VIX/positioning proxies -> chase-or-fade risk.\n"
        "- strength 0.8+: high-confidence direct link; 0.4-0.7: conditional; <0.4: weak/speculative.\n"
        "- assumptions are the load-bearing conditions; list at least one.\n"
        "- Produce 1-5 chains total; deduplicate overlapping paths.\n\n"
        "Historical retrieved examples JSON:\n"
        f"{retrieved_examples_json}\n\n"
        "Use historical examples only as analogues for possible transmission paths. "
        "They are not current facts and their event IDs must not appear in trigger_event_ids.\n\n"
        f"Stage1 digest JSON:\n{stage1_json}\n"
    )
    return system_prompt, user_prompt


def run(
    *,
    context: StageContext,
    stage1_output: dict[str, Any],
    retrieved_examples: list[dict[str, Any]] | None = None,
    snapshot_dir: Path | None = None,
) -> StageResult:
    """執行 run 的主要流程。"""
    events_in = len(stage1_output.get("events") or [])
    logger.info(
        "[stage2_transmission] start slot=%s model=%s stage1_events=%d",
        context.slot,
        context.model,
        events_in,
    )
    started = time.perf_counter()

    system_prompt, user_prompt = build_prompts(
        slot=context.slot,
        now_local_iso=context.now_local.isoformat(),
        stage1_json=json.dumps(stage1_output, ensure_ascii=False),
        retrieved_examples_json=json.dumps(retrieved_examples or [], ensure_ascii=False),
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
            schema=STAGE2_TRANSMISSION_SCHEMA,
            schema_name=_SCHEMA_NAME,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        logger.error("[stage2_transmission] failed elapsed=%.2fs error=%s", elapsed, exc)
        return StageResult(
            name=STAGE_NAME,
            model=context.model,
            output=None,
            error=str(exc),
        )

    chains_count = len(parsed.get("chains") or [])
    examples_count = len(retrieved_examples or [])
    elapsed = time.perf_counter() - started
    logger.info(
        "[stage2_transmission] ok elapsed=%.2fs chains=%d",
        elapsed,
        chains_count,
    )
    return StageResult(
        name=STAGE_NAME,
        model=context.model,
        output=parsed,
        raw_text=raw_text,
        extras={
            "chains_count": chains_count,
            "retrieved_examples_count": examples_count,
            "elapsed_sec": round(elapsed, 3),
            "usage": usage.to_dict(),
        },
    )


def _write_prompt_snapshot(snapshot_dir: Path, slot: str, system_prompt: str, user_prompt: str) -> None:
    """寫入 write prompt snapshot 對應的資料或結果。"""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / f"market_analysis_{slot}_stage2_transmission_system.txt").write_text(system_prompt, encoding="utf-8")
    (snapshot_dir / f"market_analysis_{slot}_stage2_transmission_user.txt").write_text(user_prompt, encoding="utf-8")
