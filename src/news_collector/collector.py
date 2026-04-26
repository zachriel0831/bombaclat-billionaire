"""Top-level orchestrator for news source fan-out.

``build_sources()`` instantiates the configured ``NewsSource`` adapters
(RSS / SEC / TWSE-MOPS / X) from settings; ``fetch_news()`` runs them in
parallel and returns merged ``NewsItem`` rows ready for the relay bridge."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import time

from news_collector.config import Settings, resolve_x_bearer_token
from news_collector.models import NewsItem
from news_collector.sources.base import NewsSource
from news_collector.sources.rss import OfficialRssSource
from news_collector.sources.sec_filings import SecFilingsSource
from news_collector.sources.twse_mops_announcements import TwseMopsAnnouncementsSource
from news_collector.sources.x_accounts import XAccountSource
from news_collector.utils import sort_timestamp


logger = logging.getLogger(__name__)


def build_sources(settings: Settings, source_name: str) -> list[NewsSource]:
    """建立 build sources 對應的資料或結果。"""
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

    if selected in ("all", "sec"):
        if not settings.sec_enabled:
            if selected == "sec":
                raise ValueError("SEC source is disabled. Set SEC_ENABLED=true to enable.")
            logger.info("Skip source=sec because SEC_ENABLED=false")
        elif not settings.sec_user_agent:
            if selected == "sec":
                raise ValueError("SEC_USER_AGENT is required for SEC EDGAR access.")
            logger.info("Skip source=sec because SEC_USER_AGENT is empty")
        elif not settings.sec_tracked_tickers:
            if selected == "sec":
                raise ValueError("SEC_TRACKED_TICKERS is empty. Add ticker symbols such as NVDA,TSM.")
            logger.info("Skip source=sec because SEC_TRACKED_TICKERS is empty")
        else:
            sources.append(
                SecFilingsSource(
                    user_agent=settings.sec_user_agent,
                    tracked_tickers=settings.sec_tracked_tickers,
                    allowed_forms=settings.sec_allowed_forms,
                    timeout_seconds=settings.http_timeout_seconds,
                    max_filings_per_company=settings.sec_max_filings_per_company,
                )
            )

    if selected in ("all", "twse"):
        if not settings.twse_mops_enabled:
            if selected == "twse":
                raise ValueError("TWSE/MOPS source is disabled. Set TWSE_MOPS_ENABLED=true to enable.")
            logger.info("Skip source=twse because TWSE_MOPS_ENABLED=false")
        elif not settings.twse_mops_tracked_codes:
            if selected == "twse":
                raise ValueError("TWSE_MOPS_TRACKED_CODES is empty. Add TWSE listed company codes such as 2330,2317.")
            logger.info("Skip source=twse because TWSE_MOPS_TRACKED_CODES is empty")
        else:
            sources.append(
                TwseMopsAnnouncementsSource(
                    tracked_codes=settings.twse_mops_tracked_codes,
                    timeout_seconds=settings.http_timeout_seconds,
                    max_items_per_company=settings.twse_mops_max_items_per_company,
                )
            )

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
    """抓取 fetch news 對應的資料或結果。"""
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
    """依穩定鍵移除重複資料。"""
    seen: set[str] = set()
    output: list[NewsItem] = []
    for item in items:
        key = item.url.strip() or f"{item.source}:{item.title.strip().lower()}"
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output
