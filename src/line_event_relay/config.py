from __future__ import annotations

# 讀取 relay 服務環境設定與資料庫參數。
from dataclasses import dataclass
from pathlib import Path
import os


def load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class RelaySettings:
    host: str
    port: int
    line_channel_access_token: str
    line_target_group_id: str
    dispatch_interval_seconds: int
    dispatch_batch_size: int
    dispatch_dry_run: bool
    mysql_enabled: bool
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    mysql_event_table: str
    mysql_group_table: str
    mysql_user_table: str
    mysql_x_table: str
    mysql_connect_timeout_seconds: int


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(env_file: str = ".env") -> RelaySettings:
    load_env_file(env_file)

    dry_run = parse_bool(os.getenv("LINE_RELAY_DISPATCH_DRY_RUN", "true"), default=True)
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    group_id = os.getenv("LINE_TARGET_GROUP_ID", "").strip()

    if not dry_run and not token:
        raise ValueError("LINE_CHANNEL_ACCESS_TOKEN is required when LINE_RELAY_DISPATCH_DRY_RUN=false")

    return RelaySettings(
        host=os.getenv("LINE_RELAY_HOST", "0.0.0.0"),
        port=int(os.getenv("LINE_RELAY_PORT", "18090")),
        line_channel_access_token=token,
        line_target_group_id=group_id,
        dispatch_interval_seconds=int(os.getenv("LINE_RELAY_DISPATCH_INTERVAL_SECONDS", "300")),
        dispatch_batch_size=int(os.getenv("LINE_RELAY_DISPATCH_BATCH_SIZE", "100")),
        dispatch_dry_run=dry_run,
        mysql_enabled=parse_bool(os.getenv("LINE_RELAY_MYSQL_ENABLED", "true"), default=True),
        mysql_host=os.getenv("LINE_RELAY_MYSQL_HOST", "127.0.0.1"),
        mysql_port=int(os.getenv("LINE_RELAY_MYSQL_PORT", "3306")),
        mysql_user=os.getenv("LINE_RELAY_MYSQL_USER", "root"),
        mysql_password=os.getenv("LINE_RELAY_MYSQL_PASSWORD", "root"),
        mysql_database=os.getenv("LINE_RELAY_MYSQL_DATABASE", "news_relay"),
        mysql_event_table=os.getenv("LINE_RELAY_MYSQL_EVENT_TABLE", "t_relay_events"),
        mysql_group_table=os.getenv("LINE_RELAY_MYSQL_GROUP_TABLE", "t_bot_group_info"),
        mysql_user_table=os.getenv("LINE_RELAY_MYSQL_USER_TABLE", "t_bot_user_info"),
        mysql_x_table=os.getenv("LINE_RELAY_MYSQL_X_TABLE", "t_x_posts"),
        mysql_connect_timeout_seconds=int(os.getenv("LINE_RELAY_MYSQL_CONNECT_TIMEOUT", "5")),
    )
