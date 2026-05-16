"""Backfill article-level author extraction status for existing rows."""

from __future__ import annotations

import argparse
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
    args = parser.parse_args()

    settings = load_settings(args.env_file)
    store = NewsPlatformStore(settings)
    store.initialize()
    try:
        cur = store._cursor()
        try:
            table = settings.mysql_article_table
            updates = [
                (
                    "present",
                    (
                        f"UPDATE `{table}` SET "
                        "author_extraction_status='present', "
                        "author_extraction_method=COALESCE(author_extraction_method, 'legacy_authors_json'), "
                        "author_extraction_confidence=COALESCE(author_extraction_confidence, 1.0000), "
                        "author_extracted_at=COALESCE(author_extracted_at, UTC_TIMESTAMP()) "
                        "WHERE JSON_LENGTH(COALESCE(authors_json, JSON_ARRAY())) > 0 "
                        "AND COALESCE(author_extraction_status, '') <> 'present'"
                    ),
                ),
                (
                    "low_confidence",
                    (
                        f"UPDATE `{table}` SET "
                        "author_extraction_status='low_confidence', "
                        "author_extraction_method=COALESCE(author_extraction_method, 'legacy_author_values'), "
                        "author_extraction_confidence=COALESCE(author_extraction_confidence, 0.0000), "
                        "author_raw_text=COALESCE(author_raw_text, JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.author_values'))), "
                        "author_extracted_at=COALESCE(author_extracted_at, UTC_TIMESTAMP()) "
                        "WHERE JSON_LENGTH(COALESCE(authors_json, JSON_ARRAY())) = 0 "
                        "AND author_extraction_status IS NULL "
                        "AND JSON_EXTRACT(raw_json, '$.author_values') IS NOT NULL"
                    ),
                ),
                (
                    "parser_not_supported",
                    (
                        f"UPDATE `{table}` SET "
                        "author_extraction_status='parser_not_supported', "
                        "author_extraction_method=COALESCE(author_extraction_method, 'none'), "
                        "author_extracted_at=COALESCE(author_extracted_at, UTC_TIMESTAMP()) "
                        "WHERE JSON_LENGTH(COALESCE(authors_json, JSON_ARRAY())) = 0 "
                        "AND author_extraction_status IS NULL "
                        "AND JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.kind')) IN ('ettoday_list', 'pts_category')"
                    ),
                ),
                (
                    "no_detail_fetched",
                    (
                        f"UPDATE `{table}` SET "
                        "author_extraction_status='no_detail_fetched', "
                        "author_extraction_method=COALESCE(author_extraction_method, 'none'), "
                        "author_extracted_at=COALESCE(author_extracted_at, UTC_TIMESTAMP()) "
                        "WHERE JSON_LENGTH(COALESCE(authors_json, JSON_ARRAY())) = 0 "
                        "AND author_extraction_status IS NULL"
                    ),
                ),
            ]
            for label, sql in updates:
                cur.execute(sql)
                print(f"{label}_rows={cur.rowcount}")
            store._conn.commit()
            return 0
        finally:
            cur.close()
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
