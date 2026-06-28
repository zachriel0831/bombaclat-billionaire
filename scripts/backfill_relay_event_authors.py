"""Backfill reporter names into relay-event raw_json.

This script enriches short-retention finance/news relay rows only. It fetches
already-known article detail URLs to extract byline metadata and never stores
article body content.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from event_relay.config import load_settings  # noqa: E402
from event_relay.service import MySqlEventStore  # noqa: E402
from news_platform.article_detail_author_extractor import (  # noqa: E402
    ArticleDetailAuthorExtractor,
    ArticleDetailAuthorResult,
)
from news_platform.author_extractor import normalize_authors  # noqa: E402
from news_platform.author_metadata import (  # noqa: E402
    AUTHOR_METHOD_ARTICLE_DETAIL,
    AUTHOR_METHOD_RSS_METADATA,
    AUTHOR_STATUS_LOW_CONFIDENCE,
    AUTHOR_STATUS_NO_AUTHOR_METADATA,
    AUTHOR_STATUS_PARSE_FAILED,
    AUTHOR_STATUS_PRESENT,
)
from news_platform.http_client import http_get_bytes  # noqa: E402


DETAIL_SOURCE_BY_HOST = {
    "ec.ltn.com.tw": "ltn",
    "news.ltn.com.tw": "ltn",
    "finance.ettoday.net": "ettoday",
    "www.ettoday.net": "ettoday",
    "money.udn.com": "moneyudn",
    "udn.com": "moneyudn",
    "www.cna.com.tw": "cna",
    "newtalk.tw": "newtalk",
    "www.storm.mg": "storm",
    "www.ctee.com.tw": "ctee",
    "ctee.com.tw": "ctee",
    "news.cnyes.com": "anue",
    "www.moneydj.com": "moneydj",
    "m.moneydj.com": "moneydj",
}

SOURCE_VERIFY_SSL = {
    "ettoday": False,
}

NON_AUTHOR_NAMES = {
    "anue",
    "cna",
    "ctee",
    "edn",
    "ettoday",
    "ltn",
    "moneydj",
    "moneyudn",
    "udn",
}


@dataclass(frozen=True)
class RelayEventCandidate:
    row_id: int
    source: str
    title: str
    url: str
    raw_json: str | None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    settings = load_settings(args.env_file)
    store = MySqlEventStore(settings)
    store.initialize()
    extractor = ArticleDetailAuthorExtractor()
    counters: dict[str, int] = {
        "rows_scanned": 0,
        "eligible": 0,
        "present": 0,
        "no_author_metadata": 0,
        "low_confidence": 0,
        "parse_failed": 0,
        "updated": 0,
        "dry_run": 0,
        "skipped_existing": 0,
        "skipped_unsupported": 0,
    }

    try:
        scan_limit = max(int(args.limit), 1) * 10
        candidates = fetch_recent_relay_candidates(store, days=max(int(args.days), 1), limit=scan_limit)
        counters["rows_scanned"] = len(candidates)
        processed = 0

        for candidate in candidates:
            if processed >= max(int(args.limit), 1):
                break

            payload = decode_raw_json(candidate.raw_json)
            if should_skip_existing(payload, retry_failed=bool(args.retry_failed)):
                counters["skipped_existing"] += 1
                continue

            source_id = source_id_for_url(candidate.url)
            if not source_id:
                counters["skipped_unsupported"] += 1
                continue

            processed += 1
            counters["eligible"] += 1
            result = result_from_raw_metadata(payload)
            if result is None:
                result = fetch_detail_author_result(
                    extractor,
                    candidate.url,
                    source_id=source_id,
                    timeout=int(args.timeout),
                )
            result = sanitize_author_result(result)

            counters[result.status] = counters.get(result.status, 0) + 1
            if args.dry_run:
                counters["dry_run"] += 1
                if not args.quiet:
                    print(
                        f"[dry-run] {processed}/{args.limit} id={candidate.row_id} source={candidate.source} "
                        f"host={urlparse(candidate.url).hostname or '-'} status={result.status} "
                        f"authors={','.join(result.authors) if result.authors else '-'}"
                    )
            else:
                updated = update_relay_event_raw_json(store, candidate.row_id, payload, result)
                if updated:
                    counters["updated"] += 1
                if not args.quiet:
                    print(
                        f"{processed}/{args.limit} id={candidate.row_id} source={candidate.source} "
                        f"status={result.status} authors={','.join(result.authors) if result.authors else '-'} "
                        f"updated={updated}"
                    )

            if processed < max(int(args.limit), 1) and args.sleep_seconds > 0:
                time.sleep(float(args.sleep_seconds))

        print("summary=" + json.dumps(counters, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        close_store(store)


def fetch_recent_relay_candidates(store: MySqlEventStore, *, days: int, limit: int) -> list[RelayEventCandidate]:
    sql = (
        f"SELECT id, source, title, url, raw_json "
        f"FROM `{store._event_table}` "
        "WHERE created_at >= (NOW() - INTERVAL %s DAY) "
        "AND url IS NOT NULL AND url <> '' "
        "ORDER BY id DESC "
        "LIMIT %s"
    )
    cur = store._cursor()
    try:
        cur.execute(sql, (days, limit))
        rows = cur.fetchall()
    finally:
        cur.close()

    return [
        RelayEventCandidate(
            row_id=int(row[0]),
            source=str(row[1] or ""),
            title=str(row[2] or ""),
            url=str(row[3] or ""),
            raw_json=str(row[4]) if row[4] is not None else None,
        )
        for row in rows
    ]


def decode_raw_json(raw_json: str | None) -> dict[str, object]:
    if not raw_json:
        return {}
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def should_skip_existing(payload: dict[str, object], *, retry_failed: bool) -> bool:
    if author_values_from_payload(payload):
        return True
    extraction = payload.get("author_extraction")
    status = ""
    if isinstance(extraction, dict):
        status = str(extraction.get("status") or "").strip()
    if not status:
        return False
    if status == AUTHOR_STATUS_PRESENT:
        return True
    return not retry_failed


def source_id_for_url(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www.") and host not in DETAIL_SOURCE_BY_HOST:
        host = host[4:]
    return DETAIL_SOURCE_BY_HOST.get(host)


def result_from_raw_metadata(payload: dict[str, object]) -> ArticleDetailAuthorResult | None:
    raw_values = raw_author_values(payload)
    if not raw_values:
        return None
    authors = normalize_authors(raw_values)
    if not authors:
        return ArticleDetailAuthorResult(
            authors=[],
            status=AUTHOR_STATUS_LOW_CONFIDENCE,
            method=AUTHOR_METHOD_RSS_METADATA,
            confidence=0.0,
            raw_text=" | ".join(raw_values)[:500],
        )
    return ArticleDetailAuthorResult(
        authors=authors,
        status=AUTHOR_STATUS_PRESENT,
        method=AUTHOR_METHOD_RSS_METADATA,
        confidence=1.0,
        raw_text=" | ".join(raw_values)[:500],
    )


def raw_author_values(payload: dict[str, object]) -> list[str]:
    values: list[str] = []
    values.extend(string_list(payload.get("author_values")))
    raw = payload.get("raw")
    if isinstance(raw, dict):
        values.extend(string_list(raw.get("author_values")))
    return unique_text(values)


def author_values_from_payload(payload: dict[str, object]) -> list[str]:
    values: list[str] = []
    values.extend(string_list(payload.get("authors")))
    raw = payload.get("raw")
    if isinstance(raw, dict):
        values.extend(string_list(raw.get("authors")))
    return unique_text(values)


def string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def unique_text(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def fetch_detail_author_result(
    extractor: ArticleDetailAuthorExtractor,
    url: str,
    *,
    source_id: str,
    timeout: int,
) -> ArticleDetailAuthorResult:
    try:
        payload = http_get_bytes(
            url,
            timeout=timeout,
            verify_ssl=SOURCE_VERIFY_SSL.get(source_id, True),
        )
        return extractor.extract(payload, source_id=source_id, url=url)
    except Exception:
        return ArticleDetailAuthorResult(
            authors=[],
            status=AUTHOR_STATUS_PARSE_FAILED,
            method=AUTHOR_METHOD_ARTICLE_DETAIL,
            confidence=None,
            raw_text=None,
        )


def sanitize_author_result(result: ArticleDetailAuthorResult) -> ArticleDetailAuthorResult:
    authors = [author for author in result.authors if is_plausible_author_name(author)]
    if authors == result.authors:
        return result
    if authors:
        return ArticleDetailAuthorResult(
            authors=authors,
            status=AUTHOR_STATUS_PRESENT,
            method=result.method,
            confidence=result.confidence,
            raw_text=result.raw_text,
        )
    return ArticleDetailAuthorResult(
        authors=[],
        status=AUTHOR_STATUS_LOW_CONFIDENCE if result.status == AUTHOR_STATUS_PRESENT else result.status,
        method=result.method,
        confidence=0.0 if result.status == AUTHOR_STATUS_PRESENT else result.confidence,
        raw_text=result.raw_text,
    )


def is_plausible_author_name(value: str) -> bool:
    normalized = " ".join(str(value).split()).strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered in NON_AUTHOR_NAMES:
        return False
    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        return False
    if normalized.isascii() and normalized == lowered and " " not in normalized:
        return False
    return True


def update_relay_event_raw_json(
    store: MySqlEventStore,
    row_id: int,
    payload: dict[str, object],
    result: ArticleDetailAuthorResult,
) -> bool:
    payload["authors"] = result.authors
    payload["author_extraction"] = {
        "status": result.status,
        "method": result.method,
        "confidence": result.confidence,
        "raw_text": result.raw_text,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = payload.get("raw")
    if isinstance(raw, dict):
        raw["authors"] = result.authors

    sql = f"UPDATE `{store._event_table}` SET raw_json=%s WHERE id=%s"
    cur = store._cursor()
    try:
        cur.execute(sql, (json.dumps(payload, ensure_ascii=False), row_id))
        rowcount = int(getattr(cur, "rowcount", 0) or 0)
        if store._conn is None:
            raise RuntimeError("MySQL not initialized")
        store._conn.commit()
        return rowcount > 0
    finally:
        cur.close()


def close_store(store: MySqlEventStore) -> None:
    conn = getattr(store, "_conn", None)
    if conn is not None:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
