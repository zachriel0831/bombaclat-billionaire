from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import time

from news_collector.config import Settings, resolve_benzinga_api_key, resolve_x_bearer_token
from news_collector.models import NewsItem
from news_collector.sources.base import NewsSource
from news_collector.sources.benzinga import BenzingaSource
from news_collector.sources.gdelt import GdeltSource
from news_collector.sources.rss import OfficialRssSource
from news_collector.sources.x_accounts import XAccountSource
from news_collector.utils import sort_timestamp


logger = logging.getLogger(__name__)


def build_sources(settings: Settings, source_name: str) -> list[NewsSource]:
    selected = source_name.lower()

    sources: list[NewsSource] = []
    # 來源選擇策略：先支援無 key 來源，付費來源在 key 存在時才啟用。
    if selected in ("all", "rss"):
        sources.append(
            OfficialRssSource(
                settings.official_rss_feeds,
                settings.http_timeout_seconds,
                first_per_feed=settings.official_rss_first_per_feed,
            )
        )

    if selected in ("all", "gdelt"):
        sources.append(
            GdeltSource(
                settings.gdelt_query,
                settings.gdelt_max_records,
                settings.http_timeout_seconds,
                cooldown_on_429=settings.gdelt_cooldown_on_429,
                cooldown_seconds=settings.gdelt_cooldown_seconds,
            )
        )

    if selected in ("all", "benzinga"):
        if not settings.benzinga_enabled:
            if selected == "benzinga":
                raise ValueError("Benzinga source is disabled. Set BENZINGA_ENABLED=true to enable.")
            logger.info("Skip source=benzinga because BENZINGA_ENABLED=false")
        else:
            benzinga_key = resolve_benzinga_api_key(settings)
            if not benzinga_key:
                if selected == "benzinga":
                    raise ValueError(
                        "BENZINGA_API_KEY is missing. Set env or store encrypted key in BENZINGA_API_KEY_FILE."
                    )
            else:
                sources.append(BenzingaSource(benzinga_key, settings.http_timeout_seconds))

    if selected in ("all", "x"):
        if not settings.x_enabled:
            if selected == "x":
                raise ValueError("X source is disabled. Set X_ENABLED=true to enable.")
            logger.info("Skip source=x because X_ENABLED=false")
        else:
            token = resolve_x_bearer_token(settings)
            if not token:
                if selected == "x":
                    raise ValueError("X_BEARER_TOKEN is missing. Set env or store encrypted key in X_BEARER_TOKEN_FILE.")
                logger.info("Skip source=x because X_BEARER_TOKEN is missing")
            elif not settings.x_accounts:
                if selected == "x":
                    raise ValueError("X_ACCOUNTS is empty. Add usernames or profile URLs.")
                logger.info("Skip source=x because X_ACCOUNTS is empty")
            else:
                sources.append(
                    XAccountSource(
                        bearer_token=token,
                        accounts=settings.x_accounts,
                        timeout_seconds=settings.http_timeout_seconds,
                        max_results_per_account=settings.x_max_results_per_account,
                        stop_on_429=settings.x_stop_on_429,
                        include_replies=settings.x_include_replies,
                        include_retweets=settings.x_include_retweets,
                    )
                )

    if not sources:
        raise ValueError(f"No source enabled for source='{source_name}'.")

    logger.info("Enabled sources: %s", ", ".join(src.name for src in sources))
    return sources


def fetch_news(sources: list[NewsSource], limit_per_source: int = 20) -> list[NewsItem]:
    logger.info("Starting fetch run: sources=%d, limit_per_source=%d", len(sources), limit_per_source)
    items: list[NewsItem] = []

    # 每個來源平行抓取，降低整體等待時間；單一來源失敗不影響其他來源。
    with ThreadPoolExecutor(max_workers=min(8, len(sources) or 1)) as executor:
        future_map: dict = {}
        for src in sources:
            started = time.perf_counter()
            logger.info("Fetching source=%s", src.name)
            future = executor.submit(src.fetch, limit_per_source)
            future_map[future] = (src.name, started)

        for fut in as_completed(future_map):
            source_name, started = future_map[fut]
            try:
                fetched = fut.result()
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.info("Fetched source=%s items=%d elapsed_ms=%d", source_name, len(fetched), elapsed_ms)
                items.extend(fetched)
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.warning(
                    "Fetch failed source=%s elapsed_ms=%d error=%s",
                    source_name,
                    elapsed_ms,
                    exc,
                )
                items.append(
                    NewsItem(
                        id=f"error-{source_name}",
                        source=source_name,
                        title=f"Failed to fetch from source: {source_name}",
                        url="",
                        published_at=None,
                        summary=str(exc),
                        tags=["error"],
                        raw={"source": source_name, "error": str(exc)},
                    )
                )

    # 聚合後做去重與時間排序，回傳給上游推播或儲存流程。
    deduped = _dedupe(items)
    deduped.sort(key=lambda x: sort_timestamp(x.published_at), reverse=True)
    logger.info("Fetch completed: total_items=%d deduped_items=%d", len(items), len(deduped))
    return deduped


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    # 先用 URL 去重；若無 URL，退化為 source+title key。
    seen: set[str] = set()
    output: list[NewsItem] = []
    for item in items:
        key = item.url.strip() or f"{item.source}:{item.title.strip().lower()}"
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output
