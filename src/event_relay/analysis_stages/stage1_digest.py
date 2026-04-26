"""Stage 1: event digest.

Consumes the raw events / market snapshot payloads that ``market_analysis``
already builds and asks the model for a normalised view:

* classify each event,
* extract entities,
* score importance (0-1),
* produce a one-line factual summary.

No inference, no chains, no Taiwan mapping. Output conforms to
``STAGE1_DIGEST_SCHEMA``.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from event_relay.analysis_stages.context import StageContext, StageResult
from event_relay.analysis_stages.llm_json import call_llm_json
from event_relay.analysis_stages.schemas import STAGE1_DIGEST_SCHEMA


logger = logging.getLogger(__name__)
STAGE_NAME = "stage1_digest"
_SCHEMA_NAME = "market_analysis_stage1_digest"


def build_prompts(
    *,
    slot: str,
    now_local_iso: str,
    events_json: str,
    market_snapshot_json: str,
) -> tuple[str, str]:
    """建立 build prompts 對應的資料或結果。"""
    system_prompt = (
        "You are a market-data normaliser. "
        "Your sole job is to classify events, extract named entities, score "
        "importance between 0 and 1, and produce a concise one-line fact for "
        "each event. Do not infer market impact. Do not mention Taiwan unless "
        "the event explicitly does so. Output must be a single JSON object "
        "matching the schema; no prose, no markdown."
    )
    user_prompt = (
        f"Slot: {slot}\n"
        f"Now local: {now_local_iso}\n\n"
        "Classify each event into one of: rate_decision, earnings, geopolitics, "
        "supply_chain, regulation, macro_release, corporate_action, market_move, other.\n"
        "importance heuristic: 0.9+ for Fed / major central bank / war escalation / "
        "megacap earnings guide cut; 0.6-0.8 for other policy / sizable earnings / "
        "macro release; 0.3-0.5 for routine corporate news; below 0.3 for color.\n"
        "sentiment is from a global risk-on/risk-off perspective.\n"
        "one_line_fact must not speculate; state what happened.\n"
        "Copy each event's id verbatim from the input.\n\n"
        "Each input event carries an `annotation` block produced by a rule-based\n"
        "pre-processor (category / importance / sentiment / entities). Treat it\n"
        "as a strong prior: reuse its category and entities unless the title or\n"
        "summary plainly contradicts them; you may override importance or\n"
        "sentiment when the text gives clearer evidence. Never invent entities\n"
        "that are not in the title, summary, or annotation.\n\n"
        "Also populate market_snapshot with whatever US close / bond / FX / TW "
        "session data is visible in the inputs; leave sub-objects empty if absent.\n\n"
        f"Events JSON:\n{events_json}\n\n"
        f"Market snapshot JSON:\n{market_snapshot_json}\n"
    )
    return system_prompt, user_prompt


def run(
    *,
    context: StageContext,
    events_payload: list[dict[str, Any]],
    market_payload: list[dict[str, Any]],
    snapshot_dir: Path | None = None,
) -> StageResult:
    """執行 run 的主要流程。"""
    logger.info(
        "[stage1_digest] start slot=%s model=%s events_in=%d market_rows_in=%d",
        context.slot,
        context.model,
        len(events_payload),
        len(market_payload),
    )
    started = time.perf_counter()

    system_prompt, user_prompt = build_prompts(
        slot=context.slot,
        now_local_iso=context.now_local.isoformat(),
        events_json=json.dumps(events_payload, ensure_ascii=False),
        market_snapshot_json=json.dumps(market_payload, ensure_ascii=False),
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
            schema=STAGE1_DIGEST_SCHEMA,
            schema_name=_SCHEMA_NAME,
        )
    except Exception as exc:  # noqa: BLE001 - propagated as StageResult.error
        elapsed = time.perf_counter() - started
        logger.error("[stage1_digest] failed elapsed=%.2fs error=%s", elapsed, exc)
        return StageResult(
            name=STAGE_NAME,
            model=context.model,
            output=None,
            error=str(exc),
        )

    event_count = len(parsed.get("events") or [])
    elapsed = time.perf_counter() - started
    logger.info(
        "[stage1_digest] ok elapsed=%.2fs events_out=%d",
        elapsed,
        event_count,
    )
    return StageResult(
        name=STAGE_NAME,
        model=context.model,
        output=parsed,
        raw_text=raw_text,
        extras={"event_count": event_count, "elapsed_sec": round(elapsed, 3)},
    )


def _write_prompt_snapshot(snapshot_dir: Path, slot: str, system_prompt: str, user_prompt: str) -> None:
    """寫入 write prompt snapshot 對應的資料或結果。"""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / f"market_analysis_{slot}_stage1_digest_system.txt").write_text(system_prompt, encoding="utf-8")
    (snapshot_dir / f"market_analysis_{slot}_stage1_digest_user.txt").write_text(user_prompt, encoding="utf-8")
