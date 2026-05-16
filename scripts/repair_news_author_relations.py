"""Repair normalized article-author metadata after extractor rule changes."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news_platform.author_extractor import extract_authors_from_text, normalize_authors  # noqa: E402
from news_platform.author_metadata import (  # noqa: E402
    AUTHOR_METHOD_ARTICLE_DETAIL,
    AUTHOR_METHOD_LEGACY_AUTHORS_JSON,
    AUTHOR_STATUS_LOW_CONFIDENCE,
    AUTHOR_STATUS_PRESENT,
)
from news_platform.config import load_settings  # noqa: E402
from news_platform.store import NewsPlatformStore  # noqa: E402


@dataclass(frozen=True)
class RepairCandidate:
    row_id: int
    article_id: str
    source_id: str
    published_at: datetime | None
    authors_json: str | None
    method: str | None
    confidence: float | None
    raw_text: str | None


@dataclass(frozen=True)
class RepairDecision:
    authors: list[str]
    status: str
    method: str
    confidence: float


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--sources", nargs="*", default=["ltn"])
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    settings = load_settings(args.env_file)
    store = NewsPlatformStore(settings)
    store.initialize()
    counters = {
        "candidates": 0,
        "changed": 0,
        "present": 0,
        "low_confidence": 0,
        "relations": 0,
        "orphan_authors_deleted": 0,
        "dry_run": 0,
    }

    try:
        candidates = fetch_candidates(
            store,
            sources=args.sources,
            limit=max(1, int(args.limit)),
        )
        counters["candidates"] = len(candidates)

        for index, candidate in enumerate(candidates, start=1):
            original = _parse_authors(candidate.authors_json)
            decision = repair_decision(candidate)
            changed = original != decision.authors
            counters[decision.status] = counters.get(decision.status, 0) + 1
            if changed:
                counters["changed"] += 1

            if args.dry_run:
                counters["dry_run"] += 1
                if changed and not args.quiet:
                    print(
                        f"[dry-run] {index}/{len(candidates)} "
                        f"source={candidate.source_id} article_id={candidate.article_id} "
                        f"{original} -> {decision.authors}"
                    )
                continue

            if changed:
                update_article_authors(store, candidate, decision)
                delete_article_author_relations(store, candidate.article_id)
                if decision.authors:
                    counters["relations"] += store.upsert_article_author_relations(
                        article_id=candidate.article_id,
                        source_id=candidate.source_id,
                        published_at=candidate.published_at,
                        authors=decision.authors,
                        extraction_method=decision.method,
                        confidence=decision.confidence,
                        raw_text=candidate.raw_text,
                    )
                if not args.quiet:
                    print(
                        f"{index}/{len(candidates)} source={candidate.source_id} "
                        f"article_id={candidate.article_id} {original} -> {decision.authors}"
                    )

        if not args.dry_run:
            counters["orphan_authors_deleted"] = delete_orphan_authors(store, sources=args.sources)

        print("summary=" + json.dumps(counters, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        store.close()


def fetch_candidates(
    store: NewsPlatformStore,
    *,
    sources: Iterable[str],
    limit: int,
) -> list[RepairCandidate]:
    source_ids = [source.strip().lower() for source in sources if source.strip()]
    if not source_ids:
        return []
    placeholders = ",".join(["%s"] * len(source_ids))
    sql = (
        f"SELECT id, article_id, source_id, published_at, authors_json, "
        "author_extraction_method, author_extraction_confidence, author_raw_text "
        f"FROM `{store._settings.mysql_article_table}` "
        f"WHERE source_id IN ({placeholders}) "
        "AND JSON_LENGTH(COALESCE(authors_json, JSON_ARRAY())) > 0 "
        "ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC "
        "LIMIT %s"
    )
    cur = store._cursor()
    try:
        cur.execute(sql, tuple(source_ids + [limit]))
        rows = cur.fetchall()
    finally:
        cur.close()

    return [
        RepairCandidate(
            row_id=int(row[0]),
            article_id=str(row[1]),
            source_id=str(row[2]).lower(),
            published_at=row[3],
            authors_json=row[4],
            method=None if row[5] is None else str(row[5]),
            confidence=None if row[6] is None else float(row[6]),
            raw_text=None if row[7] is None else str(row[7]),
        )
        for row in rows
    ]


def repair_decision(candidate: RepairCandidate) -> RepairDecision:
    raw_authors = extract_authors_from_text(candidate.raw_text)
    if raw_authors:
        return RepairDecision(
            authors=raw_authors,
            status=AUTHOR_STATUS_PRESENT,
            method=AUTHOR_METHOD_ARTICLE_DETAIL,
            confidence=0.95,
        )
    if candidate.raw_text or candidate.method == AUTHOR_METHOD_ARTICLE_DETAIL:
        return RepairDecision(
            authors=[],
            status=AUTHOR_STATUS_LOW_CONFIDENCE,
            method=AUTHOR_METHOD_ARTICLE_DETAIL,
            confidence=0.0,
        )

    normalized = normalize_authors(_parse_authors(candidate.authors_json))
    if normalized:
        return RepairDecision(
            authors=normalized,
            status=AUTHOR_STATUS_PRESENT,
            method=candidate.method or AUTHOR_METHOD_LEGACY_AUTHORS_JSON,
            confidence=candidate.confidence if candidate.confidence is not None else 1.0,
        )

    return RepairDecision(
        authors=[],
        status=AUTHOR_STATUS_LOW_CONFIDENCE,
        method=candidate.method or AUTHOR_METHOD_LEGACY_AUTHORS_JSON,
        confidence=0.0,
    )


def update_article_authors(
    store: NewsPlatformStore,
    candidate: RepairCandidate,
    decision: RepairDecision,
) -> None:
    sql = (
        f"UPDATE `{store._settings.mysql_article_table}` "
        "SET authors_json=%s, "
        "author_extraction_status=%s, "
        "author_extraction_method=%s, "
        "author_extraction_confidence=%s, "
        "author_extracted_at=UTC_TIMESTAMP() "
        "WHERE id=%s"
    )
    cur = store._cursor()
    try:
        cur.execute(
            sql,
            (
                json.dumps(decision.authors, ensure_ascii=False),
                decision.status,
                decision.method,
                decision.confidence,
                candidate.row_id,
            ),
        )
        store._conn.commit()
    finally:
        cur.close()


def delete_article_author_relations(store: NewsPlatformStore, article_id: str) -> int:
    cur = store._cursor()
    try:
        cur.execute(
            f"DELETE FROM `{store._settings.mysql_article_author_table}` WHERE article_id=%s",
            (article_id,),
        )
        count = int(getattr(cur, "rowcount", 0) or 0)
        store._conn.commit()
        return count
    finally:
        cur.close()


def delete_orphan_authors(store: NewsPlatformStore, *, sources: Iterable[str]) -> int:
    source_ids = [source.strip().lower() for source in sources if source.strip()]
    if not source_ids:
        return 0
    placeholders = ",".join(["%s"] * len(source_ids))
    sql = (
        f"DELETE a FROM `{store._settings.mysql_author_table}` a "
        f"LEFT JOIN `{store._settings.mysql_article_author_table}` aa ON aa.author_id = a.id "
        f"WHERE a.source_id IN ({placeholders}) AND aa.id IS NULL"
    )
    cur = store._cursor()
    try:
        cur.execute(sql, tuple(source_ids))
        count = int(getattr(cur, "rowcount", 0) or 0)
        store._conn.commit()
        return count
    finally:
        cur.close()


def _parse_authors(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [str(item).strip() for item in payload if str(item).strip()]


if __name__ == "__main__":
    raise SystemExit(main())
