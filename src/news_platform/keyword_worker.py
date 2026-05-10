"""關鍵字補欄 worker — 掃 t_news_articles.keywords_json 為 NULL 的 row。

設計：
- 與 crawler 解耦：crawler 只寫文章，這個 worker 後處理。
- 失敗單筆不擋整批：log 後繼續。
- 即使 jieba 抽不到（標題太短／全停用詞），仍寫 ``[]`` 標記已處理，避免下一輪重抽。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KeywordRunResult:
    scanned: int
    updated: int
    failed: int


class KeywordWorker:
    def __init__(self, store, extractor, *, batch_size: int = 200, top_k: int = 5) -> None:
        self._store = store
        self._extractor = extractor
        self._batch_size = max(1, int(batch_size))
        self._top_k = max(1, int(top_k))

    def run_once(self) -> KeywordRunResult:
        rows = self._store.fetch_articles_missing_keywords(limit=self._batch_size)
        updated = 0
        failed = 0
        for row in rows:
            try:
                keywords = self._extractor.extract(row.title, top_k=self._top_k)
            except Exception as exc:
                logger.warning("Extract failed row_id=%s error=%s", row.row_id, exc)
                failed += 1
                continue
            try:
                self._store.update_keywords(row.row_id, keywords)
                updated += 1
            except Exception as exc:
                logger.exception("Store keywords failed row_id=%s error=%s", row.row_id, exc)
                failed += 1
        return KeywordRunResult(scanned=len(rows), updated=updated, failed=failed)

    def run_until_drained(self, *, max_iterations: int = 100) -> KeywordRunResult:
        """連續跑直到沒有新 row 為止。每輪上限 batch_size，避免單次跑太久。"""
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
        return KeywordRunResult(
            scanned=total_scanned, updated=total_updated, failed=total_failed
        )
