"""Pipeline：從 sources fetch → dedupe → 寫入 store。

注意：本套件**不**寫入 t_relay_events，所有寫入都走自家的 store。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from news_platform.models import NewsArticle
from news_platform.sources.base import NewsSource


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchResult:
    fetched: int
    deduped: int
    stored: int
    duplicates: int
    failed: int


def fetch_all(sources: list[NewsSource], limit_per_source: int = 20) -> list[NewsArticle]:
    """平行抓取每個 source；單一來源失敗不影響整批。"""
    articles: list[NewsArticle] = []
    if not sources:
        return articles

    with ThreadPoolExecutor(max_workers=min(8, len(sources))) as executor:
        future_map = {executor.submit(src.fetch, limit_per_source): src for src in sources}
        for fut in as_completed(future_map):
            src = future_map[fut]
            try:
                items = fut.result()
                if not items:
                    # 0 筆通常是 RSS URL 失效或站台改版，要顯眼警告。
                    logger.warning("Fetched source=%s items=0 (verify feed is alive)", src.name)
                else:
                    logger.info("Fetched source=%s items=%d", src.name, len(items))
                articles.extend(items)
            except Exception as exc:
                logger.warning("Fetch failed source=%s error=%s", src.name, exc)
    return dedupe(articles)


def dedupe(articles: list[NewsArticle]) -> list[NewsArticle]:
    """先用 article_id 去重；同一條被多個 feed 收錄時保留最早遇到的那筆。"""
    seen: set[str] = set()
    output: list[NewsArticle] = []
    for art in articles:
        key = art.article_id or art.url
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(art)
    return output


def run_once(
    sources: list[NewsSource],
    store,
    limit_per_source: int = 20,
) -> FetchResult:
    """fetch + 寫庫一次。store 必須提供 ``upsert_article(article) -> bool``。"""
    articles = fetch_all(sources, limit_per_source)
    stored = 0
    duplicates = 0
    failed = 0
    for art in articles:
        try:
            inserted = store.upsert_article(art)
        except Exception as exc:
            logger.exception("Store failed source=%s url=%s error=%s", art.source_id, art.url, exc)
            failed += 1
            continue
        if inserted:
            stored += 1
        else:
            duplicates += 1
    return FetchResult(
        fetched=len(articles),
        deduped=len(articles),
        stored=stored,
        duplicates=duplicates,
        failed=failed,
    )
