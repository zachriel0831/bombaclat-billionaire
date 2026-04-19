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

from line_event_relay.config import load_settings
from line_event_relay.service import LinePushClient, MySqlEventStore


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeeklySummaryConfig:
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
    dry_run: bool
    force: bool


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate weekly macro summary and push to LINE")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--force", action="store_true", help="Bypass schedule gate and run immediately")
    parser.add_argument("--dry-run", action="store_true", help="Do not push to LINE, print generated summary only")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_secret_from_dpapi_file(path: str) -> str | None:
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


def _load_weekly_config(args: argparse.Namespace) -> WeeklySummaryConfig:
    relay_settings = load_settings(args.env_file)

    api_key_file = (os.getenv("WEEKLY_SUMMARY_OPENAI_API_KEY_FILE", ".secrets/openai_api_key.dpapi") or ".secrets/openai_api_key.dpapi").strip()
    # Priority: explicit env > dpapi file
    api_key = (
        (os.getenv("WEEKLY_SUMMARY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        or (_load_secret_from_dpapi_file(api_key_file) or "")
    )

    env_dry_run = _parse_bool(os.getenv("WEEKLY_SUMMARY_DRY_RUN"), default=relay_settings.dispatch_dry_run)
    final_dry_run = bool(args.dry_run) or env_dry_run

    return WeeklySummaryConfig(
        env_file=args.env_file,
        model=(os.getenv("WEEKLY_SUMMARY_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini").strip(),
        api_base=(os.getenv("WEEKLY_SUMMARY_OPENAI_API_BASE", "https://api.openai.com/v1") or "https://api.openai.com/v1").strip(),
        api_key=api_key or None,
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
        weekday=max(0, min(6, int(os.getenv("WEEKLY_SUMMARY_WEEKDAY", "6")))),
        hour=max(0, min(23, int(os.getenv("WEEKLY_SUMMARY_HOUR", "10")))),
        minute=max(0, min(59, int(os.getenv("WEEKLY_SUMMARY_MINUTE", "0")))),
        window_minutes=max(1, int(os.getenv("WEEKLY_SUMMARY_WINDOW_MINUTES", "20"))),
        state_file=(
            os.getenv("WEEKLY_SUMMARY_STATE_FILE", "runtime/state/weekly-summary-last-week.txt")
            or "runtime/state/weekly-summary-last-week.txt"
        ).strip(),
        dry_run=final_dry_run,
        force=bool(args.force),
    )


def _week_key(now_local: datetime) -> str:
    iso_year, iso_week, _ = now_local.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _should_run_now(config: WeeklySummaryConfig, now_local: datetime) -> bool:
    if config.force:
        return True
    if now_local.weekday() != config.weekday:
        return False
    target = now_local.replace(hour=config.hour, minute=config.minute, second=0, microsecond=0)
    delta_minutes = abs((now_local - target).total_seconds()) / 60.0
    return delta_minutes <= float(config.window_minutes)


def _already_sent_this_week(state_file: Path, key: str) -> bool:
    if not state_file.exists():
        return False
    saved = state_file.read_text(encoding="utf-8", errors="ignore").strip()
    return saved == key


def _mark_sent_this_week(state_file: Path, key: str) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(key, encoding="utf-8")


def _load_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore").strip()


def _compile_prompts(config: WeeklySummaryConfig) -> tuple[str, str]:
    macro_skill = _load_text(config.skill_macro_path)
    line_format_skill = _load_text(config.skill_line_format_path)

    system_prompt = (
        "You are a senior macro editor. Produce one weekly brief for LINE users in Traditional Chinese.\n"
        "Use plain text only. Do not output code blocks. Do not fabricate facts.\n"
        "Focus on international politics, macro/finance, and technology.\n\n"
        "[Macro Skill]\n"
        f"{macro_skill}\n\n"
        "[LINE Format Skill]\n"
        f"{line_format_skill}\n"
    )

    reusable_prompt = (
        "Please generate one weekly political/economic summary in Traditional Chinese for LINE.\n"
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
    out_dir = Path("runtime/prompts")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "weekly_summary_system_prompt.txt").write_text(system_prompt, encoding="utf-8")
    (out_dir / "weekly_summary_reusable_prompt.txt").write_text(reusable_prompt, encoding="utf-8")


def _extract_text_from_response(resp_json: dict[str, Any]) -> str:
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


def _call_openai_response(api_base: str, api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    url = f"{api_base.rstrip('/')}/responses"
    payload = {
        "model": model,
        "instructions": system_prompt,
        "input": user_prompt,
        "text": {"format": {"type": "text"}},
        "temperature": 0.2,
    }
    req = Request(url, method="POST", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "news-collector-weekly-summary/1.0")

    try:
        with urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise RuntimeError(f"OpenAI HTTPError status={exc.code} body={body[:800]}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI URLError: {exc}") from exc

    parsed = json.loads(body)
    result = _extract_text_from_response(parsed)
    if not result:
        raise RuntimeError("OpenAI response has no output text")
    return result.strip()


def _normalize_line_text(text: str) -> str:
    compact = re.sub(r"[ \t]+", " ", text).strip()
    return compact[:4500]


def run_once(config: WeeklySummaryConfig) -> dict[str, Any]:
    now_local = datetime.now().astimezone()
    run_key = _week_key(now_local)
    state_file = Path(config.state_file)

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
            "Missing OpenAI API key. Checked env vars and file: "
            f"{config.api_key_file}"
        )

    relay_settings = load_settings(config.env_file)
    if not relay_settings.mysql_enabled:
        raise RuntimeError("Weekly summary requires LINE_RELAY_MYSQL_ENABLED=true")

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
    week_range = f"{config.lookback_days} days ending {now_local.strftime('%Y-%m-%d %H:%M %Z')}"
    user_prompt = reusable_prompt.format(week_range=week_range, events_json=json.dumps(events_payload, ensure_ascii=False))

    summary_text = _call_openai_response(
        api_base=config.api_base,
        api_key=config.api_key,
        model=config.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    message = _normalize_line_text(summary_text)

    targets = [("group", gid) for gid in store.list_active_group_ids()] + [("user", uid) for uid in store.list_active_user_ids()]
    fallback_users = [uid for uid in relay_settings.line_direct_target_user_ids if uid]
    for uid in fallback_users:
        if ("user", uid) not in targets:
            targets.append(("user", uid))

    if not targets:
        raise RuntimeError("No LINE targets found (active groups/users and LINE_DIRECT_TARGET_USER_IDS are empty)")

    pushed = 0
    if config.dry_run:
        logger.info("[WEEKLY_SUMMARY_DRY_RUN] targets=%d model=%s", len(targets), config.model)
        logger.info("[WEEKLY_SUMMARY_TEXT]\n%s", message)
        pushed = len(targets)
    else:
        client = LinePushClient(relay_settings)
        for _, target_id in targets:
            client.push_text(target_id, message)
            pushed += 1
        logger.info("Weekly summary pushed to %d targets", pushed)

    _mark_sent_this_week(state_file, run_key)
    return {"ok": True, "pushed": pushed, "events_used": len(events), "dry_run": config.dry_run}


def main() -> int:
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
