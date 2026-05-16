"""News-platform MySQL store — 獨立 DB，與 event_relay 不共用連線或表。"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from news_platform.author_extractor import normalize_authors
from news_platform.author_metadata import (
    AUTHOR_METHOD_LEGACY_AUTHORS_JSON,
    AUTHOR_METHOD_NONE,
    AUTHOR_STATUS_PRESENT,
    author_key,
)
from news_platform.config import NewsPlatformSettings
from news_platform.models import NewsArticle, PublicRecord
from news_platform.registry import TW_SOURCES


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredArticleHead:
    """關鍵字 worker 等批次 job 用的精簡視圖。"""

    row_id: int
    article_id: str
    title: str


@dataclass(frozen=True)
class StoredArticleTopicInput:
    """Topic worker input view for articles that already have keywords."""

    row_id: int
    article_id: str
    category: str
    title: str
    summary: str | None
    keywords_json: str | bytes | list[dict[str, Any]] | None


@dataclass(frozen=True)
class StoredArticleLlmTopicInput:
    """LLM fallback input view for articles that rule classification missed."""

    row_id: int
    article_id: str
    category: str
    title: str
    summary: str | None


@dataclass(frozen=True)
class StoredArticlePublicRecordLink:
    """Joined view of one article-to-public-record relation."""

    article_id: str
    public_record_id: str
    relation_type: str
    confidence: float
    matched_by: str
    record_type: str
    source_id: str
    title: str
    url: str | None
    occurred_at: datetime | None
    region: str | None
    metrics_json: str | bytes | dict[str, Any] | None


@dataclass(frozen=True)
class StoredArticlePublicRecordMatchInput:
    """Article row used by deterministic public-record matching."""

    row_id: int
    article_id: str
    category: str
    title: str
    summary: str | None
    published_at: datetime | None
    keywords_json: str | bytes | list[dict[str, Any]] | None
    topics_json: str | bytes | list[dict[str, Any]] | None


@dataclass(frozen=True)
class StoredPublicRecordMatchInput:
    """Public-record row used by deterministic article matching."""

    record_id: str
    source_id: str
    record_type: str
    category: str | None
    title: str
    url: str | None
    occurred_at: datetime | None
    region: str | None
    metrics_json: str | bytes | dict[str, Any] | None
    tags_json: str | bytes | list[str] | None
    raw_json: str | bytes | dict[str, Any] | None


@dataclass(frozen=True)
class StoredAuthorCoverageDaily:
    """Daily source/category byline coverage aggregate."""

    stat_date: datetime
    source_id: str
    category: str
    article_count: int
    with_author_count: int
    without_author_count: int
    coverage_rate: float


class NewsPlatformStore:
    def __init__(self, settings: NewsPlatformSettings) -> None:
        self._settings = settings
        self._article_table = settings.mysql_article_table
        self._source_table = settings.mysql_source_table
        self._public_record_table = settings.mysql_public_record_table
        self._article_record_link_table = settings.mysql_article_record_link_table
        self._author_table = settings.mysql_author_table
        self._article_author_table = settings.mysql_article_author_table
        self._author_coverage_daily_table = settings.mysql_author_coverage_daily_table
        self._connector = self._import_mysql_connector()
        self._conn = None
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self._create_database_if_needed()
        self._connect_database()
        self._create_tables_if_needed()
        self._migrate_schema()
        self._seed_sources()

    def upsert_article(self, article: NewsArticle) -> bool:
        """寫入一筆文章；若 article_id 已存在回 False（duplicate）。"""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        ttl_at = datetime.now(timezone.utc) + timedelta(days=self._settings.article_ttl_days)
        sql = (
            f"INSERT INTO `{self._article_table}` "
            "(article_id, source_id, country, category, title, url, summary, "
            "published_at, authors_json, author_extraction_status, author_extraction_method, "
            "author_extraction_confidence, author_raw_text, author_extracted_at, "
            "tags_json, raw_json, ttl_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "authors_json = CASE "
            "WHEN JSON_LENGTH(COALESCE(authors_json, JSON_ARRAY())) = 0 "
            "AND JSON_LENGTH(COALESCE(VALUES(authors_json), JSON_ARRAY())) > 0 "
            "THEN VALUES(authors_json) ELSE authors_json END, "
            "author_extraction_status = CASE "
            "WHEN VALUES(author_extraction_status) = 'present' "
            "AND COALESCE(author_extraction_status, '') <> 'present' "
            "THEN VALUES(author_extraction_status) "
            "WHEN author_extraction_status IS NULL THEN VALUES(author_extraction_status) "
            "ELSE author_extraction_status END, "
            "author_extraction_method = CASE "
            "WHEN VALUES(author_extraction_status) = 'present' "
            "AND COALESCE(author_extraction_status, '') <> 'present' "
            "THEN VALUES(author_extraction_method) "
            "WHEN author_extraction_method IS NULL THEN VALUES(author_extraction_method) "
            "ELSE author_extraction_method END, "
            "author_extraction_confidence = CASE "
            "WHEN VALUES(author_extraction_status) = 'present' "
            "AND COALESCE(author_extraction_status, '') <> 'present' "
            "THEN VALUES(author_extraction_confidence) "
            "WHEN author_extraction_confidence IS NULL THEN VALUES(author_extraction_confidence) "
            "ELSE author_extraction_confidence END, "
            "author_raw_text = CASE "
            "WHEN VALUES(author_extraction_status) = 'present' "
            "AND COALESCE(author_extraction_status, '') <> 'present' "
            "THEN VALUES(author_raw_text) "
            "WHEN author_raw_text IS NULL THEN VALUES(author_raw_text) "
            "ELSE author_raw_text END, "
            "author_extracted_at = CASE "
            "WHEN VALUES(author_extraction_status) = 'present' "
            "AND COALESCE(author_extraction_status, '') <> 'present' "
            "THEN VALUES(author_extracted_at) "
            "WHEN author_extracted_at IS NULL THEN VALUES(author_extracted_at) "
            "ELSE author_extracted_at END"
        )
        published = (
            article.published_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if article.published_at
            else None
        )
        extracted_at = (
            article.author_extracted_at.astimezone(timezone.utc)
            if article.author_extracted_at
            else datetime.now(timezone.utc)
        )
        author_status = str(article.author_extraction_status or "")
        author_method = str(article.author_extraction_method or AUTHOR_METHOD_NONE)
        author_confidence = article.author_extraction_confidence
        if article.authors and author_status != AUTHOR_STATUS_PRESENT:
            author_status = AUTHOR_STATUS_PRESENT
            if author_method == AUTHOR_METHOD_NONE:
                author_method = AUTHOR_METHOD_LEGACY_AUTHORS_JSON
            if author_confidence is None:
                author_confidence = 1.0
        values = (
            article.article_id,
            article.source_id,
            article.country,
            article.category,
            article.title,
            article.url,
            article.summary,
            published,
            json.dumps(list(article.authors), ensure_ascii=False),
            author_status,
            author_method,
            author_confidence,
            article.author_raw_text,
            extracted_at.strftime("%Y-%m-%d %H:%M:%S"),
            json.dumps(list(article.tags), ensure_ascii=False),
            json.dumps(article.raw, ensure_ascii=False),
            ttl_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, values)
                rowcount = int(getattr(cur, "rowcount", 0) or 0)
                self._upsert_article_author_rows(cur, article)
                self._conn.commit()
                return rowcount == 1
            except self._connector.IntegrityError:
                self._conn.rollback()
                return False
            finally:
                cur.close()

    def upsert_public_record(self, record: PublicRecord) -> bool:
        """Insert or refresh one structured official record."""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        sql = (
            f"INSERT INTO `{self._public_record_table}` "
            "(record_id, source_id, record_type, country, category, title, url, "
            "occurred_at, region, metrics_json, tags_json, raw_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "source_id=VALUES(source_id), record_type=VALUES(record_type), "
            "country=VALUES(country), category=VALUES(category), title=VALUES(title), "
            "url=VALUES(url), occurred_at=VALUES(occurred_at), region=VALUES(region), "
            "metrics_json=VALUES(metrics_json), tags_json=VALUES(tags_json), "
            "raw_json=VALUES(raw_json), updated_at=CURRENT_TIMESTAMP"
        )
        occurred = (
            record.occurred_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if record.occurred_at
            else None
        )
        values = (
            record.record_id,
            record.source_id,
            record.record_type,
            record.country,
            record.category,
            record.title,
            record.url,
            occurred,
            record.region,
            json.dumps(record.metrics, ensure_ascii=False),
            json.dumps(list(record.tags), ensure_ascii=False),
            json.dumps(record.raw, ensure_ascii=False),
        )

        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, values)
                rowcount = int(getattr(cur, "rowcount", 0) or 0)
                self._conn.commit()
                return rowcount == 1
            finally:
                cur.close()

    def link_article_public_record(
        self,
        *,
        article_id: str,
        public_record_id: str,
        relation_type: str = "related",
        confidence: float = 1.0,
        matched_by: str = "manual",
        evidence: dict[str, Any] | list[Any] | None = None,
    ) -> bool:
        """Create or update a relation between an article and a public record."""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        bounded_confidence = max(0.0, min(1.0, float(confidence)))
        sql = (
            f"INSERT INTO `{self._article_record_link_table}` "
            "(article_id, public_record_id, relation_type, confidence, matched_by, evidence_json) "
            "VALUES (%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "confidence=VALUES(confidence), matched_by=VALUES(matched_by), "
            "evidence_json=VALUES(evidence_json)"
        )
        values = (
            article_id,
            public_record_id,
            str(relation_type or "related")[:32],
            round(bounded_confidence, 4),
            str(matched_by or "manual")[:32],
            json.dumps(evidence or {}, ensure_ascii=False),
        )

        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, values)
                rowcount = int(getattr(cur, "rowcount", 0) or 0)
                self._conn.commit()
                return rowcount == 1
            finally:
                cur.close()

    def upsert_article_author_relations(
        self,
        *,
        article_id: str,
        source_id: str,
        published_at: datetime | None,
        authors: list[str],
        extraction_method: str = AUTHOR_METHOD_LEGACY_AUTHORS_JSON,
        confidence: float = 1.0,
        raw_text: str | None = None,
    ) -> int:
        """Create normalized author rows and article-author links for one article."""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        article = NewsArticle(
            article_id=article_id,
            source_id=source_id,
            country="TW",
            category="",
            title="",
            url="",
            published_at=published_at,
            summary=None,
            authors=authors,
            author_extraction_status=AUTHOR_STATUS_PRESENT if authors else "",
            author_extraction_method=extraction_method,
            author_extraction_confidence=confidence,
            author_raw_text=raw_text,
        )
        with self._lock:
            cur = self._cursor()
            try:
                count = self._upsert_article_author_rows(cur, article)
                self._conn.commit()
                return count
            finally:
                cur.close()

    def fetch_public_record_links_for_article(
        self,
        article_id: str,
        limit: int = 100,
    ) -> list[StoredArticlePublicRecordLink]:
        """Return public records linked to one article."""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        safe_limit = max(1, int(limit))
        sql = (
            f"SELECT l.article_id, l.public_record_id, l.relation_type, l.confidence, "
            f"l.matched_by, r.record_type, r.source_id, r.title, r.url, "
            f"r.occurred_at, r.region, r.metrics_json "
            f"FROM `{self._article_record_link_table}` l "
            f"JOIN `{self._public_record_table}` r ON r.record_id = l.public_record_id "
            "WHERE l.article_id = %s "
            "ORDER BY l.confidence DESC, r.occurred_at DESC, l.id DESC LIMIT %s"
        )
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, (article_id, safe_limit))
                rows = cur.fetchall()
            finally:
                cur.close()
        return [
            StoredArticlePublicRecordLink(
                article_id=str(r[0]),
                public_record_id=str(r[1]),
                relation_type=str(r[2]),
                confidence=float(r[3]),
                matched_by=str(r[4]),
                record_type=str(r[5]),
                source_id=str(r[6]),
                title=str(r[7] or ""),
                url=None if r[8] is None else str(r[8]),
                occurred_at=r[9],
                region=None if r[10] is None else str(r[10]),
                metrics_json=r[11],
            )
            for r in rows
        ]

    def fetch_articles_for_public_record_matching(
        self,
        *,
        limit: int = 200,
        lookback_days: int = 14,
        categories: tuple[str, ...] = ("politics", "society"),
    ) -> list[StoredArticlePublicRecordMatchInput]:
        """Return recent article rows eligible for article-to-record matching."""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        safe_limit = max(1, int(limit))
        safe_days = max(1, int(lookback_days))
        safe_categories = tuple(dict.fromkeys(str(c).strip() for c in categories if str(c).strip()))
        if not safe_categories:
            return []
        placeholders = ",".join(["%s"] * len(safe_categories))
        sql = (
            f"SELECT id, article_id, category, title, summary, published_at, keywords_json, topics_json "
            f"FROM `{self._article_table}` "
            f"WHERE category IN ({placeholders}) "
            "AND (published_at IS NULL OR published_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY)) "
            "ORDER BY published_at DESC, id DESC LIMIT %s"
        )
        params = (*safe_categories, safe_days, safe_limit)
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, params)
                rows = cur.fetchall()
            finally:
                cur.close()
        return [
            StoredArticlePublicRecordMatchInput(
                row_id=int(r[0]),
                article_id=str(r[1]),
                category=str(r[2] or ""),
                title=str(r[3] or ""),
                summary=None if r[4] is None else str(r[4]),
                published_at=r[5],
                keywords_json=r[6],
                topics_json=r[7],
            )
            for r in rows
        ]

    def fetch_public_records_for_matching(
        self,
        *,
        limit: int = 1000,
        lookback_days: int = 45,
        categories: tuple[str, ...] | None = ("politics", "society"),
        record_types: tuple[str, ...] | None = None,
    ) -> list[StoredPublicRecordMatchInput]:
        """Return recent structured records eligible for article matching."""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        safe_limit = max(1, int(limit))
        safe_days = max(1, int(lookback_days))
        clauses = [
            "(occurred_at IS NULL OR occurred_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY))"
        ]
        params: list[Any] = [safe_days]

        if categories is not None:
            safe_categories = tuple(dict.fromkeys(str(c).strip() for c in categories if str(c).strip()))
            if safe_categories:
                placeholders = ",".join(["%s"] * len(safe_categories))
                clauses.append(f"(category IS NULL OR category IN ({placeholders}))")
                params.extend(safe_categories)

        if record_types is not None:
            safe_types = tuple(dict.fromkeys(str(t).strip() for t in record_types if str(t).strip()))
            if safe_types:
                placeholders = ",".join(["%s"] * len(safe_types))
                clauses.append(f"record_type IN ({placeholders})")
                params.extend(safe_types)

        sql = (
            f"SELECT record_id, source_id, record_type, category, title, url, occurred_at, "
            f"region, metrics_json, tags_json, raw_json "
            f"FROM `{self._public_record_table}` "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY occurred_at DESC, id DESC LIMIT %s"
        )
        params.append(safe_limit)

        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
            finally:
                cur.close()
        return [
            StoredPublicRecordMatchInput(
                record_id=str(r[0]),
                source_id=str(r[1]),
                record_type=str(r[2]),
                category=None if r[3] is None else str(r[3]),
                title=str(r[4] or ""),
                url=None if r[5] is None else str(r[5]),
                occurred_at=r[6],
                region=None if r[7] is None else str(r[7]),
                metrics_json=r[8],
                tags_json=r[9],
                raw_json=r[10],
            )
            for r in rows
        ]

    def fetch_articles_missing_keywords(self, limit: int = 100) -> list[StoredArticleHead]:
        """挑出尚未抽過關鍵字的文章。供關鍵字 worker 批次處理。"""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        safe_limit = max(1, int(limit))
        sql = (
            f"SELECT id, article_id, title FROM `{self._article_table}` "
            "WHERE keywords_json IS NULL "
            "ORDER BY id ASC LIMIT %s"
        )
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, (safe_limit,))
                rows = cur.fetchall()
            finally:
                cur.close()
        return [
            StoredArticleHead(row_id=int(r[0]), article_id=str(r[1]), title=str(r[2] or ""))
            for r in rows
        ]

    def update_keywords(self, row_id: int, keywords: list[tuple[str, float]]) -> None:
        """寫回單一文章的關鍵字。空 list 也會寫入（標記已處理過，避免反覆重抽）。"""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        payload = [{"kw": kw, "score": round(float(score), 6)} for kw, score in keywords]
        sql = (
            f"UPDATE `{self._article_table}` SET keywords_json = %s WHERE id = %s"
        )
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, (json.dumps(payload, ensure_ascii=False), int(row_id)))
                self._conn.commit()
            finally:
                cur.close()

    def fetch_articles_missing_topics(self, limit: int = 200) -> list[StoredArticleTopicInput]:
        """Pick articles that have keywords but no topic classification yet."""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        safe_limit = max(1, int(limit))
        sql = (
            f"SELECT id, article_id, category, title, summary, keywords_json FROM `{self._article_table}` "
            "WHERE topics_json IS NULL AND keywords_json IS NOT NULL "
            "ORDER BY published_at DESC, id DESC LIMIT %s"
        )
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, (safe_limit,))
                rows = cur.fetchall()
            finally:
                cur.close()
        return [
            StoredArticleTopicInput(
                row_id=int(r[0]),
                article_id=str(r[1]),
                category=str(r[2] or ""),
                title=str(r[3] or ""),
                summary=None if r[4] is None else str(r[4]),
                keywords_json=r[5],
            )
            for r in rows
        ]

    def update_article_topics(
        self,
        row_id: int,
        topics: list[dict[str, object]],
        *,
        classified_by: str = "rule",
    ) -> None:
        """Write topic classification for one article."""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        sql = (
            f"UPDATE `{self._article_table}` "
            "SET topics_json = %s, topic_classified_by = %s, topic_classified_at = UTC_TIMESTAMP() "
            "WHERE id = %s"
        )
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(
                    sql,
                    (
                        json.dumps(topics, ensure_ascii=False),
                        str(classified_by or "rule")[:16],
                        int(row_id),
                    ),
                )
                self._conn.commit()
            finally:
                cur.close()

    def fetch_articles_empty_topics(self, limit: int = 50) -> list[StoredArticleLlmTopicInput]:
        """Pick rule fallback rows for optional LLM refinement."""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        safe_limit = max(1, int(limit))
        sql = (
            f"SELECT id, article_id, category, title, summary FROM `{self._article_table}` "
            "WHERE topics_json IS NOT NULL "
            "AND ("
            "JSON_LENGTH(topics_json) = 0 "
            "OR JSON_UNQUOTE(JSON_EXTRACT(topics_json, '$[0].topic_id')) "
            "IN ('general_social_news', 'general_politics_news')"
            ") "
            "AND (topic_classified_by IS NULL OR topic_classified_by = 'rule') "
            "ORDER BY published_at DESC, id DESC LIMIT %s"
        )
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, (safe_limit,))
                rows = cur.fetchall()
            finally:
                cur.close()
        return [
            StoredArticleLlmTopicInput(
                row_id=int(r[0]),
                article_id=str(r[1]),
                category=str(r[2] or ""),
                title=str(r[3] or ""),
                summary=None if r[4] is None else str(r[4]),
            )
            for r in rows
        ]

    def purge_expired(self) -> int:
        """刪除 ttl_at 已過期的 row。回傳刪除筆數。"""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        sql = f"DELETE FROM `{self._article_table}` WHERE ttl_at < UTC_TIMESTAMP()"
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql)
                deleted = cur.rowcount or 0
                self._conn.commit()
                return int(deleted)
            finally:
                cur.close()

    def refresh_author_coverage_daily(self, *, lookback_days: int = 30) -> int:
        """Refresh daily source/category author coverage aggregates."""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        safe_days = max(1, int(lookback_days))
        sql = (
            f"INSERT INTO `{self._author_coverage_daily_table}` "
            "(stat_date, source_id, category, article_count, with_author_count, without_author_count, "
            "no_author_metadata_count, no_detail_fetched_count, parser_not_supported_count, "
            "parse_failed_count, low_confidence_count, coverage_rate, generated_at) "
            "SELECT "
            "DATE(DATE_ADD(COALESCE(published_at, fetched_at), INTERVAL 8 HOUR)) AS stat_date, "
            "source_id, category, COUNT(*) AS article_count, "
            "SUM(CASE WHEN author_extraction_status = 'present' THEN 1 ELSE 0 END) AS with_author_count, "
            "SUM(CASE WHEN COALESCE(author_extraction_status, '') <> 'present' THEN 1 ELSE 0 END) AS without_author_count, "
            "SUM(CASE WHEN author_extraction_status = 'no_author_metadata' THEN 1 ELSE 0 END) AS no_author_metadata_count, "
            "SUM(CASE WHEN author_extraction_status = 'no_detail_fetched' THEN 1 ELSE 0 END) AS no_detail_fetched_count, "
            "SUM(CASE WHEN author_extraction_status = 'parser_not_supported' THEN 1 ELSE 0 END) AS parser_not_supported_count, "
            "SUM(CASE WHEN author_extraction_status = 'parse_failed' THEN 1 ELSE 0 END) AS parse_failed_count, "
            "SUM(CASE WHEN author_extraction_status = 'low_confidence' THEN 1 ELSE 0 END) AS low_confidence_count, "
            "ROUND(SUM(CASE WHEN author_extraction_status = 'present' THEN 1 ELSE 0 END) / COUNT(*), 5) AS coverage_rate, "
            "UTC_TIMESTAMP() "
            f"FROM `{self._article_table}` "
            "WHERE COALESCE(published_at, fetched_at) >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY) "
            "GROUP BY stat_date, source_id, category "
            "ON DUPLICATE KEY UPDATE "
            "article_count=VALUES(article_count), "
            "with_author_count=VALUES(with_author_count), "
            "without_author_count=VALUES(without_author_count), "
            "no_author_metadata_count=VALUES(no_author_metadata_count), "
            "no_detail_fetched_count=VALUES(no_detail_fetched_count), "
            "parser_not_supported_count=VALUES(parser_not_supported_count), "
            "parse_failed_count=VALUES(parse_failed_count), "
            "low_confidence_count=VALUES(low_confidence_count), "
            "coverage_rate=VALUES(coverage_rate), "
            "generated_at=VALUES(generated_at)"
        )
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, (safe_days,))
                rowcount = int(getattr(cur, "rowcount", 0) or 0)
                self._conn.commit()
                return rowcount
            finally:
                cur.close()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _upsert_article_author_rows(self, cur, article: NewsArticle) -> int:
        authors = normalize_authors(article.authors)
        if not authors:
            return 0

        published = (
            article.published_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if article.published_at
            else None
        )
        method = str(article.author_extraction_method or AUTHOR_METHOD_LEGACY_AUTHORS_JSON)[:32]
        confidence = round(
            max(0.0, min(1.0, float(article.author_extraction_confidence or 1.0))),
            4,
        )
        raw_text = article.author_raw_text
        relation_count = 0

        for ordinal, display_name in enumerate(authors, start=1):
            normalized_name = " ".join(display_name.split())
            key = author_key(article.source_id, normalized_name)
            cur.execute(
                (
                    f"INSERT INTO `{self._author_table}` "
                    "(author_key, source_id, display_name, normalized_name, author_type, aliases_json, "
                    "first_seen_at, last_seen_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE "
                    "display_name=VALUES(display_name), "
                    "last_seen_at=CASE "
                    "WHEN last_seen_at IS NULL THEN VALUES(last_seen_at) "
                    "WHEN VALUES(last_seen_at) IS NULL THEN last_seen_at "
                    "WHEN VALUES(last_seen_at) > last_seen_at THEN VALUES(last_seen_at) "
                    "ELSE last_seen_at END"
                ),
                (
                    key,
                    article.source_id,
                    display_name,
                    normalized_name,
                    "reporter",
                    json.dumps([], ensure_ascii=False),
                    published,
                    published,
                ),
            )
            cur.execute(
                f"SELECT id FROM `{self._author_table}` WHERE author_key = %s",
                (key,),
            )
            row = cur.fetchone()
            if not row:
                continue
            author_id = int(row[0])
            cur.execute(
                (
                    f"INSERT INTO `{self._article_author_table}` "
                    "(article_id, author_id, role, ordinal, extraction_method, confidence, raw_text) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE "
                    "ordinal=VALUES(ordinal), extraction_method=VALUES(extraction_method), "
                    "confidence=VALUES(confidence), raw_text=VALUES(raw_text)"
                ),
                (
                    article.article_id,
                    author_id,
                    "reporter",
                    ordinal,
                    method,
                    confidence,
                    raw_text,
                ),
            )
            relation_count += 1
        return relation_count

    def _ensure_connection(self) -> None:
        if self._conn is None:
            self._connect_database()
            return
        try:
            self._conn.ping(reconnect=True, attempts=2, delay=1)
        except Exception as exc:
            logger.warning("MySQL connection unavailable; reconnecting: %s", exc)
            try:
                self._conn.close()
            except Exception:
                pass
            self._connect_database()

    def _cursor(self):
        self._ensure_connection()
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
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{self._settings.mysql_database}` CHARACTER SET utf8mb4"
            )
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

    def _create_tables_if_needed(self) -> None:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        ddl_sources = f"""
        CREATE TABLE IF NOT EXISTS `{self._source_table}` (
          source_id VARCHAR(32) NOT NULL,
          name VARCHAR(128) NOT NULL,
          country VARCHAR(8) NOT NULL,
          political_camp VARCHAR(32) NOT NULL,
          china_alignment VARCHAR(32) NOT NULL,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (source_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_articles = f"""
        CREATE TABLE IF NOT EXISTS `{self._article_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          article_id VARCHAR(64) NOT NULL,
          source_id VARCHAR(32) NOT NULL,
          country VARCHAR(8) NOT NULL,
          category VARCHAR(32) NOT NULL,
          title TEXT NOT NULL,
          url TEXT NOT NULL,
          summary TEXT NULL,
          published_at DATETIME NULL,
          authors_json JSON NULL,
          author_extraction_status VARCHAR(32) NULL,
          author_extraction_method VARCHAR(32) NULL,
          author_extraction_confidence DECIMAL(5,4) NULL,
          author_raw_text TEXT NULL,
          author_extracted_at DATETIME NULL,
          tags_json JSON NULL,
          raw_json JSON NULL,
          keywords_json JSON NULL,
          topics_json JSON NULL,
          topic_classified_by VARCHAR(16) NULL,
          topic_classified_at DATETIME NULL,
          fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          ttl_at DATETIME NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uq_article_id (article_id),
          KEY idx_country_category_pub (country, category, published_at),
          KEY idx_source_pub (source_id, published_at),
          KEY idx_ttl (ttl_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_public_records = f"""
        CREATE TABLE IF NOT EXISTS `{self._public_record_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          record_id VARCHAR(96) NOT NULL,
          source_id VARCHAR(64) NOT NULL,
          record_type VARCHAR(64) NOT NULL,
          country VARCHAR(8) NOT NULL,
          category VARCHAR(32) NULL,
          title TEXT NOT NULL,
          url TEXT NULL,
          occurred_at DATETIME NULL,
          region VARCHAR(128) NULL,
          metrics_json JSON NULL,
          tags_json JSON NULL,
          raw_json JSON NULL,
          fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_record_id (record_id),
          KEY idx_record_type_occurred (record_type, occurred_at),
          KEY idx_source_type (source_id, record_type),
          KEY idx_category_occurred (category, occurred_at),
          KEY idx_region_occurred (region, occurred_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_article_record_links = f"""
        CREATE TABLE IF NOT EXISTS `{self._article_record_link_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          article_id VARCHAR(64) NOT NULL,
          public_record_id VARCHAR(96) NOT NULL,
          relation_type VARCHAR(32) NOT NULL DEFAULT 'related',
          confidence DECIMAL(5,4) NOT NULL DEFAULT 1.0000,
          matched_by VARCHAR(32) NOT NULL DEFAULT 'manual',
          evidence_json JSON NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_article_record_relation (article_id, public_record_id, relation_type),
          KEY idx_article_id (article_id),
          KEY idx_public_record_id (public_record_id),
          KEY idx_relation_type (relation_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_authors = f"""
        CREATE TABLE IF NOT EXISTS `{self._author_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          author_key VARCHAR(96) NOT NULL,
          source_id VARCHAR(32) NOT NULL,
          display_name VARCHAR(128) NOT NULL,
          normalized_name VARCHAR(128) NOT NULL,
          author_type VARCHAR(32) NOT NULL DEFAULT 'reporter',
          aliases_json JSON NULL,
          profile_url TEXT NULL,
          first_seen_at DATETIME NULL,
          last_seen_at DATETIME NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_author_key (author_key),
          UNIQUE KEY uq_source_author_name (source_id, normalized_name),
          KEY idx_source_id (source_id),
          KEY idx_normalized_name (normalized_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_article_authors = f"""
        CREATE TABLE IF NOT EXISTS `{self._article_author_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          article_id VARCHAR(64) NOT NULL,
          author_id BIGINT NOT NULL,
          role VARCHAR(32) NOT NULL DEFAULT 'reporter',
          ordinal SMALLINT NOT NULL DEFAULT 1,
          extraction_method VARCHAR(32) NOT NULL,
          confidence DECIMAL(5,4) NOT NULL DEFAULT 1.0000,
          raw_text TEXT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_article_author_role (article_id, author_id, role),
          KEY idx_article_id (article_id),
          KEY idx_author_id (author_id),
          KEY idx_role (role),
          KEY idx_extraction_method (extraction_method)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_author_coverage_daily = f"""
        CREATE TABLE IF NOT EXISTS `{self._author_coverage_daily_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          stat_date DATE NOT NULL,
          source_id VARCHAR(32) NOT NULL,
          category VARCHAR(32) NOT NULL,
          article_count INT NOT NULL DEFAULT 0,
          with_author_count INT NOT NULL DEFAULT 0,
          without_author_count INT NOT NULL DEFAULT 0,
          no_author_metadata_count INT NOT NULL DEFAULT 0,
          no_detail_fetched_count INT NOT NULL DEFAULT 0,
          parser_not_supported_count INT NOT NULL DEFAULT 0,
          parse_failed_count INT NOT NULL DEFAULT 0,
          low_confidence_count INT NOT NULL DEFAULT 0,
          coverage_rate DECIMAL(6,5) NOT NULL DEFAULT 0.00000,
          generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_source_category_day (stat_date, source_id, category),
          KEY idx_source_date (source_id, stat_date),
          KEY idx_category_date (category, stat_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """

        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(ddl_sources)
                cur.execute(ddl_articles)
                cur.execute(ddl_public_records)
                cur.execute(ddl_article_record_links)
                cur.execute(ddl_authors)
                cur.execute(ddl_article_authors)
                cur.execute(ddl_author_coverage_daily)
                self._conn.commit()
            finally:
                cur.close()

    def _migrate_schema(self) -> None:
        """為早期版本的 DB 補上後加的 column；不影響全新建表。"""
        # Add missing columns for databases created by older deployments.
        self._ensure_column(
            table=self._article_table,
            column="authors_json",
            ddl_clause="ADD COLUMN authors_json JSON NULL AFTER published_at",
        )
        self._ensure_column(
            table=self._article_table,
            column="author_extraction_status",
            ddl_clause="ADD COLUMN author_extraction_status VARCHAR(32) NULL AFTER authors_json",
        )
        self._ensure_column(
            table=self._article_table,
            column="author_extraction_method",
            ddl_clause="ADD COLUMN author_extraction_method VARCHAR(32) NULL AFTER author_extraction_status",
        )
        self._ensure_column(
            table=self._article_table,
            column="author_extraction_confidence",
            ddl_clause="ADD COLUMN author_extraction_confidence DECIMAL(5,4) NULL AFTER author_extraction_method",
        )
        self._ensure_column(
            table=self._article_table,
            column="author_raw_text",
            ddl_clause="ADD COLUMN author_raw_text TEXT NULL AFTER author_extraction_confidence",
        )
        self._ensure_column(
            table=self._article_table,
            column="author_extracted_at",
            ddl_clause="ADD COLUMN author_extracted_at DATETIME NULL AFTER author_raw_text",
        )
        self._ensure_column(
            table=self._article_table,
            column="keywords_json",
            ddl_clause="ADD COLUMN keywords_json JSON NULL AFTER raw_json",
        )
        self._ensure_column(
            table=self._article_table,
            column="topics_json",
            ddl_clause="ADD COLUMN topics_json JSON NULL AFTER keywords_json",
        )
        self._ensure_column(
            table=self._article_table,
            column="topic_classified_by",
            ddl_clause="ADD COLUMN topic_classified_by VARCHAR(16) NULL AFTER topics_json",
        )
        self._ensure_column(
            table=self._article_table,
            column="topic_classified_at",
            ddl_clause="ADD COLUMN topic_classified_at DATETIME NULL AFTER topic_classified_by",
        )

    def _ensure_column(self, *, table: str, column: str, ddl_clause: str) -> None:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        check_sql = (
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(check_sql, (self._settings.mysql_database, table, column))
                exists = (cur.fetchone() or (0,))[0] > 0
                if not exists:
                    cur.execute(f"ALTER TABLE `{table}` {ddl_clause}")
                    self._conn.commit()
                    logger.info("Schema migrated: %s.%s added", table, column)
            finally:
                cur.close()

    def _seed_sources(self) -> None:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        sql = (
            f"INSERT INTO `{self._source_table}` "
            "(source_id, name, country, political_camp, china_alignment) "
            "VALUES (%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "name=VALUES(name), country=VALUES(country), "
            "political_camp=VALUES(political_camp), "
            "china_alignment=VALUES(china_alignment)"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                for meta in TW_SOURCES:
                    cur.execute(
                        sql,
                        (
                            meta.source_id,
                            meta.name,
                            meta.country,
                            meta.political_camp,
                            meta.china_alignment,
                        ),
                    )
                self._conn.commit()
            finally:
                cur.close()

    @staticmethod
    def _import_mysql_connector():
        try:
            import mysql.connector  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "mysql-connector-python is required. Run: pip install mysql-connector-python"
            ) from exc
        return mysql.connector
