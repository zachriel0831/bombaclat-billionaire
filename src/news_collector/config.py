from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    x_enabled: bool
    x_bearer_token: str | None
    x_bearer_token_file: str
    x_accounts: list[str]
    x_max_results_per_account: int
    x_stop_on_429: bool
    x_auto_heal_too_many_connections: bool
    x_heal_cooldown_seconds: int
    x_include_replies: bool
    x_include_retweets: bool
    x_backfill_enabled: bool
    x_backfill_max_results_per_account: int
    official_rss_feeds: list[str]
    official_rss_first_per_feed: bool
    http_timeout_seconds: int


DEFAULT_RSS_FEEDS = [
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://www.ecb.europa.eu/rss/press.html",
    "https://www.bis.org/doclist/all_pressrels.rss",
]


def load_settings(env_file: str = ".env") -> Settings:
    _load_env_file(Path(env_file))

    feeds = os.getenv("OFFICIAL_RSS_FEEDS", "")
    feed_list = [s.strip() for s in feeds.split(",") if s.strip()] or DEFAULT_RSS_FEEDS
    x_accounts = [s.strip() for s in os.getenv("X_ACCOUNTS", "").split(",") if s.strip()]

    return Settings(
        x_enabled=_parse_bool(os.getenv("X_ENABLED", "false")),
        x_bearer_token=os.getenv("X_BEARER_TOKEN") or None,
        x_bearer_token_file=os.getenv("X_BEARER_TOKEN_FILE", ".secrets/x_bearer_token.dpapi"),
        x_accounts=x_accounts,
        x_max_results_per_account=max(1, int(os.getenv("X_MAX_RESULTS_PER_ACCOUNT", "5"))),
        x_stop_on_429=_parse_bool(os.getenv("X_STOP_ON_429", "true")),
        x_auto_heal_too_many_connections=_parse_bool(os.getenv("X_AUTO_HEAL_TOO_MANY_CONNECTIONS", "true")),
        x_heal_cooldown_seconds=max(5, int(os.getenv("X_HEAL_COOLDOWN_SECONDS", "45"))),
        x_include_replies=_parse_bool(os.getenv("X_INCLUDE_REPLIES", "false")),
        x_include_retweets=_parse_bool(os.getenv("X_INCLUDE_RETWEETS", "false")),
        x_backfill_enabled=_parse_bool(os.getenv("X_BACKFILL_ENABLED", "true")),
        x_backfill_max_results_per_account=max(1, min(100, int(os.getenv("X_BACKFILL_MAX_RESULTS_PER_ACCOUNT", "10")))),
        official_rss_feeds=feed_list,
        official_rss_first_per_feed=_parse_bool(os.getenv("OFFICIAL_RSS_FIRST_PER_FEED", "false")),
        http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "15")),
    )


def resolve_x_bearer_token(settings: Settings) -> str | None:
    # 優先使用環境變數；若未提供，再嘗試讀取本機加密檔。
    if settings.x_bearer_token:
        return settings.x_bearer_token
    return _load_secret_from_dpapi_file(settings.x_bearer_token_file)


def _load_secret_from_dpapi_file(path: str) -> str | None:
    file_path = Path(path)
    if not file_path.exists():
        return None

    # DPAPI 解密只在 Windows 提供，其他系統直接略過。
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


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}
