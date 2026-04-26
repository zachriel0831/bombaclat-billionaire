from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from event_relay.config import load_settings as load_relay_settings
from event_relay.service import MySqlEventStore, RelayEvent
from news_collector.collector import build_sources, fetch_news
from news_collector.config import load_settings, resolve_x_bearer_token
from news_collector.sources.x_accounts import XAccountSource
from news_collector.us_index_tracker import UsIndexTracker
from news_collector.utils import sort_timestamp
from news_collector.x_stream import XFilteredStreamer, XStreamConfig

logger = logging.getLogger(__name__)

TOPIC_INCLUDE_KEYWORDS = (
    "politics",
    "political",
    "election",
    "government",
    "diplomacy",
    "sanction",
    "war",
    "conflict",
    "summit",
    "international",
    "global",
    "finance",
    "financial",
    "economy",
    "economic",
    "market",
    "stocks",
    "inflation",
    "recession",
    "central bank",
    "interest rate",
    "gdp",
    "treasury",
    "technology",
    "tech",
    "ai",
    "artificial intelligence",
    "semiconductor",
    "chip",
    "software",
    "cybersecurity",
    "cloud",
    "data center",
    # Chinese keywords
    "\u653f\u6cbb",
    "\u570b\u969b",
    "\u56fd\u9645",
    "\u5916\u4ea4",
    "\u5236\u88c1",
    "\u6230\u722d",
    "\u6218\u4e89",
    "\u885d\u7a81",
    "\u51b2\u7a81",
    "\u5cf0\u6703",
    "\u5cf0\u4f1a",
    "\u8ca1\u7d93",
    "\u8d22\u7ecf",
    "\u7d93\u6fdf",
    "\u7ecf\u6d4e",
    "\u5e02\u5834",
    "\u5e02\u573a",
    "\u80a1\u5e02",
    "\u901a\u81a8",
    "\u79d1\u6280",
    "\u534a\u5c0e\u9ad4",  # 半導體
    "\u534a\u5bfc\u4f53",  # 半导体
    "\u6676\u7247",  # 晶片
    "\u82af\u7247",
    "\u4eba\u5de5\u667a\u6167",
    "\u4eba\u5de5\u667a\u80fd",
)

TOPIC_EXCLUDE_KEYWORDS = (
    "entertainment",
    "celebrity",
    "movie",
    "film",
    "music",
    "tv",
    "showbiz",
    "sports",
    "football",
    "soccer",
    "basketball",
    "baseball",
    "tennis",
    "nfl",
    "nba",
    "nhl",
    "mlb",
    "fifa",
    "hollywood",
    "anime",
    "wrestling",
    # Chinese entertainment/sports terms
    "\u5a1b\u6a02",
    "\u5a31\u4e50",
    "\u5f71\u8996",
    "\u5f71\u89c6",
    "\u96fb\u5f71",
    "\u7535\u5f71",
    "\u97f3\u6a02",
    "\u97f3\u4e50",
    "\u9ad4\u80b2",
    "\u4f53\u80b2",
    "\u8db3\u7403",
    "\u7c43\u7403",
    "\u7bee\u7403",
    "\u68d2\u7403",
    "\u7d9c\u85dd",
    "\u7efc\u827a",
    "\u516b\u5366",
    "\u660e\u661f",
)


@dataclass(frozen=True)
class BridgeConfig:
    """封裝 Bridge Config 相關資料與行為。"""
    relay_url: str
    env_file: str
    poll_interval_seconds: int
    limit_per_source: int
    log_level: str
    x_stream_timeout_seconds: int
    x_stream_reconnect_max_seconds: int
    us_index_enabled: bool
    us_index_poll_interval_seconds: int
    event_sink: str


@dataclass(frozen=True)
class EventSubmitResult:
    """封裝 Event Submit Result 相關資料與行為。"""
    status: str
    accepted: bool
    stored: bool = False


class DirectDbEventSink:
    """封裝 Direct Db Event Sink 相關資料與行為。"""
    def __init__(self, store: MySqlEventStore) -> None:
        """初始化物件狀態與必要依賴。"""
        self._store = store

    def submit(self, event: dict[str, Any]) -> EventSubmitResult:
        """執行 submit 方法的主要邏輯。"""
        relay_event = _event_to_relay_event(event)
        if relay_event is None:
            return EventSubmitResult(status="dropped_invalid", accepted=False)

        if relay_event.log_only:
            logger.info(
                "[BRIDGE_LOG_ONLY_EVENT] source=%s id=%s title=%s url=%s",
                relay_event.source,
                relay_event.event_id or "-",
                relay_event.title,
                relay_event.url,
            )
            return EventSubmitResult(status="logged_only", accepted=True)

        try:
            inserted = self._store.enqueue_event_if_new(relay_event)
        except Exception as exc:
            logger.exception(
                "Bridge DB store failed source=%s id=%s url=%s error=%s",
                relay_event.source,
                relay_event.event_id or "-",
                relay_event.url,
                exc,
            )
            return EventSubmitResult(status="failed", accepted=False)

        if inserted:
            logger.info(
                "[BRIDGE_DB_STORED] id=%s source=%s url=%s",
                relay_event.event_id or "-",
                relay_event.source,
                relay_event.url,
            )
            return EventSubmitResult(status="stored", accepted=True, stored=True)

        logger.debug(
            "[BRIDGE_DB_DUPLICATE] id=%s source=%s url=%s",
            relay_event.event_id or "-",
            relay_event.source,
            relay_event.url,
        )
        return EventSubmitResult(status="duplicate", accepted=True, stored=False)


def _allow_event_topic(event: dict[str, Any]) -> bool:
    """執行 allow event topic 的主要流程。"""
    title = str(event.get("title") or "")
    summary = str(event.get("summary") or "")
    url = str(event.get("url") or "")
    source = str(event.get("source") or "")
    if source.lower().startswith("x:") or source.lower().startswith("sec:") or source.lower().startswith("twse_mops:"):
        # X account tracking, SEC filing tracking, and TWSE/MOPS tracked announcements are explicit allow-list modes.
        return True
    text = f"{title} {summary} {url} {source}".lower()

    if any(keyword in text for keyword in TOPIC_EXCLUDE_KEYWORDS):
        return False
    return any(keyword in text for keyword in TOPIC_INCLUDE_KEYWORDS)


def _parse_published_at(value: Any) -> datetime | None:
    """解析 parse published at 對應的資料或結果。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def _allow_event_date(event: dict[str, Any]) -> bool:
    # Allow events from today and previous 2 days (local timezone).
    """執行 allow event date 的主要流程。"""
    published = _parse_published_at(event.get("published_at"))
    if published is None:
        return False

    today_local = datetime.now().astimezone().date()
    earliest_allowed = today_local - timedelta(days=2)
    return published.date() >= earliest_allowed


def _normalize_summary(value: str) -> str:
    """正規化 normalize summary 對應的資料或結果。"""
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text[:1200]


def _event_to_relay_event(event: dict[str, Any]) -> RelayEvent | None:
    """執行 event to relay event 的主要流程。"""
    title = " ".join(str(event.get("title") or "").split()).strip()
    url = str(event.get("url") or "").strip()
    source = str(event.get("source") or "unknown").strip() or "unknown"
    published_at = str(event.get("published_at") or "").strip() or None
    if not title or not url:
        return None
    # bridge 入口先做一次時間窗過濾，避免 stale event 進 DB 後再靠 downstream 清掉。
    if not _allow_event_date(event):
        return None

    return RelayEvent(
        event_id=str(event.get("id") or event.get("event_id") or ""),
        source=source,
        title=title,
        url=url,
        summary=_normalize_summary(str(event.get("summary") or "")),
        published_at=published_at,
        log_only=bool(event.get("test_only")) or source.lower().startswith("manual_test"),
        raw=event,
    )


def _post_event(relay_url: str, event: dict[str, Any], timeout_seconds: int = 8) -> bool:
    """送出 post event 對應的資料或結果。"""
    body = json.dumps(event, ensure_ascii=False).encode("utf-8")
    req = Request(relay_url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            code = int(getattr(resp, "status", 0))
            if code != 200:
                logger.warning("Relay rejected event status=%s source=%s url=%s", code, event.get("source"), event.get("url"))
                return False
            return True
    except HTTPError as exc:
        logger.warning("Relay HTTPError status=%s source=%s url=%s", exc.code, event.get("source"), event.get("url"))
        return False
    except URLError as exc:
        logger.warning("Relay URLError source=%s url=%s error=%s", event.get("source"), event.get("url"), exc)
        return False
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.warning("Relay post failed source=%s url=%s error=%s", event.get("source"), event.get("url"), exc)
        return False


def _submit_event(
    event_sink: DirectDbEventSink | None,
    relay_url: str,
    event: dict[str, Any],
) -> EventSubmitResult:
    """執行 submit event 的主要流程。"""
    if event_sink is not None:
        return event_sink.submit(event)

    if _post_event(relay_url, event):
        return EventSubmitResult(status="posted", accepted=True)
    return EventSubmitResult(status="failed", accepted=False)


def _build_event_sink(config: BridgeConfig) -> DirectDbEventSink | None:
    """建立 build event sink 對應的資料或結果。"""
    if config.event_sink == "relay":
        logger.info("Bridge event sink: relay HTTP endpoint=%s", config.relay_url)
        return None

    relay_settings = load_relay_settings(config.env_file)
    if not relay_settings.mysql_enabled:
        raise RuntimeError("direct-db event sink requires RELAY_MYSQL_ENABLED=true")

    store = MySqlEventStore(relay_settings)
    store.initialize()
    logger.info(
        "Bridge event sink: direct DB %s:%s/%s event_table=%s x_table=%s market_table=%s",
        relay_settings.mysql_host,
        relay_settings.mysql_port,
        relay_settings.mysql_database,
        relay_settings.mysql_event_table,
        relay_settings.mysql_x_table,
        relay_settings.mysql_market_table,
    )
    return DirectDbEventSink(store)


def _poll_loop(config: BridgeConfig, event_sink: DirectDbEventSink | None, stop_event: threading.Event) -> None:
    """執行 poll loop 的主要流程。"""
    while not stop_event.is_set():
        settings = load_settings(config.env_file)
        # 依當前 .env 即時決定要不要帶上 SEC / TWSE，讓 operator 調設定後不用重改程式。
        source_names = ["rss"]
        if settings.sec_enabled and settings.sec_tracked_tickers:
            source_names.append("sec")
        if settings.twse_mops_enabled and settings.twse_mops_tracked_codes:
            source_names.append("twse")
        accepted = 0
        stored = 0
        duplicates = 0
        failed = 0
        dropped_by_topic = 0
        dropped_by_date = 0

        for source_name in source_names:
            if stop_event.is_set():
                return

            try:
                sources = build_sources(settings, source_name)
                items = fetch_news(sources, config.limit_per_source)
                logger.info("Polling source=%s fetched=%d", source_name, len(items))

                for item in items:
                    if not item.url:
                        continue
                    event = item.to_dict()

                    # poll sources 會先做日期/主題兩層過濾，再決定是否真的寫庫；
                    # 這樣 RSS 雜訊不會進到 relay_event 去重與分析上下文。
                    if not _allow_event_date(event):
                        dropped_by_date += 1
                        continue
                    if not _allow_event_topic(event):
                        dropped_by_topic += 1
                        continue

                    result = _submit_event(event_sink, config.relay_url, event)
                    if result.accepted:
                        accepted += 1
                    if result.stored:
                        stored += 1
                    elif result.status == "duplicate":
                        duplicates += 1
                    elif result.status == "failed":
                        failed += 1
            except Exception as exc:
                logger.exception("Polling failed source=%s error=%s", source_name, exc)

        logger.info(
            "Polling cycle complete accepted=%d stored=%d duplicates=%d failed=%d dropped_by_date=%d dropped_by_topic=%d next_in=%ss",
            accepted,
            stored,
            duplicates,
            failed,
            dropped_by_date,
            dropped_by_topic,
            config.poll_interval_seconds,
        )
        stop_event.wait(max(config.poll_interval_seconds, 1))


def _x_stream_loop(config: BridgeConfig, event_sink: DirectDbEventSink | None, stop_event: threading.Event) -> None:
    """執行 x stream loop 的主要流程。"""
    try:
        settings = load_settings(config.env_file)
        if not settings.x_enabled:
            logger.info("X stream bridge skipped: X_ENABLED=false")
            return

        token = resolve_x_bearer_token(settings)
        if not token:
            logger.warning("X stream bridge skipped: missing X bearer token")
            return

        if not settings.x_accounts:
            logger.warning("X stream bridge skipped: X_ACCOUNTS is empty")
            return

        # 先補洞、再接 live stream；這樣 bridge 掛掉再啟動時，比較不會漏掉重啟空窗期貼文。
        _run_x_backfill(config.relay_url, settings, token, event_sink=event_sink)

        streamer = XFilteredStreamer(
            XStreamConfig(
                bearer_token=token,
                accounts=settings.x_accounts,
                include_replies=settings.x_include_replies,
                include_retweets=settings.x_include_retweets,
                timeout_seconds=config.x_stream_timeout_seconds,
                reconnect_max_seconds=config.x_stream_reconnect_max_seconds,
                stop_on_429=settings.x_stop_on_429,
                auto_heal_too_many_connections=settings.x_auto_heal_too_many_connections,
                heal_cooldown_seconds=settings.x_heal_cooldown_seconds,
            )
        )

        def on_item(item: Any) -> None:
            """執行 on item 的主要流程。"""
            if stop_event.is_set():
                return
            event = item.to_dict()

            # stream 也沿用和 polling 一樣的日期/主題過濾，避免 live 路徑與 poll 路徑
            # 在資料品質上出現兩套規則。
            if not _allow_event_date(event):
                return
            if not _allow_event_topic(event):
                return

            result = _submit_event(event_sink, config.relay_url, event)
            if result.accepted:
                logger.info(
                    "[BRIDGE_X_STREAM_SUBMITTED] id=%s source=%s url=%s status=%s",
                    event.get("id", "-"),
                    event.get("source", "-"),
                    event.get("url", "-"),
                    result.status,
                )

        logger.info("Starting X account stream accounts=%s", ",".join(settings.x_accounts))
        streamer.run(on_item=on_item, stop_event=stop_event)
    except Exception as exc:
        logger.warning("X stream bridge stopped: %s", exc)


def _run_x_backfill(
    relay_url: str,
    settings: Any,
    bearer_token: str,
    event_sink: DirectDbEventSink | None = None,
) -> dict[str, int]:
    """執行 run x backfill 的主要流程。"""
    if not getattr(settings, "x_backfill_enabled", True):
        logger.info("X startup backfill skipped: X_BACKFILL_ENABLED=false")
        return {"fetched": 0, "pushed": 0, "stored": 0, "duplicates": 0, "failed": 0, "dropped_by_date": 0, "dropped_by_topic": 0}

    source = XAccountSource(
        bearer_token=bearer_token,
        accounts=list(settings.x_accounts),
        timeout_seconds=settings.http_timeout_seconds,
        max_results_per_account=settings.x_backfill_max_results_per_account,
        stop_on_429=settings.x_stop_on_429,
        include_replies=settings.x_include_replies,
        include_retweets=settings.x_include_retweets,
    )
    items = source.fetch(limit=settings.x_backfill_max_results_per_account)
    if not items:
        logger.info("X startup backfill fetched=0")
        return {"fetched": 0, "pushed": 0, "stored": 0, "duplicates": 0, "failed": 0, "dropped_by_date": 0, "dropped_by_topic": 0}

    pushed = 0
    stored = 0
    duplicates = 0
    failed = 0
    dropped_by_date = 0
    dropped_by_topic = 0

    # 補洞時刻意用 oldest-first 回放，讓恢復期間寫入 DB 的順序更接近真實發文順序。
    replay_items = sorted(items, key=lambda item: sort_timestamp(item.published_at))
    for item in replay_items:
        event = item.to_dict()
        if not _allow_event_date(event):
            dropped_by_date += 1
            continue
        if not _allow_event_topic(event):
            dropped_by_topic += 1
            continue

        result = _submit_event(event_sink, relay_url, event)
        if result.accepted:
            pushed += 1
            if result.stored:
                stored += 1
            elif result.status == "duplicate":
                duplicates += 1
            logger.info(
                "[BRIDGE_X_BACKFILL_SUBMITTED] id=%s source=%s url=%s status=%s",
                event.get("id", "-"),
                event.get("source", "-"),
                event.get("url", "-"),
                result.status,
            )
        elif result.status == "failed":
            failed += 1

    logger.info(
        "X startup backfill complete fetched=%d pushed=%d stored=%d duplicates=%d failed=%d dropped_by_date=%d dropped_by_topic=%d",
        len(items),
        pushed,
        stored,
        duplicates,
        failed,
        dropped_by_date,
        dropped_by_topic,
    )
    return {
        "fetched": len(items),
        "pushed": pushed,
        "stored": stored,
        "duplicates": duplicates,
        "failed": failed,
        "dropped_by_date": dropped_by_date,
        "dropped_by_topic": dropped_by_topic,
    }


def _build_us_index_event(session: str, trade_day: str, message: str, quotes: dict[str, Any]) -> dict[str, Any]:
    """建立 build us index event 對應的資料或結果。"""
    normalized_session = session.strip().lower()
    title = f"US index {normalized_session} {trade_day}"
    summary = " ".join(line.strip() for line in str(message or "").splitlines() if line.strip())
    primary_url = ""
    for quote in quotes.values():
        candidate = str(getattr(quote, "url", "") or "").strip()
        if candidate:
            primary_url = candidate
            break
    return {
        "id": f"us_index_{normalized_session}_{trade_day}",
        "source": "us_index_tracker",
        "title": title,
        "url": primary_url,
        "summary": summary[:4000],
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market_snapshot": {
            "trade_date": trade_day,
            "session": normalized_session,
            "indexes": [_quote_to_payload(q) for q in quotes.values()],
        },
    }


def _us_index_direct_loop(config: BridgeConfig, event_sink: DirectDbEventSink | None, stop_event: threading.Event) -> None:
    """執行 us index direct loop 的主要流程。"""
    if not config.us_index_enabled:
        logger.info("US index event bridge skipped: disabled")
        return

    tracker = UsIndexTracker(timeout_seconds=12)
    open_sent_dates: set[str] = set()
    close_sent_dates: set[str] = set()

    while not stop_event.is_set():
        try:
            trade_date, quotes = tracker.fetch_snapshot()
            if trade_date is not None and quotes:
                trade_day = trade_date.isoformat()
                now_epoch = int(datetime.now(timezone.utc).timestamp())

                start_epoch = min(q.regular_start_epoch for q in quotes.values())
                end_epoch = max(q.regular_end_epoch for q in quotes.values())

                # 只在開盤/收盤後的有限時間窗內各送一次，避免 bridge 長駐時同一交易日重複寫很多筆。
                open_window = 0 <= now_epoch - start_epoch <= 8 * 3600
                close_window = 0 <= now_epoch - end_epoch <= 8 * 3600

                if open_window and trade_day not in open_sent_dates:
                    message = tracker.format_open_message(trade_date, quotes)
                    payload = _build_us_index_event("open", trade_day, message, quotes)
                    result = _submit_event(event_sink, config.relay_url, payload)
                    if result.accepted:
                        open_sent_dates.add(trade_day)
                        logger.info("[US_INDEX_OPEN_STORED] trade_date=%s status=%s", trade_day, result.status)

                if close_window and trade_day not in close_sent_dates:
                    message = tracker.format_close_message(trade_date, quotes)
                    payload = _build_us_index_event("close", trade_day, message, quotes)
                    result = _submit_event(event_sink, config.relay_url, payload)
                    if result.accepted:
                        close_sent_dates.add(trade_day)
                        logger.info("[US_INDEX_CLOSE_STORED] trade_date=%s status=%s", trade_day, result.status)
        except Exception as exc:
            logger.warning("US index tracking failed: %s", exc)

        stop_event.wait(max(config.us_index_poll_interval_seconds, 5))


def _quote_to_payload(quote: Any) -> dict[str, Any]:
    """執行 quote to payload 的主要流程。"""
    return {
        "symbol": getattr(quote, "symbol", ""),
        "label": getattr(quote, "label", ""),
        "url": getattr(quote, "url", ""),
        "open_price": getattr(quote, "open_price", None),
        "last_price": getattr(quote, "last_price", None),
        "regular_start_epoch": getattr(quote, "regular_start_epoch", None),
        "regular_end_epoch": getattr(quote, "regular_end_epoch", None),
    }


def _build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(description="Bridge all news sources into the crawler-owned event store")
    parser.add_argument("--relay-url", default="http://127.0.0.1:18090/events", help="Compatibility event relay /events endpoint")
    parser.add_argument(
        "--event-sink",
        default="direct-db",
        choices=["direct-db", "relay"],
        help="Where normalized events are written. Default direct-db writes MySQL without the event relay API.",
    )
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--poll-interval-seconds", type=int, default=300, help="Polling interval for RSS only")
    parser.add_argument("--limit", type=int, default=5, help="Per-source fetch limit for RSS")
    parser.add_argument("--x-stream-timeout-seconds", type=int, default=90, help="X stream read timeout seconds")
    parser.add_argument(
        "--x-stream-reconnect-max-seconds",
        type=int,
        default=120,
        help="Max reconnect backoff for X stream",
    )
    parser.add_argument("--us-index-poll-interval-seconds", type=int, default=30, help="US index polling cadence")
    parser.add_argument("--disable-us-index", action="store_true", help="Disable US index stored-only event chain")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    return parser


def main() -> int:
    """程式入口，負責執行此模組的主要流程。"""
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

    config = BridgeConfig(
        relay_url=args.relay_url,
        env_file=args.env_file,
        poll_interval_seconds=max(args.poll_interval_seconds, 1),
        limit_per_source=max(args.limit, 1),
        log_level=args.log_level,
        x_stream_timeout_seconds=max(args.x_stream_timeout_seconds, 15),
        x_stream_reconnect_max_seconds=max(args.x_stream_reconnect_max_seconds, 5),
        us_index_enabled=not args.disable_us_index,
        us_index_poll_interval_seconds=max(args.us_index_poll_interval_seconds, 5),
        event_sink=args.event_sink,
    )

    stop_event = threading.Event()
    event_sink = _build_event_sink(config)

    poll_thread = threading.Thread(target=_poll_loop, args=(config, event_sink, stop_event), daemon=True, name="bridge-poll")
    x_stream_thread = threading.Thread(
        target=_x_stream_loop,
        args=(config, event_sink, stop_event),
        daemon=True,
        name="bridge-x-stream",
    )
    us_index_thread = threading.Thread(
        target=_us_index_direct_loop,
        args=(config, event_sink, stop_event),
        daemon=True,
        name="bridge-us-index",
    )

    poll_thread.start()
    x_stream_thread.start()
    us_index_thread.start()
    logger.info("Bridge started event_sink=%s relay_url=%s", config.event_sink, config.relay_url)

    try:
        poll_thread.join()
        x_stream_thread.join()
        us_index_thread.join()
        return 0
    except KeyboardInterrupt:
        logger.info("Bridge interrupted by user")
        stop_event.set()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
