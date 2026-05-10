"""Topic classification worker for articles with extracted keywords."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from news_platform.topic_classifier import classify
from news_platform.topics import general_social_topic


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TopicRunResult:
    scanned: int
    updated: int
    failed: int


class TopicWorker:
    def __init__(self, store, *, batch_size: int = 200) -> None:
        self._store = store
        self._batch_size = max(1, int(batch_size))

    def run_once(self) -> TopicRunResult:
        rows = self._store.fetch_articles_missing_topics(limit=self._batch_size)
        updated = 0
        failed = 0
        for row in rows:
            try:
                keywords = _loads_keywords(row.keywords_json)
                topics = classify(
                    title=row.title or "",
                    summary=row.summary or "",
                    keywords=keywords,
                )
                if not topics:
                    topics = [general_social_topic()]
                self._store.update_article_topics(row.row_id, topics, classified_by="rule")
                updated += 1
            except Exception as exc:
                logger.exception("Topic classification failed row_id=%s error=%s", row.row_id, exc)
                failed += 1
        return TopicRunResult(scanned=len(rows), updated=updated, failed=failed)

    def run_until_drained(self, *, max_iterations: int = 100) -> TopicRunResult:
        total_scanned = 0
        total_updated = 0
        total_failed = 0
        for _ in range(max(1, int(max_iterations))):
            result = self.run_once()
            total_scanned += result.scanned
            total_updated += result.updated
            total_failed += result.failed
            if result.scanned == 0:
                break
        return TopicRunResult(
            scanned=total_scanned,
            updated=total_updated,
            failed=total_failed,
        )


def _loads_keywords(value: str | bytes | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]
