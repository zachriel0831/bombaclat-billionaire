"""News-platform CLI 入口 — 跑一次或循環抓 TW 社會新聞。

用法：
    PYTHONPATH=src .venv/Scripts/python.exe -m news_platform.main --once
    PYTHONPATH=src .venv/Scripts/python.exe -m news_platform.main --loop
    PYTHONPATH=src .venv/Scripts/python.exe -m news_platform.main --smoke
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from datetime import date

from news_platform.config import NewsPlatformSettings, load_settings
from news_platform.keyword_extractor import KeywordExtractor
from news_platform.keyword_worker import KeywordWorker
from news_platform.pipeline import fetch_all, run_once
from news_platform.registry import FeedSpec, tw_society_feeds
from news_platform.sources.base import NewsSource
from news_platform.sources.rss_feed import RssFeedSource
from news_platform.sources.sitemap_news import GoogleNewsSitemapSource
from news_platform.store import NewsPlatformStore
from news_platform.topic_llm import TopicLlmClassifier
from news_platform.topic_llm_worker import TopicLlmFallbackWorker
from news_platform.topic_worker import TopicWorker


logger = logging.getLogger("news_platform")


def build_source(spec: FeedSpec, settings: NewsPlatformSettings) -> NewsSource:
    """依 spec.kind 建對應的來源類別。"""
    if spec.kind == "rss":
        return RssFeedSource(
            source_id=spec.source_id,
            country="TW",
            category=spec.category,
            url=spec.url,
            timeout_seconds=settings.http_timeout_seconds,
            max_age_days=settings.max_age_days,
        )
    if spec.kind == "sitemap":
        return GoogleNewsSitemapSource(
            source_id=spec.source_id,
            country="TW",
            category=spec.category,
            url=spec.url,
            path_filter=spec.path_filter,
            timeout_seconds=settings.http_timeout_seconds,
            max_age_days=settings.max_age_days,
        )
    raise ValueError(f"Unknown feed kind: {spec.kind}")


def build_tw_society_sources(settings: NewsPlatformSettings) -> list[NewsSource]:
    return [build_source(spec, settings) for spec in tw_society_feeds()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TW news platform crawler (society first)")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--once", action="store_true", help="Run a single fetch+store cycle and exit")
    parser.add_argument("--loop", action="store_true", help="Run continuously on poll interval")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Fetch and parse only — no DB write. Use to verify feed URLs are alive.",
    )
    parser.add_argument(
        "--extract-keywords",
        action="store_true",
        help="Run jieba keyword extraction over articles missing keywords_json, then exit.",
    )
    parser.add_argument(
        "--keyword-top-k",
        type=int,
        default=5,
        help="Keywords kept per article (default 5).",
    )
    parser.add_argument(
        "--keyword-batch-size",
        type=int,
        default=200,
        help="Rows per batch for keyword worker (default 200).",
    )
    parser.add_argument(
        "--classify-topics",
        action="store_true",
        help="Run topic classification over articles missing topics_json, then exit.",
    )
    parser.add_argument(
        "--topic-batch-size",
        type=int,
        default=200,
        help="Rows per batch for topic worker (default 200).",
    )
    parser.add_argument(
        "--llm-topic-fallback",
        action="store_true",
        help="Run LLM fallback over general_social_news rule-fallback articles. Also works standalone.",
    )
    parser.add_argument(
        "--topic-llm-batch-size",
        type=int,
        default=None,
        help="Rows per batch for LLM topic fallback (default from env).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = _build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )

    settings = load_settings(args.env_file)
    sources = build_tw_society_sources(settings)

    if args.smoke:
        return _smoke(sources, settings.limit_per_feed)

    if not settings.mysql_enabled:
        logger.error("NEWSPF_MYSQL_ENABLED=false; refusing to run")
        return 2

    store = NewsPlatformStore(settings)
    store.initialize()

    manual_batch_size = args.topic_llm_batch_size or settings.topic_llm_batch_size
    exit_code = 0

    if args.extract_keywords:
        exit_code = _extract_keywords(
            store,
            top_k=args.keyword_top_k,
            batch_size=args.keyword_batch_size,
        )
        if not args.classify_topics and not args.llm_topic_fallback:
            return exit_code

    if args.classify_topics:
        topic_exit_code = _classify_topics(store, batch_size=args.topic_batch_size)
        exit_code = max(exit_code, topic_exit_code)

    if args.llm_topic_fallback or (args.classify_topics and settings.topic_llm_enabled):
        llm_exit_code = _classify_topics_with_llm(store, settings, batch_size=manual_batch_size)
        exit_code = max(exit_code, llm_exit_code)

    if args.extract_keywords or args.classify_topics or args.llm_topic_fallback:
        return exit_code

    logger.info(
        "News-platform ready: db=%s sources=%s",
        settings.mysql_database,
        [s.name for s in sources],
    )

    if args.loop:
        return _loop(
            sources,
            store,
            poll_interval_seconds=settings.poll_interval_seconds,
            limit_per_feed=settings.limit_per_feed,
            keyword_top_k=args.keyword_top_k,
            keyword_batch_size=args.keyword_batch_size,
            topic_batch_size=args.topic_batch_size,
            topic_llm_enabled=settings.topic_llm_enabled,
            topic_llm_batch_size=manual_batch_size,
            settings=settings,
        )
    return _once(sources, store, settings.limit_per_feed)


def _once(sources, store, limit_per_feed: int) -> int:
    result = run_once(sources, store, limit_per_source=limit_per_feed)
    logger.info(
        "Cycle complete fetched=%d stored=%d duplicates=%d failed=%d",
        result.fetched,
        result.stored,
        result.duplicates,
        result.failed,
    )
    return 0


def _loop(
    sources,
    store,
    *,
    poll_interval_seconds: int,
    limit_per_feed: int,
    keyword_top_k: int,
    keyword_batch_size: int,
    topic_batch_size: int,
    topic_llm_enabled: bool,
    topic_llm_batch_size: int,
    settings: NewsPlatformSettings,
) -> int:
    """每輪：crawl → 抽詞 → 議題分類 → 等下一輪。

    KeywordExtractor 一次性建好重複用，jieba 字典只載一次。
    """
    extractor = KeywordExtractor(top_k=keyword_top_k)
    worker = KeywordWorker(store, extractor, batch_size=keyword_batch_size, top_k=keyword_top_k)
    topic_worker = TopicWorker(store, batch_size=topic_batch_size)
    topic_llm_worker = (
        TopicLlmFallbackWorker(
            store,
            TopicLlmClassifier(settings),
            batch_size=topic_llm_batch_size,
        )
        if topic_llm_enabled
        else None
    )
    stop_event = threading.Event()
    last_purge_date: date | None = None
    try:
        while not stop_event.is_set():
            _once(sources, store, limit_per_feed)
            kw_result = worker.run_until_drained()
            if kw_result.scanned:
                logger.info(
                    "Keyword pass scanned=%d updated=%d failed=%d",
                    kw_result.scanned,
                    kw_result.updated,
                    kw_result.failed,
                )
            topic_result = topic_worker.run_until_drained()
            if topic_result.scanned:
                logger.info(
                    "Topic pass scanned=%d updated=%d failed=%d",
                    topic_result.scanned,
                    topic_result.updated,
                    topic_result.failed,
                )
            if topic_llm_worker is not None:
                llm_result = topic_llm_worker.run_until_drained()
                if llm_result.scanned:
                    logger.info(
                        "Topic LLM fallback scanned=%d updated=%d failed=%d",
                        llm_result.scanned,
                        llm_result.updated,
                        llm_result.failed,
                    )
            # 一天 purge 一次過期 row 即可。記錄最後 purge 的 date，跨日才再跑。
            today = date.today()
            if last_purge_date != today:
                try:
                    deleted = store.purge_expired()
                    logger.info("TTL purge done date=%s deleted=%d", today.isoformat(), deleted)
                except Exception as exc:
                    logger.warning("TTL purge failed: %s", exc)
                last_purge_date = today
            stop_event.wait(max(poll_interval_seconds, 1))
    except KeyboardInterrupt:
        logger.info("News-platform interrupted by user")
    return 0


def _extract_keywords(store, *, top_k: int, batch_size: int) -> int:
    extractor = KeywordExtractor(top_k=top_k)
    worker = KeywordWorker(store, extractor, batch_size=batch_size, top_k=top_k)
    result = worker.run_until_drained()
    logger.info(
        "Keyword extraction done: scanned=%d updated=%d failed=%d",
        result.scanned,
        result.updated,
        result.failed,
    )
    return 0 if result.failed == 0 else 1


def _classify_topics(store, *, batch_size: int) -> int:
    worker = TopicWorker(store, batch_size=batch_size)
    result = worker.run_until_drained()
    logger.info(
        "Topic classification done: scanned=%d updated=%d failed=%d",
        result.scanned,
        result.updated,
        result.failed,
    )
    return 0 if result.failed == 0 else 1


def _classify_topics_with_llm(store, settings: NewsPlatformSettings, *, batch_size: int) -> int:
    worker = TopicLlmFallbackWorker(
        store,
        TopicLlmClassifier(settings),
        batch_size=batch_size,
    )
    result = worker.run_until_drained()
    logger.info(
        "Topic LLM fallback done: scanned=%d updated=%d failed=%d",
        result.scanned,
        result.updated,
        result.failed,
    )
    return 0 if result.failed == 0 else 1


def _smoke(sources, limit_per_feed: int) -> int:
    logger.info("Smoke mode: fetch + parse only, no DB.")
    articles = fetch_all(sources, limit_per_source=limit_per_feed)
    by_source: dict[str, int] = {}
    for art in articles:
        by_source[art.source_id] = by_source.get(art.source_id, 0) + 1
    expected = {src.source_id for src in sources}
    missing = sorted(s for s in expected if by_source.get(s, 0) == 0)
    for src in sources:
        count = by_source.get(src.source_id, 0)
        sample = next((a.title for a in articles if a.source_id == src.source_id), "-")
        logger.info("[SMOKE] source=%s count=%d sample=%s", src.name, count, sample)
    if missing:
        logger.warning("[SMOKE] sources with zero items: %s", missing)
        return 1
    logger.info("[SMOKE] total=%d sources_ok=%d", len(articles), len(expected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
