"""Pipeline for official structured public records."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from news_platform.models import PublicRecord


logger = logging.getLogger(__name__)


@dataclass
class PublicRecordRunResult:
    fetched: int = 0
    stored: int = 0
    duplicates: int = 0
    failed: int = 0


def fetch_all_public_records(
    sources,
    *,
    limit_per_source: int | None = None,
    fetch_kwargs: dict | None = None,
) -> list[PublicRecord]:
    if not sources:
        return []
    output: list[PublicRecord] = []
    kwargs = dict(fetch_kwargs or {})
    with ThreadPoolExecutor(max_workers=min(4, len(sources))) as executor:
        future_map = {
            executor.submit(src.fetch, limit=limit_per_source, **kwargs): src
            for src in sources
        }
        for future in as_completed(future_map):
            src = future_map[future]
            try:
                records = future.result()
            except Exception as exc:
                logger.warning("Public record source failed source=%s error=%s", getattr(src, "name", src), exc)
                continue
            logger.info("Fetched public source=%s records=%d", getattr(src, "name", src), len(records))
            output.extend(records)
    return output


def run_public_records_once(
    sources,
    store,
    *,
    limit_per_source: int | None = None,
    fetch_kwargs: dict | None = None,
) -> PublicRecordRunResult:
    records = fetch_all_public_records(
        sources,
        limit_per_source=limit_per_source,
        fetch_kwargs=fetch_kwargs,
    )
    result = PublicRecordRunResult(fetched=len(records))
    for record in records:
        try:
            inserted = store.upsert_public_record(record)
        except Exception as exc:
            result.failed += 1
            logger.warning("Public record store failed record_id=%s error=%s", record.record_id, exc)
            continue
        if inserted:
            result.stored += 1
        else:
            result.duplicates += 1
    return result
