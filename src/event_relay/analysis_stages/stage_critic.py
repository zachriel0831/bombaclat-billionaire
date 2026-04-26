"""Risk-officer critic stage.

A short stage that adopts a critical persona and grades the analysis pipeline
output before stage4 commits to a narrative. It looks for logical jumps,
unsupported claims, overconfidence, and ambiguous wording. The result is fed
into stage4 so the final summary can include a confidence level and the top
counterpoint.

Failure mode: critic errors do NOT abort the pipeline. The orchestrator marks
``raw_json.critic_skipped = true`` and stage4 proceeds without critic input.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from event_relay.analysis_stages.context import StageContext, StageResult
from event_relay.analysis_stages.llm_json import call_llm_json
from event_relay.analysis_stages.schemas import STAGE_CRITIC_SCHEMA


logger = logging.getLogger(__name__)
STAGE_NAME = "stage_critic"
_SCHEMA_NAME = "market_analysis_stage_critic"


def build_prompts(
    *,
    slot: str,
    now_local_iso: str,
    stage1_json: str,
    stage3_json: str,
    dual_view_json: str,
) -> tuple[str, str]:
    """建立 build prompts 對應的資料或結果。"""
    system_prompt = (
        "You are a senior risk officer reviewing a junior analyst's draft.\n"
        "Your job is NOT to write the report — it is to find weaknesses.\n"
        "Look for: logical_jump (chain of reasoning skips a step),\n"
        "evidence_missing (claim has no event support), overconfidence\n"
        "(strong claim but weak evidence), factual_error (contradicts the\n"
        "stage1 events), ambiguous_claim (vague language).\n"
        "Be strict. If the input is thin, recommend low confidence."
    )
    user_prompt = (
        f"Slot: {slot}\nNow local: {now_local_iso}\n\n"
        "List up to 5 issues with type / description / severity.\n"
        "Provide 1-3 actionable suggestions for stage4.\n"
        "Pick the single strongest counterpoint a sceptic should raise.\n"
        "Recommend confidence_recommendation (low / medium / high) based on:\n"
        "  high: multiple independent chains agree, evidence rich\n"
        "  medium: one main chain supported, minor gaps\n"
        "  low: thin events, contradictions, or many overconfidence issues\n\n"
        f"Stage1 digest JSON:\n{stage1_json}\n\n"
        f"Stage3 mapping JSON:\n{stage3_json}\n\n"
        f"Dual view JSON:\n{dual_view_json}\n"
    )
    return system_prompt, user_prompt


def run(
    *,
    context: StageContext,
    stage1_output: dict[str, Any],
    stage3_output: dict[str, Any],
    dual_view_output: dict[str, Any],
    snapshot_dir: Path | None = None,
) -> StageResult:
    """執行 run 的主要流程。"""
    logger.info("[stage_critic] start slot=%s model=%s", context.slot, context.model)
    started = time.perf_counter()

    system_prompt, user_prompt = build_prompts(
        slot=context.slot,
        now_local_iso=context.now_local.isoformat(),
        stage1_json=json.dumps(stage1_output, ensure_ascii=False),
        stage3_json=json.dumps(stage3_output, ensure_ascii=False),
        dual_view_json=json.dumps(dual_view_output, ensure_ascii=False),
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
            schema=STAGE_CRITIC_SCHEMA,
            schema_name=_SCHEMA_NAME,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        logger.warning("[stage_critic] failed elapsed=%.2fs error=%s; pipeline will mark critic_skipped", elapsed, exc)
        return StageResult(
            name=STAGE_NAME,
            model=context.model,
            output=None,
            error=str(exc),
        )

    elapsed = time.perf_counter() - started
    issues = parsed.get("issues") or []
    logger.info(
        "[stage_critic] ok elapsed=%.2fs issues=%d confidence=%s",
        elapsed,
        len(issues),
        parsed.get("confidence_recommendation"),
    )
    return StageResult(
        name=STAGE_NAME,
        model=context.model,
        output=parsed,
        raw_text=raw_text,
        extras={
            "issues_count": len(issues),
            "confidence_recommendation": parsed.get("confidence_recommendation"),
            "elapsed_sec": round(elapsed, 3),
        },
    )


def _write_prompt_snapshot(snapshot_dir: Path, slot: str, system_prompt: str, user_prompt: str) -> None:
    """寫入 write prompt snapshot 對應的資料或結果。"""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / f"market_analysis_{slot}_stage_critic_system.txt").write_text(system_prompt, encoding="utf-8")
    (snapshot_dir / f"market_analysis_{slot}_stage_critic_user.txt").write_text(user_prompt, encoding="utf-8")
