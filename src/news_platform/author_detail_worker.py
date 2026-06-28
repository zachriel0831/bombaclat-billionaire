"""Bounded article-detail author enrichment for the news platform."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from news_platform.article_detail_author_extractor import (
    ArticleDetailAuthorExtractor,
    ArticleDetailAuthorResult,
)
from news_platform.author_metadata import (
    AUTHOR_METHOD_ARTICLE_DETAIL,
    AUTHOR_STATUS_LOW_CONFIDENCE,
    AUTHOR_STATUS_NO_AUTHOR_METADATA,
    AUTHOR_STATUS_NO_DETAIL_FETCHED,
    AUTHOR_STATUS_PARSE_FAILED,
    AUTHOR_STATUS_PARSER_NOT_SUPPORTED,
    AUTHOR_STATUS_PRESENT,
)
from news_platform.http_client import http_get_bytes
from news_platform.store import NewsPlatformStore


DEFAULT_DETAIL_AUTHOR_SOURCES = (
    "cna",
    "storm",
    "newtalk",
    "ltn",
    "ettoday",
    "tvbs",
    "ebc",
    "ctee",
    "pts",
)
DEFAULT_LOOP_ELIGIBLE_STATUSES = (
    AUTHOR_STATUS_NO_DETAIL_FETCHED,
    AUTHOR_STATUS_PARSER_NOT_SUPPORTED,
)
DEFAULT_MANUAL_ELIGIBLE_STATUSES = (
    AUTHOR_STATUS_NO_DETAIL_FETCHED,
    AUTHOR_STATUS_PARSER_NOT_SUPPORTED,
    AUTHOR_STATUS_LOW_CONFIDENCE,
)
SOURCE_VERIFY_SSL = {
    "ettoday": False,
}


@dataclass(frozen=True)
class ArticleDetailAuthorCandidate:
    row_id: int
    article_id: str
    source_id: str
    url: str
    published_at: datetime | None


@dataclass
class ArticleDetailAuthorWorkerResult:
    candidates: int = 0
    present: int = 0
    no_author_metadata: int = 0
    low_confidence: int = 0
    parse_failed: int = 0
    updated: int = 0
    relations: int = 0
    failed: int = 0
    dry_run: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)

    def record_status(self, status: str) -> None:
        self.status_counts[status] = self.status_counts.get(status, 0) + 1
        if status == AUTHOR_STATUS_PRESENT:
            self.present += 1
        elif status == AUTHOR_STATUS_NO_AUTHOR_METADATA:
            self.no_author_metadata += 1
        elif status == AUTHOR_STATUS_LOW_CONFIDENCE:
            self.low_confidence += 1
        elif status == AUTHOR_STATUS_PARSE_FAILED:
            self.parse_failed += 1

    def as_dict(self) -> dict[str, int | dict[str, int]]:
        return {
            "candidates": self.candidates,
            "present": self.present,
            "no_author_metadata": self.no_author_metadata,
            "low_confidence": self.low_confidence,
            "parse_failed": self.parse_failed,
            "updated": self.updated,
            "relations": self.relations,
            "failed": self.failed,
            "dry_run": self.dry_run,
            "status_counts": dict(self.status_counts),
        }


class ArticleDetailAuthorWorker:
    """Fetch article detail pages for rows still missing reporter names."""

    def __init__(
        self,
        store: NewsPlatformStore,
        *,
        extractor: ArticleDetailAuthorExtractor | None = None,
        sources: Iterable[str] = DEFAULT_DETAIL_AUTHOR_SOURCES,
        statuses: Iterable[str] = DEFAULT_LOOP_ELIGIBLE_STATUSES,
        batch_size: int = 30,
        timeout_seconds: int = 10,
        sleep_seconds: float = 0.05,
        dry_run: bool = False,
    ) -> None:
        self.store = store
        self.extractor = extractor or ArticleDetailAuthorExtractor()
        self.sources = tuple(dict.fromkeys(source.strip().lower() for source in sources if source.strip()))
        self.statuses = tuple(dict.fromkeys(status.strip() for status in statuses if status.strip()))
        self.batch_size = max(1, int(batch_size))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.sleep_seconds = max(0.0, float(sleep_seconds))
        self.dry_run = bool(dry_run)

    def run_once(self) -> ArticleDetailAuthorWorkerResult:
        result = ArticleDetailAuthorWorkerResult()
        candidates = self.fetch_candidates()
        result.candidates = len(candidates)
        for index, candidate in enumerate(candidates, start=1):
            try:
                payload = http_get_bytes(
                    candidate.url,
                    timeout=self.timeout_seconds,
                    verify_ssl=SOURCE_VERIFY_SSL.get(candidate.source_id, True),
                )
                author_result = self.extractor.extract(
                    payload,
                    source_id=candidate.source_id,
                    url=candidate.url,
                )
            except Exception:
                author_result = ArticleDetailAuthorResult(
                    authors=[],
                    status=AUTHOR_STATUS_PARSE_FAILED,
                    method=AUTHOR_METHOD_ARTICLE_DETAIL,
                    confidence=None,
                    raw_text=None,
                )

            result.record_status(author_result.status)
            if self.dry_run:
                result.dry_run += 1
            else:
                try:
                    updated = self.update_article_author_result(candidate.row_id, author_result)
                    if updated:
                        result.updated += 1
                        if author_result.authors:
                            result.relations += self.store.upsert_article_author_relations(
                                article_id=candidate.article_id,
                                source_id=candidate.source_id,
                                published_at=candidate.published_at,
                                authors=author_result.authors,
                                extraction_method=AUTHOR_METHOD_ARTICLE_DETAIL,
                                confidence=author_result.confidence or 0.0,
                                raw_text=author_result.raw_text,
                            )
                except Exception:
                    result.failed += 1

            if index < len(candidates) and self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)
        return result

    def fetch_candidates(self) -> list[ArticleDetailAuthorCandidate]:
        if not self.sources:
            return []
        source_placeholders = ",".join(["%s"] * len(self.sources))
        if self.statuses:
            status_placeholders = ",".join(["%s"] * len(self.statuses))
            status_predicate = (
                f"(author_extraction_status IS NULL OR author_extraction_status IN ({status_placeholders}))"
            )
            status_params: tuple[str, ...] = self.statuses
        else:
            status_predicate = "author_extraction_status IS NULL"
            status_params = ()
        sql = (
            f"SELECT id, article_id, source_id, url, published_at "
            f"FROM `{self.store._settings.mysql_article_table}` "
            "WHERE JSON_LENGTH(COALESCE(authors_json, JSON_ARRAY())) = 0 "
            "AND COALESCE(author_extraction_status, '') <> 'present' "
            f"AND source_id IN ({source_placeholders}) "
            f"AND {status_predicate} "
            "AND url IS NOT NULL AND url <> '' "
            "ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC "
            "LIMIT %s"
        )
        params = tuple(self.sources + status_params + (self.batch_size,))
        cur = self.store._cursor()
        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
        finally:
            cur.close()

        return [
            ArticleDetailAuthorCandidate(
                row_id=int(row[0]),
                article_id=str(row[1]),
                source_id=str(row[2]).lower(),
                url=str(row[3]),
                published_at=row[4],
            )
            for row in rows
        ]

    def update_article_author_result(
        self,
        row_id: int,
        result: ArticleDetailAuthorResult,
    ) -> bool:
        authors_json = json.dumps(result.authors, ensure_ascii=False)
        sql = (
            f"UPDATE `{self.store._settings.mysql_article_table}` "
            "SET authors_json=%s, "
            "author_extraction_status=%s, "
            "author_extraction_method=%s, "
            "author_extraction_confidence=%s, "
            "author_raw_text=CASE WHEN %s IS NOT NULL THEN %s ELSE author_raw_text END, "
            "author_extracted_at=UTC_TIMESTAMP() "
            "WHERE id=%s "
            "AND JSON_LENGTH(COALESCE(authors_json, JSON_ARRAY())) = 0 "
            "AND COALESCE(author_extraction_status, '') <> 'present'"
        )
        cur = self.store._cursor()
        try:
            cur.execute(
                sql,
                (
                    authors_json,
                    result.status,
                    result.method,
                    result.confidence,
                    result.raw_text,
                    result.raw_text,
                    row_id,
                ),
            )
            rowcount = int(getattr(cur, "rowcount", 0) or 0)
            self.store._conn.commit()
            return rowcount > 0
        finally:
            cur.close()
