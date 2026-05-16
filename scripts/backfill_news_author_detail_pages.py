"""Backfill missing reporter names from article detail pages.

The script only enriches author metadata for existing RSS/sitemap/list article
rows. It does not extract or store article body content.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news_platform.article_detail_author_extractor import (  # noqa: E402
    ArticleDetailAuthorExtractor,
    ArticleDetailAuthorResult,
)
from news_platform.author_metadata import (  # noqa: E402
    AUTHOR_METHOD_ARTICLE_DETAIL,
    AUTHOR_STATUS_LOW_CONFIDENCE,
    AUTHOR_STATUS_NO_AUTHOR_METADATA,
    AUTHOR_STATUS_NO_DETAIL_FETCHED,
    AUTHOR_STATUS_PARSE_FAILED,
    AUTHOR_STATUS_PARSER_NOT_SUPPORTED,
    AUTHOR_STATUS_PRESENT,
)
from news_platform.config import load_settings  # noqa: E402
from news_platform.http_client import http_get_bytes  # noqa: E402
from news_platform.store import NewsPlatformStore  # noqa: E402


FIRST_PASS_SOURCE_IDS = ("cna", "storm", "newtalk", "ltn", "ettoday")
DEFAULT_ELIGIBLE_STATUSES = (
    AUTHOR_STATUS_NO_DETAIL_FETCHED,
    AUTHOR_STATUS_PARSER_NOT_SUPPORTED,
    AUTHOR_STATUS_LOW_CONFIDENCE,
)
SOURCE_VERIFY_SSL = {
    "ettoday": False,
}


@dataclass(frozen=True)
class ArticleCandidate:
    row_id: int
    article_id: str
    source_id: str
    url: str
    published_at: datetime | None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--sources", nargs="*", default=list(FIRST_PASS_SOURCE_IDS))
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    settings = load_settings(args.env_file)
    store = NewsPlatformStore(settings)
    store.initialize()
    extractor = ArticleDetailAuthorExtractor()
    counters = {
        "candidates": 0,
        "present": 0,
        "no_author_metadata": 0,
        "low_confidence": 0,
        "parse_failed": 0,
        "updated": 0,
        "relations": 0,
        "dry_run": 0,
    }
    try:
        statuses = list(DEFAULT_ELIGIBLE_STATUSES)
        if args.retry_failed:
            statuses.append(AUTHOR_STATUS_PARSE_FAILED)
        candidates = fetch_candidates(
            store,
            sources=args.sources,
            statuses=statuses,
            limit=max(1, int(args.limit)),
        )
        counters["candidates"] = len(candidates)
        for index, candidate in enumerate(candidates, start=1):
            try:
                payload = http_get_bytes(
                    candidate.url,
                    timeout=args.timeout,
                    verify_ssl=SOURCE_VERIFY_SSL.get(candidate.source_id, True),
                )
                result = extractor.extract(payload, source_id=candidate.source_id, url=candidate.url)
            except Exception:
                result = ArticleDetailAuthorResult(
                    authors=[],
                    status=AUTHOR_STATUS_PARSE_FAILED,
                    method=AUTHOR_METHOD_ARTICLE_DETAIL,
                    confidence=None,
                    raw_text=None,
                )

            counters[result.status] = counters.get(result.status, 0) + 1
            if args.dry_run:
                counters["dry_run"] += 1
                if not args.quiet:
                    print(
                        f"[dry-run] {index}/{len(candidates)} source={candidate.source_id} "
                        f"article_id={candidate.article_id} status={result.status} authors={result.authors}"
                    )
            else:
                updated = update_article_author_result(store, candidate.row_id, result)
                if updated:
                    counters["updated"] += 1
                    if result.authors:
                        counters["relations"] += store.upsert_article_author_relations(
                            article_id=candidate.article_id,
                            source_id=candidate.source_id,
                            published_at=candidate.published_at,
                            authors=result.authors,
                            extraction_method=AUTHOR_METHOD_ARTICLE_DETAIL,
                            confidence=result.confidence or 0.0,
                            raw_text=result.raw_text,
                        )
                if not args.quiet:
                    print(
                        f"{index}/{len(candidates)} source={candidate.source_id} "
                        f"article_id={candidate.article_id} status={result.status} "
                        f"authors={','.join(result.authors) if result.authors else '-'} updated={updated}"
                    )

            if index < len(candidates) and args.sleep_seconds > 0:
                time.sleep(float(args.sleep_seconds))

        print("summary=" + json.dumps(counters, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        store.close()


def fetch_candidates(
    store: NewsPlatformStore,
    *,
    sources: Iterable[str],
    statuses: Iterable[str],
    limit: int,
) -> list[ArticleCandidate]:
    source_ids = [source.strip().lower() for source in sources if source.strip()]
    status_values = [status.strip() for status in statuses if status.strip()]
    if not source_ids:
        return []

    source_placeholders = ",".join(["%s"] * len(source_ids))
    status_placeholders = ",".join(["%s"] * len(status_values))
    status_predicate = (
        f"(author_extraction_status IS NULL OR author_extraction_status IN ({status_placeholders}))"
        if status_values
        else "1=1"
    )
    sql = (
        f"SELECT id, article_id, source_id, url, published_at "
        f"FROM `{store._settings.mysql_article_table}` "
        "WHERE JSON_LENGTH(COALESCE(authors_json, JSON_ARRAY())) = 0 "
        "AND COALESCE(author_extraction_status, '') <> 'present' "
        f"AND source_id IN ({source_placeholders}) "
        f"AND {status_predicate} "
        "AND url IS NOT NULL AND url <> '' "
        "ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC "
        "LIMIT %s"
    )
    params = tuple(source_ids + status_values + [limit])
    cur = store._cursor()
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close()

    return [
        ArticleCandidate(
            row_id=int(row[0]),
            article_id=str(row[1]),
            source_id=str(row[2]).lower(),
            url=str(row[3]),
            published_at=row[4],
        )
        for row in rows
    ]


def update_article_author_result(
    store: NewsPlatformStore,
    row_id: int,
    result: ArticleDetailAuthorResult,
) -> bool:
    authors_json = json.dumps(result.authors, ensure_ascii=False)
    sql = (
        f"UPDATE `{store._settings.mysql_article_table}` "
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
    cur = store._cursor()
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
        store._conn.commit()
        return rowcount > 0
    finally:
        cur.close()


if __name__ == "__main__":
    raise SystemExit(main())
