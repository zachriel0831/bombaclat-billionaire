"""Collect English Palestine issue news into long-term issue-news storage.

This module keeps the Free Palestine timeline's recent-news column separate
from the general finance relay feed. It stores accepted rows in
``t_palestine_news_items`` so ``t_relay_events`` retention does not delete
long-lived issue context.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import html
import json
import logging
import os
import re
import sys
import threading
from typing import Any
from urllib.parse import urlparse

from event_relay.config import load_env_file, load_settings
from news_collector.models import NewsItem
from news_collector.sources.rss import OfficialRssSource
from news_collector.utils import sort_timestamp, stable_id


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PalestineNewsFeed:
    source_id: str
    url: str


@dataclass(frozen=True)
class PalestineNewsItem:
    news_id: str
    source_id: str
    source_name: str
    title: str
    url: str
    summary: str
    published_at: str | None
    language: str
    topic: str
    source_url: str | None
    original_source: str | None
    original_id: str | None
    tags: list[str]
    raw: dict[str, Any]

    @property
    def url_hash(self) -> str:
        return hashlib.sha1(self.url.strip().encode("utf-8")).hexdigest()

    @property
    def api_source(self) -> str:
        return f"palestine_watch:{self.source_id}"


@dataclass(frozen=True)
class PalestineNewsCollection:
    items: list[PalestineNewsItem]
    fetched_count: int
    skipped_count: int
    error_count: int

    @property
    def events(self) -> list[PalestineNewsItem]:
        """Backward-compatible alias for older local tests/scripts."""
        return self.items


DEFAULT_FEEDS: tuple[PalestineNewsFeed, ...] = (
    PalestineNewsFeed(
        "google_news_en",
        "https://news.google.com/rss/search?q=(Gaza%20OR%20Palestine%20OR%20Palestinian%20OR%20%22West%20Bank%22)%20when%3A7d&hl=en-US&gl=US&ceid=US%3Aen",
    ),
    PalestineNewsFeed("al_jazeera_en", "https://www.aljazeera.com/xml/rss/all.xml"),
    PalestineNewsFeed("bbc_middle_east_en", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
    PalestineNewsFeed("guardian_palestine_en", "https://www.theguardian.com/world/palestinian-territories/rss"),
)

PALESTINE_KEYWORDS = (
    "gaza",
    "palestine",
    "palestinian",
    "west bank",
    "east jerusalem",
    "rafah",
    "khan younis",
    "jabalia",
    "deir al-balah",
    "ocha opt",
    "unrwa",
    "settler",
    "settlement",
    "occupation",
    "ceasefire",
    "israel-hamas",
    "israel hamas",
)

CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
HTML_TAG_RE = re.compile(r"<[^>]+>")


def load_feed_config_from_env() -> list[PalestineNewsFeed]:
    """Load optional feed overrides from PALESTINE_NEWS_RSS_FEEDS.

    Format: ``source_id|https://feed.url;other_source|https://feed.url``.
    When the variable is absent, the audited local defaults are used.
    """

    configured = os.getenv("PALESTINE_NEWS_RSS_FEEDS", "").strip()
    if not configured:
        return list(DEFAULT_FEEDS)

    feeds: list[PalestineNewsFeed] = []
    for raw_part in configured.replace("\n", ";").split(";"):
        part = raw_part.strip()
        if not part:
            continue
        if "|" in part:
            raw_source_id, raw_url = part.split("|", 1)
            source_id = normalize_source_id(raw_source_id)
            url = raw_url.strip()
        else:
            url = part
            source_id = normalize_source_id(urlparse(url).netloc or "custom")
        if source_id and url:
            feeds.append(PalestineNewsFeed(source_id, url))

    return feeds or list(DEFAULT_FEEDS)


def collect_palestine_news(
    feeds: list[PalestineNewsFeed] | None = None,
    limit_per_feed: int = 20,
    timeout_seconds: int = 15,
) -> PalestineNewsCollection:
    resolved_feeds = feeds or load_feed_config_from_env()
    accepted_items: list[PalestineNewsItem] = []
    fetched_count = 0
    skipped_count = 0
    error_count = 0

    for feed in resolved_feeds:
        source = OfficialRssSource([feed.url], timeout_seconds=timeout_seconds, first_per_feed=False)
        fetched_items = source.fetch(limit=max(1, int(limit_per_feed)))
        fetched_count += len(fetched_items)

        for item in fetched_items:
            if item.source == "official_rss:error" or "error" in item.tags:
                error_count += 1
                continue
            if not is_palestine_issue_item(item):
                skipped_count += 1
                continue
            accepted_items.append(news_item_to_palestine_news_item(item, feed))

    deduped = dedupe_items(accepted_items)
    deduped.sort(key=lambda item: sort_timestamp(parse_event_timestamp(item.published_at)), reverse=True)
    return PalestineNewsCollection(deduped, fetched_count, skipped_count, error_count)


def is_palestine_issue_item(item: NewsItem) -> bool:
    text = normalize_text(f"{item.title} {item.summary or ''} {item.url}")
    return is_probably_english(text) and any(keyword in text for keyword in PALESTINE_KEYWORDS)


def is_probably_english(text: str) -> bool:
    if not text.strip() or CJK_RE.search(text):
        return False

    letters = [char for char in text if char.isalpha()]
    if not letters:
        return False

    ascii_letters = [char for char in letters if "a" <= char.lower() <= "z"]
    return len(ascii_letters) / len(letters) >= 0.7


def news_item_to_palestine_news_item(item: NewsItem, feed: PalestineNewsFeed) -> PalestineNewsItem:
    summary = clean_summary(item.summary)
    source_id = normalize_source_id(feed.source_id)
    raw = {
        "topic": "free_palestine",
        "language": "en",
        "collector": "palestine_news",
        "feed_url": feed.url,
        "source_id": source_id,
        "original_source": item.source,
        "original_id": item.id,
        "tags": item.tags,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    return PalestineNewsItem(
        news_id=f"palestine-watch-{stable_id(source_id, item.title, item.url)}",
        source_id=source_id,
        source_name=source_id,
        title=clean_summary(item.title)[:500],
        url=item.url,
        summary=summary,
        published_at=item.published_at.isoformat() if item.published_at else None,
        language="en",
        topic="free_palestine",
        source_url=feed.url,
        original_source=item.source,
        original_id=item.id,
        tags=list(item.tags),
        raw=raw,
    )


def news_item_to_relay_event(item: NewsItem, feed: PalestineNewsFeed) -> PalestineNewsItem:
    """Compatibility wrapper; new storage uses PalestineNewsItem, not RelayEvent."""
    return news_item_to_palestine_news_item(item, feed)


def dedupe_items(items: list[PalestineNewsItem]) -> list[PalestineNewsItem]:
    seen: set[str] = set()
    result: list[PalestineNewsItem] = []
    for item in items:
        key = item.url or item.news_id
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def normalize_source_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized[:64]


def normalize_text(value: str) -> str:
    return clean_summary(value).lower()


def clean_summary(value: str | None) -> str:
    if not value:
        return ""
    no_tags = HTML_TAG_RE.sub(" ", value)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def parse_event_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class PalestineNewsStore:
    def __init__(self, env_file: str) -> None:
        self._settings = load_settings(env_file)
        self._table = safe_identifier(self._settings.mysql_palestine_news_table)
        self._event_table = safe_identifier(self._settings.mysql_event_table)
        self._connector = self._import_mysql_connector()
        self._conn = None
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self._create_database_if_needed()
        self._connect_database()
        self._create_table_if_needed()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def upsert_item(self, item: PalestineNewsItem) -> bool:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        sql = (
            f"INSERT INTO `{self._table}` "
            "(news_id, source_id, source_name, title, url, url_hash, summary, published_at, "
            "language, topic, source_url, original_source, original_id, tags_json, raw_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "news_id=VALUES(news_id), "
            "source_id=VALUES(source_id), "
            "source_name=VALUES(source_name), "
            "title=VALUES(title), "
            "summary=VALUES(summary), "
            "published_at=COALESCE(VALUES(published_at), published_at), "
            "language=VALUES(language), "
            "topic=VALUES(topic), "
            "source_url=VALUES(source_url), "
            "original_source=VALUES(original_source), "
            "original_id=VALUES(original_id), "
            "tags_json=VALUES(tags_json), "
            "raw_json=VALUES(raw_json), "
            "last_seen_at=CURRENT_TIMESTAMP"
        )
        values = (
            item.news_id,
            item.source_id,
            item.source_name,
            item.title,
            item.url,
            item.url_hash,
            item.summary,
            item.published_at,
            item.language,
            item.topic,
            item.source_url,
            item.original_source,
            item.original_id,
            json.dumps(item.tags, ensure_ascii=False),
            json.dumps(item.raw, ensure_ascii=False),
        )

        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, values)
                self._conn.commit()
                return cur.rowcount == 1
            finally:
                cur.close()

    def backfill_from_relay_events(self, limit: int | None = None) -> tuple[int, int]:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        sql = (
            f"SELECT event_id, source, title, url, summary, published_at, raw_json "
            f"FROM `{self._event_table}` "
            "WHERE source LIKE 'palestine_watch:%' "
            "ORDER BY id ASC"
        )
        args: tuple[int, ...] = ()
        if limit is not None and limit > 0:
            sql += " LIMIT %s"
            args = (int(limit),)

        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, args)
                rows = cur.fetchall()
            finally:
                cur.close()

        inserted = 0
        duplicate = 0
        for row in rows:
            item = self._relay_row_to_item(row)
            if self.upsert_item(item):
                inserted += 1
            else:
                duplicate += 1
        return inserted, duplicate

    def _relay_row_to_item(self, row: tuple[Any, ...]) -> PalestineNewsItem:
        raw = parse_json_object(row[6])
        source = str(row[1] or "")
        source_id = normalize_source_id(source.split(":", 1)[1] if ":" in source else source)
        tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
        return PalestineNewsItem(
            news_id=str(row[0] or f"palestine-watch-{stable_id(source_id, row[2], row[3])}"),
            source_id=source_id,
            source_name=str(raw.get("source_id") or source_id),
            title=clean_summary(str(row[2] or ""))[:500],
            url=str(row[3] or ""),
            summary=clean_summary(str(row[4] or "")),
            published_at=str(row[5]) if row[5] is not None else None,
            language=str(raw.get("language") or "en"),
            topic=str(raw.get("topic") or "free_palestine"),
            source_url=str(raw.get("feed_url") or "") or None,
            original_source=str(raw.get("original_source") or "") or None,
            original_id=str(raw.get("original_id") or "") or None,
            tags=[str(tag) for tag in tags],
            raw=raw or {
                "topic": "free_palestine",
                "language": "en",
                "collector": "palestine_news",
                "migrated_from": "t_relay_events",
            },
        )

    def _cursor(self):
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        return self._conn.cursor()

    def _create_database_if_needed(self) -> None:
        conn = self._connector.connect(
            host=self._settings.mysql_host,
            port=self._settings.mysql_port,
            user=self._settings.mysql_user,
            password=self._settings.mysql_password,
            connection_timeout=self._settings.mysql_connect_timeout_seconds,
            autocommit=True,
        )
        try:
            cur = conn.cursor()
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{self._settings.mysql_database}` CHARACTER SET utf8mb4")
            cur.close()
        finally:
            conn.close()

    def _connect_database(self) -> None:
        self._conn = self._connector.connect(
            host=self._settings.mysql_host,
            port=self._settings.mysql_port,
            user=self._settings.mysql_user,
            password=self._settings.mysql_password,
            database=self._settings.mysql_database,
            connection_timeout=self._settings.mysql_connect_timeout_seconds,
            autocommit=False,
        )

    def _create_table_if_needed(self) -> None:
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self._table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          news_id VARCHAR(128) NOT NULL,
          source_id VARCHAR(64) NOT NULL,
          source_name VARCHAR(128) NOT NULL,
          title TEXT NOT NULL,
          url TEXT NOT NULL,
          url_hash CHAR(40) NOT NULL,
          summary TEXT NULL,
          published_at VARCHAR(64) NULL,
          language VARCHAR(16) NOT NULL DEFAULT 'en',
          topic VARCHAR(64) NOT NULL DEFAULT 'free_palestine',
          source_url TEXT NULL,
          original_source VARCHAR(255) NULL,
          original_id VARCHAR(255) NULL,
          tags_json JSON NULL,
          raw_json JSON NULL,
          first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_palestine_news_hash (url_hash),
          KEY idx_palestine_news_published (published_at),
          KEY idx_palestine_news_source (source_id),
          KEY idx_palestine_news_seen (last_seen_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        cur = self._cursor()
        try:
            cur.execute(ddl)
            self._conn.commit()
        finally:
            cur.close()

    @staticmethod
    def _import_mysql_connector():
        try:
            import mysql.connector  # type: ignore
        except ImportError as exc:
            raise RuntimeError("mysql-connector-python is required. Run: pip install -e .") from exc
        return mysql.connector


def safe_identifier(value: str | None) -> str:
    candidate = (value or "t_palestine_news_items").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", candidate):
        raise ValueError(f"Unsafe SQL table identifier: {candidate}")
    return candidate


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def store_items(items: list[PalestineNewsItem], env_file: str) -> tuple[int, int]:
    store = PalestineNewsStore(env_file)
    store.initialize()
    inserted = 0
    duplicate = 0
    for item in items:
        if store.upsert_item(item):
            inserted += 1
        else:
            duplicate += 1
    store.close()
    return inserted, duplicate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect English Palestine issue news into long-term storage")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--limit", type=int, default=20, help="Maximum RSS items to inspect per feed")
    parser.add_argument("--timeout-seconds", type=int, default=15, help="RSS request timeout")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print accepted rows without writing MySQL")
    parser.add_argument(
        "--backfill-relay",
        action="store_true",
        help="Copy legacy source=palestine_watch:* rows from t_relay_events into the long-term table",
    )
    parser.add_argument(
        "--backfill-only",
        action="store_true",
        help="Run the legacy relay backfill and skip RSS collection",
    )
    parser.add_argument("--backfill-limit", type=int, default=0, help="Optional legacy relay row limit")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )

    load_env_file(args.env_file)
    if args.backfill_relay and not args.dry_run:
        store = PalestineNewsStore(args.env_file)
        store.initialize()
        backfill_inserted, backfill_duplicate = store.backfill_from_relay_events(args.backfill_limit or None)
        store.close()
        print(f"Backfilled Palestine news inserted={backfill_inserted} duplicate={backfill_duplicate}")
        if args.backfill_only:
            return 0

    collection = collect_palestine_news(limit_per_feed=args.limit, timeout_seconds=args.timeout_seconds)
    print(
        "Palestine news collection "
        f"fetched={collection.fetched_count} accepted={len(collection.items)} "
        f"skipped={collection.skipped_count} errors={collection.error_count}"
    )

    if args.dry_run:
        print(json.dumps([item_preview(item) for item in collection.items], ensure_ascii=False, indent=2))
        return 0

    inserted, duplicate = store_items(collection.items, args.env_file)
    print(f"Stored Palestine news inserted={inserted} duplicate={duplicate}")
    return 0


def event_preview(item: PalestineNewsItem) -> dict[str, str | None]:
    return item_preview(item)


def item_preview(item: PalestineNewsItem) -> dict[str, str | None]:
    return {
        "news_id": item.news_id,
        "source": item.api_source,
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at,
    }


if __name__ == "__main__":
    raise SystemExit(main())
