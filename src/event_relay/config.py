"""Event-relay runtime settings.

Defines ``RelaySettings`` (host/port, MySQL connection, table names,
retention) and ``load_settings()`` which reads env vars (with a tolerant
``.env`` loader) and returns a frozen settings object consumed by
``MySqlEventStore``, ``RelayProcessor``, and the HTTP server.
"""

from __future__ import annotations

# 讀取 relay 服務環境設定與資料庫參數。
from dataclasses import dataclass
from pathlib import Path
import os


def load_env_file(path: str) -> None:
    """載入 load env file 對應的資料或結果。"""
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
    """封裝 Relay Settings 相關資料與行為。"""
    host: str
    port: int
    dispatch_interval_seconds: int
    mysql_enabled: bool
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    mysql_event_table: str
    mysql_x_table: str
    mysql_market_table: str
    mysql_quote_snapshot_table: str
    mysql_analysis_table: str
    mysql_annotation_table: str
    mysql_event_embedding_table: str
    mysql_analysis_embedding_table: str
    mysql_connect_timeout_seconds: int
    retention_enabled: bool
    retention_keep_days: int


def parse_bool(value: str | None, default: bool = False) -> bool:
    """解析 parse bool 對應的資料或結果。"""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(env_file: str = ".env") -> RelaySettings:
    """載入 load settings 對應的資料或結果。"""
    load_env_file(env_file)

    return RelaySettings(
        host=os.getenv("RELAY_HOST", "0.0.0.0"),
        port=int(os.getenv("RELAY_PORT") or os.getenv("PORT", "18090")),
        dispatch_interval_seconds=int(os.getenv("RELAY_DISPATCH_INTERVAL_SECONDS", "300")),
        mysql_enabled=parse_bool(os.getenv("RELAY_MYSQL_ENABLED", "true"), default=True),
        mysql_host=os.getenv("RELAY_MYSQL_HOST", "127.0.0.1"),
        mysql_port=int(os.getenv("RELAY_MYSQL_PORT", "3306")),
        mysql_user=os.getenv("RELAY_MYSQL_USER", "root"),
        mysql_password=os.getenv("RELAY_MYSQL_PASSWORD", "root"),
        mysql_database=os.getenv("RELAY_MYSQL_DATABASE", "news_relay"),
        mysql_event_table=os.getenv("RELAY_MYSQL_EVENT_TABLE", "t_relay_events"),
        mysql_x_table=os.getenv("RELAY_MYSQL_X_TABLE", "t_x_posts"),
        mysql_market_table=os.getenv("RELAY_MYSQL_MARKET_TABLE", "t_market_index_snapshots"),
        mysql_quote_snapshot_table=os.getenv(
            "RELAY_MYSQL_QUOTE_SNAPSHOT_TABLE", "t_market_quote_snapshots"
        ),
        mysql_analysis_table=os.getenv("RELAY_MYSQL_ANALYSIS_TABLE", "t_market_analyses"),
        mysql_annotation_table=os.getenv(
            "RELAY_MYSQL_ANNOTATION_TABLE", "t_relay_event_annotations"
        ),
        mysql_event_embedding_table=os.getenv(
            "RELAY_MYSQL_EVENT_EMBEDDING_TABLE", "t_event_embeddings"
        ),
        mysql_analysis_embedding_table=os.getenv(
            "RELAY_MYSQL_ANALYSIS_EMBEDDING_TABLE", "t_analysis_embeddings"
        ),
        mysql_connect_timeout_seconds=int(os.getenv("RELAY_MYSQL_CONNECT_TIMEOUT", "5")),
        retention_enabled=parse_bool(os.getenv("RELAY_RETENTION_ENABLED", "true"), default=True),
        retention_keep_days=max(1, min(365, int(os.getenv("RELAY_RETENTION_KEEP_DAYS", "7")))),
    )
