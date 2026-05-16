"""News-platform runtime settings — 獨立 MySQL DB，與 event_relay 不共用。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_provider_order(value: str | None) -> tuple[str, ...]:
    raw = value or "openai,anthropic"
    providers = tuple(
        item.strip().lower()
        for item in raw.split(",")
        if item.strip().lower() in {"openai", "anthropic"}
    )
    return providers or ("openai", "anthropic")


@dataclass(frozen=True)
class NewsPlatformSettings:
    mysql_enabled: bool
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    mysql_article_table: str
    mysql_source_table: str
    mysql_public_record_table: str
    mysql_article_record_link_table: str
    mysql_author_table: str
    mysql_article_author_table: str
    mysql_author_coverage_daily_table: str
    mysql_connect_timeout_seconds: int
    article_ttl_days: int
    poll_interval_seconds: int
    http_timeout_seconds: int
    limit_per_feed: int
    max_age_days: int
    topic_llm_enabled: bool
    topic_llm_provider_order: tuple[str, ...]
    topic_llm_timeout_seconds: int
    topic_llm_batch_size: int
    topic_llm_min_confidence: float
    topic_openai_model: str
    topic_openai_api_base: str
    topic_openai_api_key: str
    topic_anthropic_model: str
    topic_anthropic_api_base: str
    topic_anthropic_api_key: str


def load_settings(env_file: str = ".env") -> NewsPlatformSettings:
    _load_env_file(env_file)
    topic_min_confidence = float(os.getenv("NEWSPF_TOPIC_LLM_MIN_CONFIDENCE", "0.55"))
    return NewsPlatformSettings(
        mysql_enabled=_parse_bool(os.getenv("NEWSPF_MYSQL_ENABLED", "true"), default=True),
        mysql_host=os.getenv("NEWSPF_MYSQL_HOST", "127.0.0.1"),
        mysql_port=int(os.getenv("NEWSPF_MYSQL_PORT", "3306")),
        mysql_user=os.getenv("NEWSPF_MYSQL_USER", "root"),
        mysql_password=os.getenv("NEWSPF_MYSQL_PASSWORD", "root"),
        mysql_database=os.getenv("NEWSPF_MYSQL_DATABASE", "news_platform"),
        mysql_article_table=os.getenv("NEWSPF_MYSQL_ARTICLE_TABLE", "t_news_articles"),
        mysql_source_table=os.getenv("NEWSPF_MYSQL_SOURCE_TABLE", "t_news_sources"),
        mysql_public_record_table=os.getenv("NEWSPF_MYSQL_PUBLIC_RECORD_TABLE", "t_public_records"),
        mysql_article_record_link_table=os.getenv(
            "NEWSPF_MYSQL_ARTICLE_RECORD_LINK_TABLE",
            "t_news_article_public_record_links",
        ),
        mysql_author_table=os.getenv("NEWSPF_MYSQL_AUTHOR_TABLE", "t_news_authors"),
        mysql_article_author_table=os.getenv(
            "NEWSPF_MYSQL_ARTICLE_AUTHOR_TABLE",
            "t_news_article_authors",
        ),
        mysql_author_coverage_daily_table=os.getenv(
            "NEWSPF_MYSQL_AUTHOR_COVERAGE_DAILY_TABLE",
            "t_news_author_coverage_daily",
        ),
        mysql_connect_timeout_seconds=int(os.getenv("NEWSPF_MYSQL_CONNECT_TIMEOUT", "5")),
        article_ttl_days=max(1, min(365, int(os.getenv("NEWSPF_ARTICLE_TTL_DAYS", "30")))),
        poll_interval_seconds=max(60, int(os.getenv("NEWSPF_POLL_INTERVAL_SECONDS", "900"))),
        http_timeout_seconds=int(os.getenv("NEWSPF_HTTP_TIMEOUT_SECONDS", "15")),
        limit_per_feed=max(1, int(os.getenv("NEWSPF_LIMIT_PER_FEED", "20"))),
        max_age_days=max(1, min(30, int(os.getenv("NEWSPF_MAX_AGE_DAYS", "3")))),
        topic_llm_enabled=_parse_bool(os.getenv("NEWSPF_TOPIC_LLM_ENABLED"), default=False),
        topic_llm_provider_order=_parse_provider_order(os.getenv("NEWSPF_TOPIC_LLM_PROVIDER_ORDER")),
        topic_llm_timeout_seconds=max(2, int(os.getenv("NEWSPF_TOPIC_LLM_TIMEOUT_SECONDS", "20"))),
        topic_llm_batch_size=max(1, int(os.getenv("NEWSPF_TOPIC_LLM_BATCH_SIZE", "50"))),
        topic_llm_min_confidence=max(0.0, min(1.0, topic_min_confidence)),
        topic_openai_model=os.getenv("NEWSPF_TOPIC_OPENAI_MODEL", "gpt-5-nano").strip() or "gpt-5-nano",
        topic_openai_api_base=os.getenv("NEWSPF_TOPIC_OPENAI_API_BASE", "https://api.openai.com/v1").strip(),
        topic_openai_api_key=(
            os.getenv("NEWSPF_TOPIC_OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        ).strip(),
        topic_anthropic_model=(
            os.getenv("NEWSPF_TOPIC_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001").strip()
            or "claude-haiku-4-5-20251001"
        ),
        topic_anthropic_api_base=os.getenv("NEWSPF_TOPIC_ANTHROPIC_API_BASE", "https://api.anthropic.com").strip(),
        topic_anthropic_api_key=(
            os.getenv("NEWSPF_TOPIC_ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or ""
        ).strip(),
    )
