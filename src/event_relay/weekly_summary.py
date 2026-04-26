"""Weekly market summary generator (Sunday 23:00 Asia/Taipei).

Aggregates the past week of relay events + market analyses, calls the LLM
(Anthropic / OpenAI) to produce a Traditional-Chinese summary, persists
to ``t_market_analyses`` with ``slot=weekly_tw_preopen``. Hosts shared
LLM helpers reused by ``market_analysis``."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from event_relay.config import load_settings
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


logger = logging.getLogger(__name__)
WEEKLY_ANALYSIS_SLOT = "weekly_tw_preopen"
WEEKLY_PROMPT_VERSION = "weekly-summary-v1"


@dataclass(frozen=True)
class WeeklySummaryConfig:
    """封裝 Weekly Summary Config 相關資料與行為。"""
    env_file: str
    model: str
    api_base: str
    api_key: str | None
    api_key_file: str
    skill_macro_path: str
    skill_line_format_path: str
    lookback_days: int
    max_events: int
    weekday: int
    hour: int
    minute: int
    window_minutes: int
    state_file: str
    force: bool
    provider: str = "openai"


def _build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(description="Generate weekly macro summary and store it")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--force", action="store_true", help="Bypass schedule gate and run immediately")
    parser.add_argument("--dry-run", action="store_true", help="Deprecated compatibility flag; weekly summary never pushes")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _load_secret_from_dpapi_file(path: str) -> str | None:
    """載入 load secret from dpapi file 對應的資料或結果。"""
    file_path = Path(path)
    if not file_path.exists():
        return None
    if os.name != "nt":
        return None

    ps_path = str(file_path.resolve()).replace("'", "''")
    command = (
        "$enc = Get-Content -Raw -LiteralPath '{path}'; "
        "$secure = ConvertTo-SecureString $enc; "
        "[System.Net.NetworkCredential]::new('', $secure).Password"
    ).format(path=ps_path)

    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _resolve_anthropic_settings() -> tuple[str, str, str, str, str | None]:
    """解析並決定 resolve anthropic settings 對應的資料或結果。"""
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


def _resolve_openai_settings(default_model: str) -> tuple[str, str, str, str, str | None]:
    """解析並決定 resolve openai settings 對應的資料或結果。"""
    api_key_file = (os.getenv("WEEKLY_SUMMARY_OPENAI_API_KEY_FILE") or ".secrets/openai_api_key.dpapi").strip()
    direct_key = (os.getenv("WEEKLY_SUMMARY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    api_key = direct_key or (_load_secret_from_dpapi_file(api_key_file) or "")
    return (
        "openai",
        (os.getenv("WEEKLY_SUMMARY_MODEL") or default_model).strip(),
        (os.getenv("WEEKLY_SUMMARY_OPENAI_API_BASE") or "https://api.openai.com/v1").strip(),
        api_key_file,
        api_key or None,
    )


def _resolve_llm_settings(default_openai_model: str) -> tuple[str, str, str, str, str | None]:
    """Resolve (provider, model, api_base, api_key_file, api_key) based on LLM_PROVIDER."""
    provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    if provider == "anthropic":
        return _resolve_anthropic_settings()
    return _resolve_openai_settings(default_openai_model)


def _load_weekly_config(args: argparse.Namespace) -> WeeklySummaryConfig:
    """載入 load weekly config 對應的資料或結果。"""
    provider, model, api_base, api_key_file, api_key = _resolve_llm_settings(default_openai_model="gpt-5")

    return WeeklySummaryConfig(
        env_file=args.env_file,
        model=model,
        api_base=api_base,
        api_key=api_key,
        api_key_file=api_key_file,
        skill_macro_path=(
            os.getenv("WEEKLY_SUMMARY_MACRO_SKILL_PATH", "skills/macro-weekly-summary-skill/SKILLS.md")
            or "skills/macro-weekly-summary-skill/SKILLS.md"
        ).strip(),
        skill_line_format_path=(
            os.getenv("WEEKLY_SUMMARY_LINE_SKILL_PATH", "skills/line-brief-format-skill/line-weekly-brief.md")
            or "skills/line-brief-format-skill/line-weekly-brief.md"
        ).strip(),
        lookback_days=max(1, int(os.getenv("WEEKLY_SUMMARY_LOOKBACK_DAYS", "7"))),
        max_events=max(10, int(os.getenv("WEEKLY_SUMMARY_MAX_EVENTS", "120"))),
        weekday=max(0, min(6, int(os.getenv("WEEKLY_SUMMARY_WEEKDAY", "5")))),
        hour=max(0, min(23, int(os.getenv("WEEKLY_SUMMARY_HOUR", "23")))),
        minute=max(0, min(59, int(os.getenv("WEEKLY_SUMMARY_MINUTE", "0")))),
        window_minutes=max(1, int(os.getenv("WEEKLY_SUMMARY_WINDOW_MINUTES", "20"))),
        state_file=(
            os.getenv("WEEKLY_SUMMARY_STATE_FILE", "runtime/state/weekly-summary-last-week.txt")
            or "runtime/state/weekly-summary-last-week.txt"
        ).strip(),
        force=bool(args.force),
        provider=provider,
    )


def _week_key(now_local: datetime) -> str:
    """執行 week key 的主要流程。"""
    iso_year, iso_week, _ = now_local.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _should_run_now(config: WeeklySummaryConfig, now_local: datetime) -> bool:
    """執行 should run now 的主要流程。"""
    if config.force:
        return True
    if now_local.weekday() != config.weekday:
        return False
    # weekly summary 用時間窗而不是精準分鐘觸發，讓 Task Scheduler 晚幾分鐘啟動也能補跑。
    target = now_local.replace(hour=config.hour, minute=config.minute, second=0, microsecond=0)
    delta_minutes = abs((now_local - target).total_seconds()) / 60.0
    return delta_minutes <= float(config.window_minutes)


def _already_sent_this_week(state_file: Path, key: str) -> bool:
    """執行 already sent this week 的主要流程。"""
    if not state_file.exists():
        return False
    saved = state_file.read_text(encoding="utf-8", errors="ignore").strip()
    return saved == key


def _mark_sent_this_week(state_file: Path, key: str) -> None:
    """執行 mark sent this week 的主要流程。"""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(key, encoding="utf-8")


def _load_text(path: str) -> str:
    """載入 load text 對應的資料或結果。"""
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore").strip()


def _compile_prompts(config: WeeklySummaryConfig) -> tuple[str, str]:
    """執行 compile prompts 的主要流程。"""
    macro_skill = _load_text(config.skill_macro_path)
    line_format_skill = _load_text(config.skill_line_format_path)

    system_prompt = (
        "You are a senior macro editor. Produce one weekly mobile-chat brief in Traditional Chinese.\n"
        "Use plain text only. Do not output code blocks. Do not fabricate facts.\n"
        "Focus on international politics, macro/finance, and technology.\n\n"
        "Evidence policy:\n"
        "- Treat t_relay_events and stored market_context rows as the primary local evidence.\n"
        "- Do not treat absence from local events as proof that nothing happened.\n"
        "- If web search is available, verify latest policy, price, war, macro, and earnings facts before using them.\n"
        "- If web search is unavailable or evidence is insufficient, explicitly label the data gap and lower confidence.\n"
        "- Distinguish local-event facts, externally verified facts, and inference.\n\n"
        "[Macro Skill]\n"
        f"{macro_skill}\n\n"
        "[Mobile Chat Format Skill]\n"
        f"{line_format_skill}\n"
    )

    reusable_prompt = (
        "Please generate one weekly political/economic summary in Traditional Chinese for downstream mobile chat delivery.\n"
        "The Events JSON is the local event-store context, not a complete list of everything that happened.\n"
        "Use web search when available to verify missing or current facts, and state any remaining gaps.\n"
        "Required sections:\n"
        "1) 本週重點\n"
        "2) 國際政治面\n"
        "3) 財經科技面\n"
        "4) 下週觀察\n"
        "5) 風險提醒\n"
        "Each section should be 1-3 sentences. Total length 320-800 Chinese characters.\n\n"
        "Time range: {week_range}\n"
        "Events JSON:\n{events_json}\n"
    )
    return system_prompt, reusable_prompt


def _write_prompt_snapshots(system_prompt: str, reusable_prompt: str) -> None:
    """寫入 write prompt snapshots 對應的資料或結果。"""
    out_dir = Path("runtime/prompts")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "weekly_summary_system_prompt.txt").write_text(system_prompt, encoding="utf-8")
    (out_dir / "weekly_summary_reusable_prompt.txt").write_text(reusable_prompt, encoding="utf-8")


def _extract_text_from_response(resp_json: dict[str, Any]) -> str:
    """取出 extract text from response 對應的資料或結果。"""
    if isinstance(resp_json.get("output_text"), str) and resp_json.get("output_text").strip():
        return str(resp_json["output_text"]).strip()

    output = resp_json.get("output")
    if not isinstance(output, list):
        return ""
    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if str(part.get("type") or "") != "output_text":
                continue
            text = str(part.get("text") or "").strip()
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def _parse_bool_env(value: str | None, default: bool) -> bool:
    """解析 parse bool env 對應的資料或結果。"""
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _openai_web_search_enabled() -> bool:
    """執行 openai web search enabled 的主要流程。"""
    raw = os.getenv("LLM_WEB_SEARCH_ENABLED")
    if raw is None:
        raw = os.getenv("OPENAI_WEB_SEARCH_ENABLED")
    return _parse_bool_env(raw, default=True)


def _send_openai_response_request(url: str, api_key: str, payload: dict[str, Any]) -> str:
    """執行 send openai response request 的主要流程。"""
    req = Request(url, method="POST", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "news-collector-weekly-summary/1.0")

    try:
        with urlopen(req, timeout=_llm_timeout_seconds(120)) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise RuntimeError(f"OpenAI HTTPError status={exc.code} body={body[:800]}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI URLError: {exc}") from exc


def _should_retry_openai_without_web_search(error_message: str) -> bool:
    """執行 should retry openai without web search 的主要流程。"""
    lower = error_message.lower()
    if not any(f"status={status}" in lower for status in (400, 403, 404)):
        return False
    return any(token in lower for token in ("web_search", "tool", "tools"))


def _call_openai_response(api_base: str, api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    """執行 call openai response 的主要流程。"""
    url = f"{api_base.rstrip('/')}/responses"
    payload = {
        "model": model,
        "instructions": system_prompt,
        "input": user_prompt,
        "text": {"format": {"type": "text"}},
    }
    if _openai_web_search_enabled():
        payload["tools"] = [{"type": "web_search"}]
    if _openai_model_supports_temperature(model):
        payload["temperature"] = 0.2

    try:
        body = _send_openai_response_request(url=url, api_key=api_key, payload=payload)
    except RuntimeError as exc:
        # 某些帳號/模型不支援 web_search tool；遇到這類錯誤時會自動退成純文字 call，
        # 目標是保住摘要產出，而不是因工具不可用整次失敗。
        if payload.get("tools") and _should_retry_openai_without_web_search(str(exc)):
            logger.warning("OpenAI web_search tool unavailable; retrying response without web search")
            fallback_payload = dict(payload)
            fallback_payload.pop("tools", None)
            body = _send_openai_response_request(url=url, api_key=api_key, payload=fallback_payload)
        else:
            raise

    parsed = json.loads(body)
    result = _extract_text_from_response(parsed)
    if not result:
        raise RuntimeError("OpenAI response has no output text")
    return result.strip()


def _openai_model_supports_temperature(model: str) -> bool:
    """執行 openai model supports temperature 的主要流程。"""
    value = (model or "").strip().lower()
    return not (value == "gpt-5" or value.startswith("gpt-5-"))


def _llm_timeout_seconds(default: int = 120) -> int:
    """執行 llm timeout seconds 的主要流程。"""
    raw = os.getenv("LLM_TIMEOUT_SECONDS") or os.getenv("OPENAI_RESPONSE_TIMEOUT_SECONDS") or str(default)
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(15, min(value, 300))


def _extract_text_from_anthropic(resp_json: dict[str, Any]) -> str:
    """取出 extract text from anthropic 對應的資料或結果。"""
    content = resp_json.get("content")
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if str(part.get("type") or "") != "text":
            continue
        text = str(part.get("text") or "").strip()
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def _call_anthropic_message(api_base: str, api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    """執行 call anthropic message 的主要流程。"""
    url = f"{api_base.rstrip('/')}/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": 0.2,
    }
    req = Request(url, method="POST", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")
    req.add_header("user-agent", "news-collector-weekly-summary/1.0")

    try:
        with urlopen(req, timeout=_llm_timeout_seconds(120)) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise RuntimeError(f"Anthropic HTTPError status={exc.code} body={body[:800]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Anthropic URLError: {exc}") from exc

    parsed = json.loads(body)
    result = _extract_text_from_anthropic(parsed)
    if not result:
        raise RuntimeError("Anthropic response has no output text")
    return result.strip()


def _call_llm(provider: str, api_base: str, api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    """執行 call llm 的主要流程。"""
    if (provider or "").strip().lower() == "anthropic":
        return _call_anthropic_message(api_base, api_key, model, system_prompt, user_prompt)
    return _call_openai_response(api_base, api_key, model, system_prompt, user_prompt)


def _normalize_line_text(text: str) -> str:
    """正規化 normalize line text 對應的資料或結果。"""
    compact = re.sub(r"[ \t]+", " ", text).strip()
    return compact[:4500]


def _store_weekly_analysis(
    store: MySqlEventStore,
    now_local: datetime,
    config: WeeklySummaryConfig,
    message: str,
    events_used: int,
) -> None:
    """執行 store weekly analysis 的主要流程。"""
    store.upsert_market_analysis(
        MarketAnalysisRecord(
            analysis_date=_week_key(now_local),
            analysis_slot=WEEKLY_ANALYSIS_SLOT,
            scheduled_time_local="Mon 07:30",
            model=config.model,
            prompt_version=WEEKLY_PROMPT_VERSION,
            summary_text=message,
            events_used=events_used,
            market_rows_used=0,
            push_enabled=True,
            pushed=False,
            raw_json=json.dumps(
                {
                    "dimension": "weekly",
                    "anchor_local_date": now_local.date().isoformat(),
                    "scheduled_weekday": config.weekday,
                    "scheduled_time": f"{config.hour:02d}:{config.minute:02d}",
                    "events_used": events_used,
                    "delivery_owner": "java",
                    "python_push_removed": True,
                    "web_search_requested": config.provider == "openai" and _openai_web_search_enabled(),
                },
                ensure_ascii=False,
            ),
        )
    )


def run_once(config: WeeklySummaryConfig) -> dict[str, Any]:
    """執行單次任務流程並回傳結果。"""
    now_local = datetime.now().astimezone()
    run_key = _week_key(now_local)
    state_file = Path(config.state_file)

    # 每週排程有兩道保護：先檢查是否在允許時間窗，再檢查這個 iso week 是否已寫過。
    # 這樣手動重啟服務或排程重試時，不會同一週重複寫多筆。
    if not _should_run_now(config, now_local):
        logger.info(
            "Weekly summary skipped by schedule now=%s target_weekday=%d target_time=%02d:%02d",
            now_local.isoformat(),
            config.weekday,
            config.hour,
            config.minute,
        )
        return {"ok": True, "skipped": "schedule"}

    if _already_sent_this_week(state_file, run_key):
        logger.info("Weekly summary already sent for %s", run_key)
        return {"ok": True, "skipped": "already_sent"}

    if not config.api_key:
        raise RuntimeError(
            f"Missing {config.provider} API key. Checked env vars and file: "
            f"{config.api_key_file}"
        )

    relay_settings = load_settings(config.env_file)
    if not relay_settings.mysql_enabled:
        raise RuntimeError("Weekly summary requires RELAY_MYSQL_ENABLED=true")

    store = MySqlEventStore(relay_settings)
    store.initialize()
    events = store.fetch_recent_summary_events(days=config.lookback_days, limit=config.max_events)
    if not events:
        logger.warning("Weekly summary skipped: no events in lookback window days=%d", config.lookback_days)
        return {"ok": True, "skipped": "no_events"}

    system_prompt, reusable_prompt = _compile_prompts(config)
    _write_prompt_snapshots(system_prompt, reusable_prompt)

    events_payload = [
        {
            "id": event.row_id,
            "source": event.source,
            "title": event.title,
            "url": event.url,
            "summary": event.summary,
            "published_at": event.published_at,
            "created_at": event.created_at,
        }
        for event in events
    ]
    # weekly_summary 直接帶最近 N 天事件摘要，不再重放完整 raw_json，
    # 目的是保留主線資訊，同時控制 prompt 體積。
    week_range = f"{config.lookback_days} days ending {now_local.strftime('%Y-%m-%d %H:%M %Z')}"
    user_prompt = reusable_prompt.format(week_range=week_range, events_json=json.dumps(events_payload, ensure_ascii=False))

    summary_text = _call_llm(
        provider=config.provider,
        api_base=config.api_base,
        api_key=config.api_key,
        model=config.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    message = _normalize_line_text(summary_text)

    logger.info("[WEEKLY_SUMMARY_STORED_ONLY] model=%s", config.model)
    logger.info("[WEEKLY_SUMMARY_TEXT]\n%s", message)

    _store_weekly_analysis(
        store=store,
        now_local=now_local,
        config=config,
        message=message,
        events_used=len(events),
    )
    _mark_sent_this_week(state_file, run_key)
    return {
        "ok": True,
        "pushed": 0,
        "events_used": len(events),
        "dry_run": True,
        "analysis_date": run_key,
        "analysis_slot": WEEKLY_ANALYSIS_SLOT,
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
        config = _load_weekly_config(args)
        result = run_once(config)
        logger.info("Weekly summary result: %s", result)
        return 0
    except Exception as exc:
        logger.error("Weekly summary failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
