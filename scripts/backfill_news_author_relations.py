"""Backfill normalized author relations from existing authors_json rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news_platform.config import load_settings
from news_platform.store import NewsPlatformStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    settings = load_settings(args.env_file)
    store = NewsPlatformStore(settings)
    store.initialize()
    processed = 0
    linked = 0
    try:
        cur = store._cursor()
        try:
            cur.execute(
                (
                    f"SELECT article_id, source_id, published_at, authors_json, "
                    f"author_extraction_method, author_raw_text "
                    f"FROM `{settings.mysql_article_table}` "
                    "WHERE JSON_LENGTH(COALESCE(authors_json, JSON_ARRAY())) > 0 "
                    "ORDER BY id ASC LIMIT %s"
                ),
                (max(1, int(args.limit)),),
            )
            rows = cur.fetchall()
        finally:
            cur.close()

        for article_id, source_id, published_at, authors_json, method, raw_text in rows:
            authors = _parse_authors(authors_json)
            if not authors:
                continue
            linked += store.upsert_article_author_relations(
                article_id=str(article_id),
                source_id=str(source_id),
                published_at=published_at,
                authors=authors,
                extraction_method=str(method or "legacy_authors_json"),
                confidence=1.0,
                raw_text=None if raw_text is None else str(raw_text),
            )
            processed += 1

        print(f"processed_articles={processed} linked_relations={linked}")
        return 0
    finally:
        store.close()


def _parse_authors(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
    else:
        parsed = value
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item or "").strip()]


if __name__ == "__main__":
    raise SystemExit(main())
