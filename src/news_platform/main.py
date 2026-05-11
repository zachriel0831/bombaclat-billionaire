"""News-platform CLI 入口 — 跑一次或循環抓 TW 社會／政治新聞。

用法：
    PYTHONPATH=src .venv/Scripts/python.exe -m news_platform.main --once
    PYTHONPATH=src .venv/Scripts/python.exe -m news_platform.main --loop
    PYTHONPATH=src .venv/Scripts/python.exe -m news_platform.main --smoke
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from datetime import date, datetime

from news_platform.config import NewsPlatformSettings, load_settings
from news_platform.keyword_extractor import KeywordExtractor
from news_platform.keyword_worker import KeywordWorker
from news_platform.pipeline import fetch_all, run_once
from news_platform.public_record_pipeline import fetch_all_public_records, run_public_records_once
from news_platform.public_sources.ly_legislative_bill import LegislativeBillSource
from news_platform.registry import FeedSpec, SUPPORTED_TW_CATEGORIES, tw_news_feeds
from news_platform.sources.base import NewsSource
from news_platform.sources.ettoday_list import EttodayNewsListSource
from news_platform.sources.pts_category import PtsCategorySource
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
    if spec.kind == "ettoday_list":
        return EttodayNewsListSource(
            source_id=spec.source_id,
            country="TW",
            category=spec.category,
            url=spec.url,
            timeout_seconds=settings.http_timeout_seconds,
            max_age_days=settings.max_age_days,
        )
    if spec.kind == "pts_category":
        return PtsCategorySource(
            source_id=spec.source_id,
            country="TW",
            category=spec.category,
            url=spec.url,
            timeout_seconds=settings.http_timeout_seconds,
            max_age_days=settings.max_age_days,
        )
    raise ValueError(f"Unknown feed kind: {spec.kind}")


def build_tw_news_sources(
    settings: NewsPlatformSettings,
    categories: tuple[str, ...] | None = None,
) -> list[NewsSource]:
    return [build_source(spec, settings) for spec in tw_news_feeds(categories=categories)]


def build_public_record_sources(
    settings: NewsPlatformSettings,
    *,
    source_names: tuple[str, ...],
    lookback_days: int,
):
    sources = []
    for name in source_names:
        if name == "ly_bills":
            sources.append(
                LegislativeBillSource(
                    timeout_seconds=settings.http_timeout_seconds,
                    lookback_days=lookback_days,
                )
            )
            continue
        raise ValueError(f"Unsupported public record source: {name}. Supported: ly_bills")
    return sources


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TW news platform crawler")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--once", action="store_true", help="Run a single fetch+store cycle and exit")
    parser.add_argument("--loop", action="store_true", help="Run continuously on poll interval")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Fetch and parse only — no DB write. Use to verify feed URLs are alive.",
    )
    parser.add_argument(
        "--categories",
        default=None,
        help=(
            "Comma-separated categories to crawl. "
            f"Supported: {', '.join(SUPPORTED_TW_CATEGORIES)}. "
            "Default from NEWSPF_CATEGORIES or society,politics."
        ),
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
        help="Run LLM fallback over rule-fallback general topic articles. Also works standalone.",
    )
    parser.add_argument(
        "--collect-public-records",
        action="store_true",
        help="Fetch official structured public records and write them to t_public_records.",
    )
    parser.add_argument(
        "--public-records-smoke",
        action="store_true",
        help="Fetch official structured public records without DB writes.",
    )
    parser.add_argument(
        "--public-sources",
        default="ly_bills",
        help="Comma-separated public-record sources. Supported: ly_bills.",
    )
    parser.add_argument(
        "--public-record-lookback-days",
        type=int,
        default=14,
        help="Default lookback window for public-record sources (default 14).",
    )
    parser.add_argument(
        "--public-record-limit",
        type=int,
        default=None,
        help="Limit records per public-record source.",
    )
    parser.add_argument(
        "--public-record-from",
        default=None,
        help="Reserved for source-specific date windows; use YYYY-MM-DD.",
    )
    parser.add_argument(
        "--public-record-to",
        default=None,
        help="Reserved for source-specific date windows; use YYYY-MM-DD.",
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


def parse_categories(value: str | None) -> tuple[str, ...]:
    raw = value or os.getenv("NEWSPF_CATEGORIES", "society,politics")
    aliases = {
        "social": "society",
        "society": "society",
        "社會": "society",
        "politic": "politics",
        "politics": "politics",
        "政治": "politics",
    }
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    if not parts or any(item.lower() == "all" for item in parts):
        return SUPPORTED_TW_CATEGORIES

    categories: list[str] = []
    for item in parts:
        normalized = aliases.get(item.lower()) or aliases.get(item)
        if normalized not in SUPPORTED_TW_CATEGORIES:
            supported = ", ".join(SUPPORTED_TW_CATEGORIES)
            raise ValueError(f"Unsupported category: {item}. Supported: {supported}")
        if normalized not in categories:
            categories.append(normalized)
    return tuple(categories)


def parse_public_sources(value: str | None) -> tuple[str, ...]:
    raw = value or "ly_bills"
    sources: list[str] = []
    for item in raw.split(","):
        normalized = item.strip().lower().replace("-", "_")
        if not normalized:
            continue
        if normalized in {"all", "ly", "legislative_bill", "legislative_bills"}:
            normalized = "ly_bills"
        if normalized not in sources:
            sources.append(normalized)
    return tuple(sources or ["ly_bills"])


def _parse_cli_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


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
    try:
        categories = parse_categories(args.categories)
        sources = build_tw_news_sources(settings, categories)
        public_sources = build_public_record_sources(
            settings,
            source_names=parse_public_sources(args.public_sources),
            lookback_days=args.public_record_lookback_days,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    except Exception as exc:
        logger.error("Invalid public-record options: %s", exc)
        return 2

    if args.smoke:
        return _smoke(sources, settings.limit_per_feed)

    if args.public_records_smoke:
        return _public_records_smoke(
            public_sources,
            limit_per_source=args.public_record_limit,
            from_date=_parse_cli_date(args.public_record_from),
            to_date=_parse_cli_date(args.public_record_to),
        )

    if not settings.mysql_enabled:
        logger.error("NEWSPF_MYSQL_ENABLED=false; refusing to run")
        return 2

    store = NewsPlatformStore(settings)
    store.initialize()

    if args.collect_public_records:
        return _public_records_once(
            public_sources,
            store,
            limit_per_source=args.public_record_limit,
            from_date=_parse_cli_date(args.public_record_from),
            to_date=_parse_cli_date(args.public_record_to),
        )

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


def _public_records_once(
    sources,
    store,
    *,
    limit_per_source: int | None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> int:
    result = run_public_records_once(
        sources,
        store,
        limit_per_source=limit_per_source,
        fetch_kwargs=_public_record_fetch_kwargs(from_date, to_date),
    )
    logger.info(
        "Public records complete fetched=%d stored=%d duplicates=%d failed=%d",
        result.fetched,
        result.stored,
        result.duplicates,
        result.failed,
    )
    return 0 if result.failed == 0 else 1


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


def _public_records_smoke(
    sources,
    *,
    limit_per_source: int | None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> int:
    logger.info("Public-record smoke mode: fetch + parse only, no DB.")
    records = fetch_all_public_records(
        sources,
        limit_per_source=limit_per_source,
        fetch_kwargs=_public_record_fetch_kwargs(from_date, to_date),
    )
    by_source: dict[str, int] = {}
    for record in records:
        key = f"{record.source_id}:{record.record_type}"
        by_source[key] = by_source.get(key, 0) + 1
    for src in sources:
        key = f"{src.source_id}:{src.record_type}"
        sample = next((record.title for record in records if f"{record.source_id}:{record.record_type}" == key), "-")
        logger.info("[PUBLIC SMOKE] source=%s count=%d sample=%s", src.name, by_source.get(key, 0), sample)
    logger.info("[PUBLIC SMOKE] total=%d sources_ok=%d", len(records), len(sources))
    return 0 if records else 1


def _public_record_fetch_kwargs(from_date: date | None, to_date: date | None) -> dict:
    kwargs = {}
    if from_date is not None:
        kwargs["from_date"] = from_date
    if to_date is not None:
        kwargs["to_date"] = to_date
    return kwargs


def _smoke(sources, limit_per_feed: int) -> int:
    logger.info("Smoke mode: fetch + parse only, no DB.")
    articles = fetch_all(sources, limit_per_source=limit_per_feed)
    by_source: dict[str, int] = {}
    for art in articles:
        source_key = f"{art.source_id}:{art.category}"
        by_source[source_key] = by_source.get(source_key, 0) + 1
    expected = {src.name for src in sources}
    missing = sorted(s for s in expected if by_source.get(s, 0) == 0)
    for src in sources:
        category = getattr(src, "category", None)
        count = by_source.get(src.name, 0)
        sample = next(
            (
                a.title
                for a in articles
                if a.source_id == src.source_id and a.category == category
            ),
            "-",
        )
        logger.info("[SMOKE] source=%s count=%d sample=%s", src.name, count, sample)
    if missing:
        logger.warning("[SMOKE] sources with zero items: %s", missing)
        return 1
    logger.info("[SMOKE] total=%d sources_ok=%d", len(articles), len(expected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
