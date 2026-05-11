"""Worker that sends rule-fallback topic articles to the LLM refinement layer."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from news_platform.topic_llm import TopicLlmClassifier
from news_platform.topics import general_topic_for_category


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TopicLlmRunResult:
    scanned: int
    updated: int
    failed: int


class TopicLlmFallbackWorker:
    def __init__(self, store, classifier: TopicLlmClassifier, *, batch_size: int = 50) -> None:
        self._store = store
        self._classifier = classifier
        self._batch_size = max(1, int(batch_size))

    def run_once(self) -> TopicLlmRunResult:
        rows = self._store.fetch_articles_empty_topics(limit=self._batch_size)
        updated = 0
        failed = 0
        for row in rows:
            try:
                result = self._classifier.classify(title=row.title or "", summary=row.summary or "")
                topics = result.topics or [
                    general_topic_for_category(
                        getattr(row, "category", None),
                        source="llm_fallback",
                        reason="llm_no_specific_topic_match",
                        raw_topic_id=result.raw_topic_id,
                        provider=result.provider,
                        model=result.model,
                        confidence=round(float(result.confidence), 2),
                    )
                ]
                self._store.update_article_topics(row.row_id, topics, classified_by="llm")
                updated += 1
            except Exception as exc:
                logger.exception("Topic LLM fallback failed row_id=%s error=%s", row.row_id, exc)
                failed += 1
        return TopicLlmRunResult(scanned=len(rows), updated=updated, failed=failed)

    def run_until_drained(self, *, max_iterations: int = 100) -> TopicLlmRunResult:
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
        return TopicLlmRunResult(
            scanned=total_scanned,
            updated=total_updated,
            failed=total_failed,
        )
