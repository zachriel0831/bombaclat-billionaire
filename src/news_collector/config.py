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
    benzinga_enabled: bool
    benzinga_api_key: str | None
    benzinga_api_key_file: str
    benzinga_stop_on_429: bool
    x_enabled: bool
    x_bearer_token: str | None
    x_bearer_token_file: str
    x_accounts: list[str]
    x_max_results_per_account: int
    x_stop_on_429: bool
    x_include_replies: bool
    x_include_retweets: bool
    gdelt_query: str
    gdelt_max_records: int
    gdelt_cooldown_on_429: bool
    gdelt_cooldown_seconds: int
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
        benzinga_enabled=_parse_bool(os.getenv("BENZINGA_ENABLED", "false")),
        benzinga_api_key=os.getenv("BENZINGA_API_KEY") or None,
        benzinga_api_key_file=os.getenv("BENZINGA_API_KEY_FILE", ".secrets/benzinga_api_key.dpapi"),
        benzinga_stop_on_429=_parse_bool(os.getenv("BENZINGA_STOP_ON_429", "false")),
        x_enabled=_parse_bool(os.getenv("X_ENABLED", "false")),
        x_bearer_token=os.getenv("X_BEARER_TOKEN") or None,
        x_bearer_token_file=os.getenv("X_BEARER_TOKEN_FILE", ".secrets/x_bearer_token.dpapi"),
        x_accounts=x_accounts,
        x_max_results_per_account=max(1, int(os.getenv("X_MAX_RESULTS_PER_ACCOUNT", "5"))),
        x_stop_on_429=_parse_bool(os.getenv("X_STOP_ON_429", "true")),
        x_include_replies=_parse_bool(os.getenv("X_INCLUDE_REPLIES", "false")),
        x_include_retweets=_parse_bool(os.getenv("X_INCLUDE_RETWEETS", "false")),
        gdelt_query=os.getenv("GDELT_QUERY", "(finance OR economy OR inflation OR \"central bank\")"),
        gdelt_max_records=int(os.getenv("GDELT_MAX_RECORDS", "50")),
        gdelt_cooldown_on_429=_parse_bool(os.getenv("GDELT_COOLDOWN_ON_429", "false")),
        gdelt_cooldown_seconds=int(os.getenv("GDELT_COOLDOWN_SECONDS", "600")),
        official_rss_feeds=feed_list,
        official_rss_first_per_feed=_parse_bool(os.getenv("OFFICIAL_RSS_FIRST_PER_FEED", "false")),
        http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "15")),
    )


def resolve_benzinga_api_key(settings: Settings) -> str | None:
    # 優先使用環境變數；若未提供，再嘗試讀取本機加密檔。
    if settings.benzinga_api_key:
        return settings.benzinga_api_key

    return _load_secret_from_dpapi_file(settings.benzinga_api_key_file)


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
