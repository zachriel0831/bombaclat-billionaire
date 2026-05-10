"""Stage 0: deterministic core-tension selector.

This stage runs before LLM normalisation. It reads the packed prompt context,
especially ``market_context:scorecard``, and selects 1-2 daily contradictions
that later stages should answer directly.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from event_relay.analysis_stages.context import StageContext, StageResult
from event_relay.analysis_stages.schemas import STAGE0_THESIS_SELECTOR_SCHEMA, validate_against_schema


logger = logging.getLogger(__name__)
STAGE_NAME = "stage0_thesis_selector"
DIMENSION_LABELS = {
    "breadth_health": "市場廣度",
    "ai_capex_quality": "AI capex 品質",
    "energy_shock_risk": "能源衝擊風險",
    "credit_stress": "信用壓力",
    "liquidity_impulse": "流動性脈衝",
}


def run(
    *,
    context: StageContext,
    events_payload: list[dict[str, Any]],
    market_payload: list[dict[str, Any]],
    snapshot_dir: Path | None = None,
) -> StageResult:
    """Select 1-2 core tensions from deterministic context."""
    try:
        output = select_core_tensions(events_payload=events_payload, market_payload=market_payload)
        validate_against_schema(output, STAGE0_THESIS_SELECTOR_SCHEMA)
    except Exception as exc:  # noqa: BLE001 - keep pipeline recoverable
        logger.warning("[stage0_thesis_selector] failed: %s", exc)
        return StageResult(name=STAGE_NAME, model="deterministic", output=None, error=str(exc))
    if snapshot_dir is not None:
        _write_snapshot(snapshot_dir, context.slot, output)
    logger.info(
        "[stage0_thesis_selector] ok slot=%s tensions=%d",
        context.slot,
        len(output.get("core_tensions") or []),
    )
    return StageResult(
        name=STAGE_NAME,
        model="deterministic",
        output=output,
        extras={"tensions_count": len(output.get("core_tensions") or [])},
    )


def select_core_tensions(
    *,
    events_payload: list[dict[str, Any]],
    market_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pure deterministic selector used by tests and the pipeline."""
    scorecard_event = _find_scorecard_event(events_payload)
    scorecard = _extract_scorecard(scorecard_event)
    dimensions = scorecard.get("dimensions") if isinstance(scorecard.get("dimensions"), dict) else {}
    scored_dimensions = {
        name: int(payload.get("score") or 0)
        for name, payload in dimensions.items()
        if isinstance(payload, dict)
    }
    positive = sorted((item for item in scored_dimensions.items() if item[1] > 0), key=lambda item: item[1], reverse=True)
    negative = sorted((item for item in scored_dimensions.items() if item[1] < 0), key=lambda item: item[1])
    tensions: list[dict[str, Any]] = []
    notes: list[str] = []
    scorecard_evidence_id = scorecard_event.get("id") if isinstance(scorecard_event, dict) else None

    if positive and negative:
        bull_name, bull_score = positive[0]
        bear_name, bear_score = negative[0]
        tensions.append(
            _tension(
                index=1,
                thesis=f"{_label(bull_name)}支撐 risk-on，但{_label(bear_name)}形成反向壓力",
                bullish_force=f"{_label(bull_name)} score {bull_score:+d}",
                bearish_force=f"{_label(bear_name)} score {bear_score:+d}",
                why_now="scorecard 同時出現正負維度，今日分析必須先判斷哪一邊是主導變數。",
                evidence_ids=[scorecard_evidence_id],
                dimensions=[bull_name, bear_name],
            )
        )
        notes.append("selected from opposing scorecard dimensions")

    if scored_dimensions.get("ai_capex_quality", 0) > 0 and scored_dimensions.get("breadth_health", 0) < 0:
        tensions.append(
            _tension(
                index=len(tensions) + 1,
                thesis="AI capex 基本面仍強，但市場廣度收斂使漲勢品質打折",
                bullish_force=f"AI capex score {scored_dimensions['ai_capex_quality']:+d}",
                bearish_force=f"breadth score {scored_dimensions['breadth_health']:+d}",
                why_now="這是 AI 主線能否延續到台股供應鏈的核心矛盾。",
                evidence_ids=[scorecard_evidence_id],
                dimensions=["ai_capex_quality", "breadth_health"],
            )
        )

    if scored_dimensions.get("liquidity_impulse", 0) > 0 and scored_dimensions.get("energy_shock_risk", 0) < 0:
        tensions.append(
            _tension(
                index=len(tensions) + 1,
                thesis="流動性仍支撐風險資產，但油價/能源衝擊可能重新推高通膨折現率",
                bullish_force=f"liquidity score {scored_dimensions['liquidity_impulse']:+d}",
                bearish_force=f"energy score {scored_dimensions['energy_shock_risk']:+d}",
                why_now="能源價格若失控，會直接干擾利率、估值與科技股風險偏好。",
                evidence_ids=[scorecard_evidence_id],
                dimensions=["liquidity_impulse", "energy_shock_risk"],
            )
        )

    high_events = _top_high_importance_events(events_payload)
    if not tensions and high_events:
        top = high_events[0]
        tensions.append(
            _tension(
                index=1,
                thesis=f"{top.get('title') or top.get('source')} 是今日主要敘事，但需要市場/官方資料確認",
                bullish_force="高重要度事件可能改變短線風險偏好",
                bearish_force="若缺少 scorecard 或官方資料支撐，容易只是新聞噪音",
                why_now="缺少明確 scorecard 矛盾時，先用最高重要度事件作為待驗證主軸。",
                evidence_ids=[top.get("id")],
                dimensions=[],
            )
        )
        notes.append("fallback to highest-importance event")

    if not tensions:
        tensions.append(
            _tension(
                index=1,
                thesis="今日沒有單一明確矛盾，分析應以資料缺口和確認條件為主",
                bullish_force="尚未出現足夠負面證據",
                bearish_force="也缺少足夠正面確認",
                why_now=f"packed events={len(events_payload)}, market rows={len(market_payload)}",
                evidence_ids=[],
                dimensions=[],
            )
        )
        notes.append("fallback to data-gap thesis")

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, ...] | str] = set()
    for item in tensions:
        dimensions_key = tuple(sorted(str(value) for value in (item.get("scorecard_dimensions") or []) if value))
        key: tuple[str, ...] | str = dimensions_key or str(item.get("thesis") or "")
        if key in seen:
            continue
        seen.add(key)
        item["id"] = f"thesis-{len(deduped) + 1}"
        deduped.append(item)
        if len(deduped) >= 2:
            break

    return {
        "core_tensions": deduped,
        "selection_notes": notes or ["selected deterministically from packed context"],
    }


def _find_scorecard_event(events_payload: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in events_payload:
        if str(event.get("source") or "") == "market_context:scorecard":
            return event
    return None


def _extract_scorecard(event: dict[str, Any] | None) -> dict[str, Any]:
    raw = event.get("raw") if isinstance(event, dict) and isinstance(event.get("raw"), dict) else {}
    scorecard = raw.get("scorecard") if isinstance(raw, dict) else None
    return scorecard if isinstance(scorecard, dict) else {}


def _top_high_importance_events(events_payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def importance(event: dict[str, Any]) -> float:
        annotation = event.get("annotation") if isinstance(event.get("annotation"), dict) else {}
        try:
            return float(annotation.get("importance") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return sorted(events_payload, key=importance, reverse=True)[:3]


def _label(name: str) -> str:
    return DIMENSION_LABELS.get(name, name)


def _tension(
    *,
    index: int,
    thesis: str,
    bullish_force: str,
    bearish_force: str,
    why_now: str,
    evidence_ids: list[Any],
    dimensions: list[str],
) -> dict[str, Any]:
    return {
        "id": f"thesis-{index}",
        "thesis": thesis,
        "bullish_force": bullish_force,
        "bearish_force": bearish_force,
        "why_now": why_now,
        "evidence_ids": [item for item in evidence_ids if item is not None],
        "scorecard_dimensions": dimensions,
    }


def _write_snapshot(snapshot_dir: Path, slot: str, output: dict[str, Any]) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / f"market_analysis_{slot}_stage0_thesis_selector.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
