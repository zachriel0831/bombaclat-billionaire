"""Collect recent source context for the Codex four-hour news digest.

The script only reads existing storage and emits compact JSON. It does not call
paid model APIs and does not write generated analysis.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from event_relay.config import load_settings as load_relay_settings  # noqa: E402
from news_platform.config import load_settings as load_news_platform_settings  # noqa: E402

try:
    TAIPEI = ZoneInfo("Asia/Taipei")
except Exception:
    TAIPEI = timezone(timedelta(hours=8), name="Asia/Taipei")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
MOJIBAKE_RE = re.compile(r"[\ufffd\u0080-\u009f\ue000-\uf8ff]|\?{3,}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--hours", type=int, default=4)
    parser.add_argument("--limit-per-section", type=int, default=80)
    parser.add_argument("--out-file", default="")
    args = parser.parse_args()

    hours = max(1, min(int(args.hours), 24))
    limit = max(1, min(int(args.limit_per_section), 200))
    context = collect_context(args.env_file, hours=hours, limit=limit)

    payload = json.dumps(context, ensure_ascii=False, indent=2)
    if args.out_file:
        out_path = Path(args.out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


def collect_context(env_file: str, *, hours: int, limit: int) -> dict[str, Any]:
    now = datetime.now(TAIPEI)
    window_start = now - timedelta(hours=hours)
    notes: list[str] = []

    relay_settings = load_relay_settings(env_file)
    news_settings = load_news_platform_settings(env_file)

    relay_conn = connect_mysql(
        host=relay_settings.mysql_host,
        port=relay_settings.mysql_port,
        user=relay_settings.mysql_user,
        password=relay_settings.mysql_password,
        database=relay_settings.mysql_database,
        timeout=relay_settings.mysql_connect_timeout_seconds,
    )
    news_conn = connect_mysql(
        host=news_settings.mysql_host,
        port=news_settings.mysql_port,
        user=news_settings.mysql_user,
        password=news_settings.mysql_password,
        database=news_settings.mysql_database,
        timeout=news_settings.mysql_connect_timeout_seconds,
    )

    try:
        finance = fetch_relay_finance_events(
            relay_conn,
            safe_table_name(relay_settings.mysql_event_table),
            hours=hours,
            limit=limit,
            notes=notes,
        )
        celebrity = fetch_celebrity_events(
            relay_conn,
            safe_table_name(relay_settings.mysql_event_table),
            hours=hours,
            limit=limit,
            notes=notes,
        )
        palestine = fetch_palestine_news(
            relay_conn,
            safe_table_name(relay_settings.mysql_palestine_news_table),
            hours=hours,
            limit=limit,
            notes=notes,
        )
        society = fetch_news_platform_articles(
            news_conn,
            safe_table_name(news_settings.mysql_article_table),
            category="society",
            hours=hours,
            limit=limit,
            notes=notes,
        )
        politics = fetch_news_platform_articles(
            news_conn,
            safe_table_name(news_settings.mysql_article_table),
            category="politics",
            hours=hours,
            limit=limit,
            notes=notes,
        )
    finally:
        relay_conn.close()
        news_conn.close()

    sections = {
        "finance": finance,
        "society": society,
        "politics": politics,
        "celebrity": celebrity,
        "free_palestine": palestine,
    }
    return {
        "contextVersion": "four-hour-digest-context-v1",
        "windowStart": window_start.isoformat(timespec="seconds"),
        "windowEnd": now.isoformat(timespec="seconds"),
        "generatedAt": now.isoformat(timespec="seconds"),
        "hours": hours,
        "sourceCounts": {key: len(value) for key, value in sections.items()},
        "sections": sections,
        "notes": notes,
    }


def connect_mysql(*, host: str, port: int, user: str, password: str, database: str, timeout: int):
    try:
        import mysql.connector  # type: ignore
    except ImportError as exc:
        raise RuntimeError("mysql-connector-python is required") from exc
    return mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        connection_timeout=timeout,
        charset="utf8mb4",
        use_unicode=True,
    )


def fetch_relay_finance_events(conn, table: str, *, hours: int, limit: int, notes: list[str]) -> list[dict[str, Any]]:
    sql = f"""
        SELECT id, source, title, summary, url, published_at, created_at
        FROM {table}
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
          AND source NOT LIKE 'x:%%'
          AND source NOT LIKE 'truthsocial:%%'
          AND source NOT LIKE 'market_context:%%'
          AND source NOT LIKE 'sec:%%'
          AND source NOT LIKE 'twse_mops:%%'
          AND source NOT LIKE 'yfinance%%'
          AND source NOT LIKE 'palestine_watch:%%'
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    rows = query_rows(conn, sql, (hours, limit), notes, "finance")
    return filter_usable_items([relay_item(row) for row in rows], notes, "finance")


def fetch_celebrity_events(conn, table: str, *, hours: int, limit: int, notes: list[str]) -> list[dict[str, Any]]:
    sql = f"""
        SELECT id, source, title, summary, url, published_at, created_at
        FROM {table}
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
          AND (source LIKE 'x:%%' OR source LIKE 'truthsocial:%%')
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    rows = query_rows(conn, sql, (hours, limit), notes, "celebrity")
    return filter_usable_items([relay_item(row) for row in rows], notes, "celebrity")


def fetch_palestine_news(conn, table: str, *, hours: int, limit: int, notes: list[str]) -> list[dict[str, Any]]:
    sql = f"""
        SELECT id, source_id, source_name, title, summary, url, published_at, last_seen_at
        FROM {table}
        WHERE topic = 'free_palestine'
          AND language = 'en'
          AND last_seen_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
        ORDER BY last_seen_at DESC, id DESC
        LIMIT %s
    """
    rows = query_rows(conn, sql, (hours, limit), notes, "free_palestine")
    return filter_usable_items([
        {
            "id": row.get("id"),
            "source": clean_text(row.get("source_name") or row.get("source_id"), 80),
            "title": clean_text(row.get("title"), 220),
            "summary": clean_text(row.get("summary"), 500),
            "publishedAt": datetime_to_text(row.get("published_at")),
            "storedAt": datetime_to_text(row.get("last_seen_at")),
            "url": clean_text(row.get("url"), 500),
        }
        for row in rows
    ], notes, "free_palestine")


def fetch_news_platform_articles(
    conn,
    table: str,
    *,
    category: str,
    hours: int,
    limit: int,
    notes: list[str],
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT id, article_id, source_id, category, title, summary, url, published_at, fetched_at
        FROM {table}
        WHERE category = %s
          AND COALESCE(published_at, fetched_at) >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s HOUR)
        ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC
        LIMIT %s
    """
    rows = query_rows(conn, sql, (category, hours, limit), notes, category)
    return filter_usable_items([
        {
            "id": row.get("id"),
            "articleId": clean_text(row.get("article_id"), 80),
            "source": clean_text(row.get("source_id"), 80),
            "category": clean_text(row.get("category"), 32),
            "title": clean_text(row.get("title"), 220),
            "summary": clean_text(row.get("summary"), 500),
            "publishedAt": datetime_to_text(row.get("published_at")),
            "storedAt": datetime_to_text(row.get("fetched_at")),
            "url": clean_text(row.get("url"), 500),
        }
        for row in rows
    ], notes, category)


def relay_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "source": clean_text(row.get("source"), 80),
        "title": clean_text(row.get("title"), 220),
        "summary": clean_text(row.get("summary"), 500),
        "publishedAt": datetime_to_text(row.get("published_at")),
        "storedAt": datetime_to_text(row.get("created_at")),
        "url": clean_text(row.get("url"), 500),
    }


def query_rows(conn, sql: str, params: tuple[Any, ...], notes: list[str], section: str) -> list[dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return list(cursor.fetchall())
    except Exception as exc:  # mysql connector raises a vendor-specific base class
        notes.append(f"{section}: query failed ({exc.__class__.__name__})")
        return []
    finally:
        cursor.close()


def filter_usable_items(items: list[dict[str, Any]], notes: list[str], section: str) -> list[dict[str, Any]]:
    clean_items: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        if any(looks_mojibake(item.get(field)) for field in ("source", "title", "summary")):
            dropped += 1
            continue
        clean_items.append(item)
    if dropped:
        notes.append(f"{section}: skipped {dropped} likely mojibake rows")
    return clean_items


def looks_mojibake(value: Any) -> bool:
    if value is None:
        return False
    return bool(MOJIBAKE_RE.search(str(value)))


def safe_table_name(value: str) -> str:
    parts = [part.strip().strip("`") for part in value.split(".") if part.strip()]
    if not parts:
        raise ValueError("table name is required")
    for part in parts:
        if not IDENTIFIER_RE.match(part):
            raise ValueError(f"unsafe table name: {value!r}")
    return ".".join(f"`{part}`" for part in parts)


def clean_text(value: Any, max_chars: int) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def datetime_to_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return clean_text(value, 80)


if __name__ == "__main__":
    raise SystemExit(main())
