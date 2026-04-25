"""Stage between stage3_tw_mapping and stage4_synthesis.

Asks the model to argue both sides of the case from the same stage1+2+3
inputs: an explicit ``bull_case`` and ``bear_case`` JSON, each with a thesis,
drivers, counter-risks, and the evidence_ids backing it. This forces the
synthesis stage to weigh a real opposing view rather than rationalising the
median position.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from event_relay.analysis_stages.context import StageContext, StageResult
from event_relay.analysis_stages.llm_json import call_llm_json
from event_relay.analysis_stages.schemas import STAGE_DUAL_VIEW_SCHEMA


logger = logging.getLogger(__name__)
STAGE_NAME = "stage_dual_view"
_SCHEMA_NAME = "market_analysis_stage_dual_view"


def build_prompts(
    *,
    slot: str,
    now_local_iso: str,
    stage1_json: str,
    stage2_json: str,
    stage3_json: str,
) -> tuple[str, str]:
    system_prompt = (
        "You are a debate moderator generating two opposing market views.\n"
        "Output a single JSON object with bull_case and bear_case.\n"
        "Each side must use evidence_ids drawn from stage1.events; do not\n"
        "invent new events. Bull and bear must be substantively different —\n"
        "they may share evidence but must reach opposite directional theses.\n"
        "counter_risks lists what would invalidate that side's thesis."
    )
    user_prompt = (
        f"Slot: {slot}\nNow local: {now_local_iso}\n\n"
        "Construct one bull_case and one bear_case grounded in the inputs.\n"
        "Each thesis is one sentence (Traditional Chinese OK).\n"
        "drivers: 2-4 short bullets, each tied to specific events / chains.\n"
        "counter_risks: 1-3 bullets describing the strongest objection to\n"
        "this side's thesis — the very arguments the opposite side will use.\n"
        "evidence_ids: subset of stage1.events[].id supporting the thesis.\n\n"
        f"Stage1 digest JSON:\n{stage1_json}\n\n"
        f"Stage2 chains JSON:\n{stage2_json}\n\n"
        f"Stage3 mapping JSON:\n{stage3_json}\n"
    )
    return system_prompt, user_prompt


def run(
    *,
    context: StageContext,
    stage1_output: dict[str, Any],
    stage2_output: dict[str, Any],
    stage3_output: dict[str, Any],
    snapshot_dir: Path | None = None,
) -> StageResult:
    logger.info(
        "[stage_dual_view] start slot=%s model=%s sectors=%d",
        context.slot,
        context.model,
        len(stage3_output.get("sector_watch") or []),
    )
    started = time.perf_counter()

    system_prompt, user_prompt = build_prompts(
        slot=context.slot,
        now_local_iso=context.now_local.isoformat(),
        stage1_json=json.dumps(stage1_output, ensure_ascii=False),
        stage2_json=json.dumps(stage2_output, ensure_ascii=False),
        stage3_json=json.dumps(stage3_output, ensure_ascii=False),
    )
    if snapshot_dir is not None:
        _write_prompt_snapshot(snapshot_dir, context.slot, system_prompt, user_prompt)

    try:
        parsed, raw_text = call_llm_json(
            provider=context.provider,
            api_base=context.api_base,
            api_key=context.api_key,
            model=context.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=STAGE_DUAL_VIEW_SCHEMA,
            schema_name=_SCHEMA_NAME,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        logger.error("[stage_dual_view] failed elapsed=%.2fs error=%s", elapsed, exc)
        return StageResult(
            name=STAGE_NAME,
            model=context.model,
            output=None,
            error=str(exc),
        )

    elapsed = time.perf_counter() - started
    bull_drivers = len((parsed.get("bull_case") or {}).get("drivers") or [])
    bear_drivers = len((parsed.get("bear_case") or {}).get("drivers") or [])
    logger.info(
        "[stage_dual_view] ok elapsed=%.2fs bull_drivers=%d bear_drivers=%d",
        elapsed,
        bull_drivers,
        bear_drivers,
    )
    return StageResult(
        name=STAGE_NAME,
        model=context.model,
        output=parsed,
        raw_text=raw_text,
        extras={
            "bull_drivers": bull_drivers,
            "bear_drivers": bear_drivers,
            "elapsed_sec": round(elapsed, 3),
        },
    )


def _write_prompt_snapshot(snapshot_dir: Path, slot: str, system_prompt: str, user_prompt: str) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / f"market_analysis_{slot}_stage_dual_view_system.txt").write_text(system_prompt, encoding="utf-8")
    (snapshot_dir / f"market_analysis_{slot}_stage_dual_view_user.txt").write_text(user_prompt, encoding="utf-8")
