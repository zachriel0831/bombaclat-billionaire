"""Stage 4: Traditional-Chinese narrative + structured output.

Consumes the outputs of stages 1-3 (and optional dual_view + critic) and
produces (a) the final 220-700 character Chinese report written into
``t_market_analyses.summary_text`` and (b) a schema-validated JSON object
stored in ``t_market_analyses.structured_json``.

The summary_text always ends with two regex-extractable lines:
    信心等級：<low|medium|high>
    主要反方觀點：<one sentence>
so downstream consumers can pick those out without LLM reparsing.

Primary path: structured-output call (OpenAI ``json_schema`` / Anthropic
``tool input_schema``) returning both narrative + structured fields. If schema
validation fails after retry, fall back to a free-text call so summary_text is
still produced — ``structured`` is left ``None`` and the failure mode is
recorded in ``extras``.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from event_relay.analysis_stages.context import StageContext, StageResult
from event_relay.analysis_stages.llm_json import call_llm_json
from event_relay.analysis_stages.schemas import (
    STAGE4_SYNTHESIS_SCHEMA,
    SchemaValidationError,
)
from event_relay.weekly_summary import _call_llm


logger = logging.getLogger(__name__)
STAGE_NAME = "stage4_synthesis"
_SCHEMA_NAME = "market_analysis_stage4_synthesis"

CONFIDENCE_LINE_PREFIX = "信心等級："
COUNTERPOINT_LINE_PREFIX = "主要反方觀點："
CONFIDENCE_LINE_RE = re.compile(r"^信心等級：(low|medium|high)\s*$", re.MULTILINE)
COUNTERPOINT_LINE_RE = re.compile(r"^主要反方觀點：(.+)$", re.MULTILINE)

_VALID_CONFIDENCE = {"low", "medium", "high"}

_SLOT_SECTIONS: dict[str, tuple[str, list[str]]] = {
    "us_close": (
        "Focus on what the U.S. close implies for Taiwan's next session.",
        ["美股收盤重點", "對台股的可能影響", "需要留意的族群或事件", "風險與資料缺口"],
    ),
    "pre_tw_open": (
        "Focus on Taiwan pre-open positioning and what matters before 09:00.",
        ["美股收盤重點", "對台股的可能影響", "需要留意的族群或事件", "風險與資料缺口"],
    ),
    "tw_close": (
        "Taiwan close review: summarise today's close and set up tomorrow.",
        ["台股收盤復盤", "法人/期權/融資券", "類股輪動", "隔日觀察與風險"],
    ),
}


def _structured_instructions() -> str:
    return (
        "Produce BOTH a Traditional-Chinese narrative AND a structured JSON view\n"
        "of the same analysis.\n"
        "  - summary_text: 220-700 characters of Traditional Chinese plain text\n"
        "    that follows the section list below. End summary_text with two\n"
        "    final lines on their own:\n"
        "        信心等級：<low|medium|high>\n"
        "        主要反方觀點：<one sentence stating the strongest opposing view>\n"
        "  - headline: a single Traditional-Chinese sentence (<=40 chars).\n"
        "  - sentiment: bullish / bearish / neutral (global risk-on/risk-off view).\n"
        "  - confidence: low / medium / high. Match the value used inside\n"
        "    summary_text. Use low when stage1 events are sparse, critic flags\n"
        "    multiple high-severity issues, or risks dominate; use high only\n"
        "    when multiple independent chains agree and critic is clean.\n"
        "  - key_drivers: short bullets naming the top 2-4 events / forces.\n"
        "  - tw_sector_watch / stock_watch: copy the sector / ticker buckets\n"
        "    from stage3, restated tersely. Use stage3.direction values.\n"
        "  - risks / data_gaps: copy from stage3, dedupe.\n"
        "Do not introduce new facts beyond what stages 1-3 produced. Use the\n"
        "bull_case / bear_case / critic input to balance tone — if critic\n"
        "flagged overconfidence, soften certainty in summary_text."
    )


def build_prompts(
    *,
    slot: str,
    now_local_iso: str,
    stage1_json: str,
    stage2_json: str,
    stage3_json: str,
    macro_skill: str,
    line_skill: str,
    structured: bool,
    dual_view_json: str | None = None,
    critic_json: str | None = None,
) -> tuple[str, str]:
    focus, sections = _SLOT_SECTIONS.get(slot, _SLOT_SECTIONS["pre_tw_open"])
    numbered_sections = "\n".join(f"{idx + 1}) {title}" for idx, title in enumerate(sections))

    system_prompt = (
        "You are a Taiwan market morning strategist writing in Traditional Chinese.\n"
        "Use plain text only. Be concise, concrete, and avoid fabricating facts.\n"
        "You are the final stage of a multi-stage pipeline. Do not introduce new\n"
        "facts: restate what earlier stages produced, keep evidence-backed claims,\n"
        "and clearly mark items coming from risks / data_gaps.\n"
        "Treat the dual-view bull/bear and the critic's findings as constraints:\n"
        "if critic flags overconfidence, lower the confidence; if dual-view bear\n"
        "is strong, surface its top point as 主要反方觀點.\n\n"
        "[Macro Skill]\n"
        f"{macro_skill}\n\n"
        "[Mobile Chat Format Skill]\n"
        f"{line_skill}\n"
    )
    user_lines = [
        f"Generate one {slot} market analysis in Traditional Chinese.",
        focus,
        "Required sections (used inside summary_text):",
        numbered_sections,
        "Total length 220-700 Chinese characters.",
        f"Now local time: {now_local_iso}",
        "",
        "Use only claims supported by the stage outputs below. If a section",
        "has no supporting material, state the data gap rather than inventing.",
        "",
        "summary_text MUST end with two lines, each on its own line:",
        f"    {CONFIDENCE_LINE_PREFIX}<low|medium|high>",
        f"    {COUNTERPOINT_LINE_PREFIX}<one sentence>",
    ]
    if structured:
        user_lines.extend(["", _structured_instructions()])
    user_lines.extend(
        [
            "",
            f"Stage1 digest JSON:\n{stage1_json}",
            "",
            f"Stage2 chains JSON:\n{stage2_json}",
            "",
            f"Stage3 mapping JSON:\n{stage3_json}",
        ]
    )
    if dual_view_json is not None:
        user_lines.extend(["", f"Dual-view JSON (bull_case / bear_case):\n{dual_view_json}"])
    if critic_json is not None:
        user_lines.extend(["", f"Critic JSON (issues, suggestions, top_counterpoint):\n{critic_json}"])
    elif dual_view_json is not None:
        user_lines.extend(
            [
                "",
                "Critic stage was skipped — derive top_counterpoint from bear_case.thesis.",
            ]
        )
    return system_prompt, "\n".join(user_lines)


def run(
    *,
    context: StageContext,
    stage1_output: dict[str, Any],
    stage2_output: dict[str, Any],
    stage3_output: dict[str, Any],
    macro_skill: str,
    line_skill: str,
    snapshot_dir: Path | None = None,
    dual_view_output: dict[str, Any] | None = None,
    critic_output: dict[str, Any] | None = None,
) -> StageResult:
    logger.info(
        "[stage4_synthesis] start slot=%s model=%s sectors=%d stocks=%d dual=%s critic=%s",
        context.slot,
        context.model,
        len(stage3_output.get("sector_watch") or []),
        len(stage3_output.get("stock_watch") or []),
        dual_view_output is not None,
        critic_output is not None,
    )
    started = time.perf_counter()

    stage1_json = json.dumps(stage1_output, ensure_ascii=False)
    stage2_json = json.dumps(stage2_output, ensure_ascii=False)
    stage3_json = json.dumps(stage3_output, ensure_ascii=False)
    dual_view_json = json.dumps(dual_view_output, ensure_ascii=False) if dual_view_output else None
    critic_json = json.dumps(critic_output, ensure_ascii=False) if critic_output else None

    structured_system, structured_user = build_prompts(
        slot=context.slot,
        now_local_iso=context.now_local.isoformat(),
        stage1_json=stage1_json,
        stage2_json=stage2_json,
        stage3_json=stage3_json,
        macro_skill=macro_skill,
        line_skill=line_skill,
        structured=True,
        dual_view_json=dual_view_json,
        critic_json=critic_json,
    )
    if snapshot_dir is not None:
        _write_prompt_snapshot(snapshot_dir, context.slot, structured_system, structured_user)

    parsed, summary_text, structured_error, fallback_error = _resolve_summary(
        context=context,
        structured_system=structured_system,
        structured_user=structured_user,
        slot=context.slot,
        stage1_json=stage1_json,
        stage2_json=stage2_json,
        stage3_json=stage3_json,
        macro_skill=macro_skill,
        line_skill=line_skill,
        dual_view_json=dual_view_json,
        critic_json=critic_json,
    )
    if fallback_error is not None:
        elapsed = time.perf_counter() - started
        logger.error("[stage4_synthesis] failed elapsed=%.2fs error=%s", elapsed, fallback_error)
        return StageResult(
            name=STAGE_NAME,
            model=context.model,
            output=None,
            error=fallback_error,
            extras={"structured_error": structured_error or "unknown"},
        )

    summary_text = ensure_confidence_footer(
        summary_text=summary_text,
        structured=parsed,
        critic=critic_output,
        dual_view=dual_view_output,
    )

    elapsed = time.perf_counter() - started
    structured_payload = parsed if parsed is not None else None
    extras: dict[str, Any] = {
        "chars": len(summary_text),
        "elapsed_sec": round(elapsed, 3),
        "has_structured": structured_payload is not None,
        "has_dual_view": dual_view_output is not None,
        "has_critic": critic_output is not None,
    }
    if structured_error and structured_payload is None:
        extras["structured_fallback"] = structured_error[:200]
    logger.info(
        "[stage4_synthesis] ok elapsed=%.2fs chars=%d has_structured=%s",
        elapsed,
        len(summary_text),
        structured_payload is not None,
    )
    return StageResult(
        name=STAGE_NAME,
        model=context.model,
        output={"summary_text": summary_text, "structured": structured_payload},
        raw_text=summary_text,
        extras=extras,
    )


def ensure_confidence_footer(
    *,
    summary_text: str,
    structured: dict[str, Any] | None,
    critic: dict[str, Any] | None,
    dual_view: dict[str, Any] | None,
) -> str:
    """Guarantee summary_text ends with regex-extractable confidence + counterpoint lines.

    If the model already emitted both lines, leave them in place. Otherwise pick
    the best available source: structured.confidence > critic.confidence_recommendation
    > 'medium'; critic.top_counterpoint > bear_case.thesis > generic placeholder.
    """
    text = (summary_text or "").strip()
    has_confidence = CONFIDENCE_LINE_RE.search(text) is not None
    has_counterpoint = COUNTERPOINT_LINE_RE.search(text) is not None
    if has_confidence and has_counterpoint:
        return text

    confidence = _resolve_confidence(structured, critic)
    counterpoint = _resolve_counterpoint(critic, dual_view)

    appended_lines: list[str] = []
    if not has_confidence:
        appended_lines.append(f"{CONFIDENCE_LINE_PREFIX}{confidence}")
    if not has_counterpoint:
        appended_lines.append(f"{COUNTERPOINT_LINE_PREFIX}{counterpoint}")
    suffix = "\n".join(appended_lines)
    return f"{text}\n{suffix}" if text else suffix


def _resolve_confidence(structured: dict[str, Any] | None, critic: dict[str, Any] | None) -> str:
    if isinstance(structured, dict):
        value = str(structured.get("confidence") or "").strip().lower()
        if value in _VALID_CONFIDENCE:
            return value
    if isinstance(critic, dict):
        value = str(critic.get("confidence_recommendation") or "").strip().lower()
        if value in _VALID_CONFIDENCE:
            return value
    return "medium"


def _resolve_counterpoint(critic: dict[str, Any] | None, dual_view: dict[str, Any] | None) -> str:
    if isinstance(critic, dict):
        value = str(critic.get("top_counterpoint") or "").strip()
        if value:
            return value
    if isinstance(dual_view, dict):
        bear = dual_view.get("bear_case") or {}
        if isinstance(bear, dict):
            thesis = str(bear.get("thesis") or "").strip()
            if thesis:
                return thesis
    return "資料不足，待後續事件確認"


def _resolve_summary(
    *,
    context: StageContext,
    structured_system: str,
    structured_user: str,
    slot: str,
    stage1_json: str,
    stage2_json: str,
    stage3_json: str,
    macro_skill: str,
    line_skill: str,
    dual_view_json: str | None,
    critic_json: str | None,
) -> tuple[dict[str, Any] | None, str, str | None, str | None]:
    """Run structured call, then fall back to text. Returns (parsed, summary, structured_err, fallback_err)."""
    parsed, structured_error = _try_structured_call(
        context=context,
        system_prompt=structured_system,
        user_prompt=structured_user,
    )
    summary_text = _normalize((parsed or {}).get("summary_text") or "") if parsed else ""
    if parsed is not None and not summary_text:
        structured_error = "structured_summary_text_empty"
        parsed = None

    if parsed is not None:
        return parsed, summary_text, structured_error, None

    try:
        summary_text = _run_text_fallback(
            context=context,
            slot=slot,
            stage1_json=stage1_json,
            stage2_json=stage2_json,
            stage3_json=stage3_json,
            macro_skill=macro_skill,
            line_skill=line_skill,
            dual_view_json=dual_view_json,
            critic_json=critic_json,
        )
    except Exception as exc:  # noqa: BLE001
        return None, "", structured_error, str(exc)
    return None, summary_text, structured_error, None


def _try_structured_call(
    *,
    context: StageContext,
    system_prompt: str,
    user_prompt: str,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed, _raw_text = call_llm_json(
            provider=context.provider,
            api_base=context.api_base,
            api_key=context.api_key,
            model=context.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=STAGE4_SYNTHESIS_SCHEMA,
            schema_name=_SCHEMA_NAME,
        )
        return parsed, None
    except SchemaValidationError as exc:
        logger.warning("[stage4_synthesis] structured output failed schema; falling back to text. %s", exc)
        return None, f"schema_failed: {exc}"
    except Exception as exc:  # noqa: BLE001 - fall back to legacy text call
        logger.warning("[stage4_synthesis] structured call failed (%s); falling back to text.", exc)
        return None, f"call_failed: {exc}"


def _run_text_fallback(
    *,
    context: StageContext,
    slot: str,
    stage1_json: str,
    stage2_json: str,
    stage3_json: str,
    macro_skill: str,
    line_skill: str,
    dual_view_json: str | None,
    critic_json: str | None,
) -> str:
    text_system, text_user = build_prompts(
        slot=slot,
        now_local_iso=context.now_local.isoformat(),
        stage1_json=stage1_json,
        stage2_json=stage2_json,
        stage3_json=stage3_json,
        macro_skill=macro_skill,
        line_skill=line_skill,
        structured=False,
        dual_view_json=dual_view_json,
        critic_json=critic_json,
    )
    raw_text = _call_llm(
        provider=context.provider,
        api_base=context.api_base,
        api_key=context.api_key,
        model=context.model,
        system_prompt=text_system,
        user_prompt=text_user,
    )
    return _normalize(raw_text)


def _normalize(text: str) -> str:
    return (text or "").strip()


def _write_prompt_snapshot(snapshot_dir: Path, slot: str, system_prompt: str, user_prompt: str) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / f"market_analysis_{slot}_stage4_synthesis_system.txt").write_text(system_prompt, encoding="utf-8")
    (snapshot_dir / f"market_analysis_{slot}_stage4_synthesis_user.txt").write_text(user_prompt, encoding="utf-8")
