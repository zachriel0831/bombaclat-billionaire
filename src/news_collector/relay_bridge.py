from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from news_collector.benzinga_stream import BenzingaNewsStreamer, StreamConfig
from news_collector.collector import build_sources, fetch_news
from news_collector.config import load_settings, resolve_benzinga_api_key, resolve_x_bearer_token
from news_collector.us_index_tracker import UsIndexTracker
from news_collector.x_stream import XFilteredStreamer, XStreamConfig

logger = logging.getLogger(__name__)

BENZINGA_ALLOWED_URL_PREFIXES = (
    "https://www.benzinga.com/crypto/cryptocurrency/",
    "https://www.benzinga.com/news/topics/",
    "https://www.benzinga.com/markets/",
    "https://www.benzinga.com/news/politics",
)

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
    "\u653f\u6cbb",  # 政治
    "\u570b\u969b",  # 國際
    "\u56fd\u9645",  # 国际
    "\u5916\u4ea4",  # 外交
    "\u5236\u88c1",  # 制裁
    "\u6230\u722d",  # 戰爭
    "\u6218\u4e89",  # 战争
    "\u885d\u7a81",  # 衝突
    "\u51b2\u7a81",  # 冲突
    "\u5cf0\u6703",  # 峰會
    "\u5cf0\u4f1a",  # 峰会
    "\u8ca1\u7d93",  # 財經
    "\u8d22\u7ecf",  # 财经
    "\u7d93\u6fdf",  # 經濟
    "\u7ecf\u6d4e",  # 经济
    "\u5e02\u5834",  # 市場
    "\u5e02\u573a",  # 市场
    "\u80a1\u5e02",  # 股市
    "\u901a\u81a8",  # 通膨
    "\u79d1\u6280",  # 科技
    "\u534a\u5c0e\u9ad4",  # 半導體
    "\u534a\u5bfc\u4f53",  # 半导体
    "\u6676\u7247",  # 晶片
    "\u82af\u7247",  # 芯片
    "\u4eba\u5de5\u667a\u6167",  # 人工智慧
    "\u4eba\u5de5\u667a\u80fd",  # 人工智能
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
    "\u5a1b\u6a02",  # 娛樂
    "\u5a31\u4e50",  # 娱乐
    "\u5f71\u8996",  # 影視
    "\u5f71\u89c6",  # 影视
    "\u96fb\u5f71",  # 電影
    "\u7535\u5f71",  # 电影
    "\u97f3\u6a02",  # 音樂
    "\u97f3\u4e50",  # 音乐
    "\u9ad4\u80b2",  # 體育
    "\u4f53\u80b2",  # 体育
    "\u8db3\u7403",  # 足球
    "\u7c43\u7403",  # 籃球
    "\u7bee\u7403",  # 篮球
    "\u68d2\u7403",  # 棒球
    "\u7d9c\u85dd",  # 綜藝
    "\u7efc\u827a",  # 综艺
    "\u516b\u5366",  # 八卦
    "\u660e\u661f",  # 明星
)


@dataclass(frozen=True)
class BridgeConfig:
    relay_url: str
    relay_direct_push_url: str
    env_file: str
    poll_interval_seconds: int
    limit_per_source: int
    log_level: str
    benzinga_tickers: list[str]
    benzinga_channels: list[str]
    benzinga_languages: list[str]
    x_stream_timeout_seconds: int
    x_stream_reconnect_max_seconds: int
    us_index_enabled: bool
    us_index_poll_interval_seconds: int


def _normalize_benzinga_language(lang: str) -> str:
    normalized = lang.strip().lower()
    alias = {
        "cn": "zh",
        "zh-cn": "zh",
        "zh-tw": "zh",
        "english": "en",
        "chinese": "zh",
    }
    return alias.get(normalized, normalized)


def _allow_benzinga_url(url: str) -> bool:
    check = (url or "").strip().lower()
    if not check:
        return False
    return any(check.startswith(prefix.lower()) for prefix in BENZINGA_ALLOWED_URL_PREFIXES)


def _allow_event_topic(event: dict[str, Any]) -> bool:
    title = str(event.get("title") or "")
    summary = str(event.get("summary") or "")
    url = str(event.get("url") or "")
    source = str(event.get("source") or "")
    if source.lower().startswith("x:"):
        # X account tracking is explicit allow-list mode; do not apply topic keyword filter.
        return True
    text = f"{title} {summary} {url} {source}".lower()

    if any(keyword in text for keyword in TOPIC_EXCLUDE_KEYWORDS):
        return False
    return any(keyword in text for keyword in TOPIC_INCLUDE_KEYWORDS)


def _parse_published_at(value: Any) -> datetime | None:
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
    # Only allow events published today (local timezone) or in the future.
    published = _parse_published_at(event.get("published_at"))
    if published is None:
        return False

    today_local = datetime.now().astimezone().date()
    return published.date() >= today_local


def _post_event(relay_url: str, event: dict[str, Any], timeout_seconds: int = 8) -> bool:
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


def _post_direct_push(relay_url: str, payload: dict[str, Any], timeout_seconds: int = 8) -> bool:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(relay_url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            code = int(getattr(resp, "status", 0))
            if code != 200:
                logger.warning("Relay direct push rejected status=%s source=%s", code, payload.get("source"))
                return False
            return True
    except HTTPError as exc:
        logger.warning("Relay direct push HTTPError status=%s source=%s", exc.code, payload.get("source"))
        return False
    except URLError as exc:
        logger.warning("Relay direct push URLError source=%s error=%s", payload.get("source"), exc)
        return False
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.warning("Relay direct push failed source=%s error=%s", payload.get("source"), exc)
        return False


def _poll_loop(config: BridgeConfig, stop_event: threading.Event) -> None:
    # 輪巡僅保留 RSS/GDELT；X 改由串流執行緒近即時監聽。
    source_names = ["rss", "gdelt"]

    while not stop_event.is_set():
        settings = load_settings(config.env_file)
        pushed = 0
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

                    if not _allow_event_date(event):
                        dropped_by_date += 1
                        continue
                    if not _allow_event_topic(event):
                        dropped_by_topic += 1
                        continue

                    ok = _post_event(config.relay_url, event)
                    if ok:
                        pushed += 1
            except Exception as exc:
                logger.exception("Polling failed source=%s error=%s", source_name, exc)

        logger.info(
            "Polling cycle complete pushed=%d dropped_by_date=%d dropped_by_topic=%d next_in=%ss",
            pushed,
            dropped_by_date,
            dropped_by_topic,
            config.poll_interval_seconds,
        )
        stop_event.wait(max(config.poll_interval_seconds, 1))


def _stream_loop(config: BridgeConfig, stop_event: threading.Event) -> None:
    settings = load_settings(config.env_file)
    if not settings.benzinga_enabled:
        logger.info("Benzinga stream bridge skipped: BENZINGA_ENABLED=false")
        return

    api_key = resolve_benzinga_api_key(settings)
    if not api_key:
        logger.warning("Benzinga stream bridge skipped: missing API key")
        return

    def on_event(event: dict[str, Any]) -> None:
        if stop_event.is_set():
            return

        url = str(event.get("url") or "").strip()
        if not url:
            return
        if not _allow_event_date(event):
            return
        if not _allow_benzinga_url(url):
            logger.debug("Drop benzinga event by url rule id=%s url=%s", event.get("id", "-"), url)
            return

        ok = _post_event(config.relay_url, event)
        if ok:
            logger.info(
                "[BRIDGE_STREAM_SENT] id=%s source=%s url=%s",
                event.get("id", "-"),
                event.get("source", "-"),
                event.get("url", "-"),
            )

    streamer = BenzingaNewsStreamer(
        StreamConfig(
            api_key=api_key,
            tickers=config.benzinga_tickers,
            channels=config.benzinga_channels,
            languages=config.benzinga_languages,
            timeout_seconds=30,
            reconnect_max_seconds=60,
            stop_on_429=settings.benzinga_stop_on_429,
        )
    )

    logger.info(
        "Starting Benzinga bridge stream tickers=%s channels=%s languages=%s",
        ",".join(config.benzinga_tickers) or "-",
        ",".join(config.benzinga_channels) or "-",
        ",".join(config.benzinga_languages) or "all",
    )
    streamer.run(on_event=on_event, max_messages=None, duration_seconds=None)


def _x_stream_loop(config: BridgeConfig, stop_event: threading.Event) -> None:
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

    streamer = XFilteredStreamer(
        XStreamConfig(
            bearer_token=token,
            accounts=settings.x_accounts,
            include_replies=settings.x_include_replies,
            include_retweets=settings.x_include_retweets,
            timeout_seconds=config.x_stream_timeout_seconds,
            reconnect_max_seconds=config.x_stream_reconnect_max_seconds,
            stop_on_429=settings.x_stop_on_429,
        )
    )

    def on_item(item: Any) -> None:
        if stop_event.is_set():
            return
        event = item.to_dict()

        if not _allow_event_date(event):
            return
        if not _allow_event_topic(event):
            return

        ok = _post_event(config.relay_url, event)
        if ok:
            logger.info(
                "[BRIDGE_X_STREAM_SENT] id=%s source=%s url=%s",
                event.get("id", "-"),
                event.get("source", "-"),
                event.get("url", "-"),
            )

    logger.info("Starting X account stream accounts=%s", ",".join(settings.x_accounts))
    streamer.run(on_item=on_item, stop_event=stop_event)


def _us_index_direct_loop(config: BridgeConfig, stop_event: threading.Event) -> None:
    if not config.us_index_enabled:
        logger.info("US index direct push skipped: disabled")
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

                # 僅在本交易日時間窗內發送，避免服務重啟時補推過期交易日。
                open_window = 0 <= now_epoch - start_epoch <= 8 * 3600
                close_window = 0 <= now_epoch - end_epoch <= 8 * 3600

                if open_window and trade_day not in open_sent_dates:
                    message = tracker.format_open_message(trade_date, quotes)
                    payload = {
                        "source": "us_index_tracker",
                        "title": f"US index open {trade_day}",
                        "text": message,
                        "event_id": f"us_index_open_{trade_day}",
                    }
                    if _post_direct_push(config.relay_direct_push_url, payload):
                        open_sent_dates.add(trade_day)
                        logger.info("[US_INDEX_OPEN_PUSHED] trade_date=%s", trade_day)

                if close_window and trade_day not in close_sent_dates:
                    message = tracker.format_close_message(trade_date, quotes)
                    payload = {
                        "source": "us_index_tracker",
                        "title": f"US index close {trade_day}",
                        "text": message,
                        "event_id": f"us_index_close_{trade_day}",
                    }
                    if _post_direct_push(config.relay_direct_push_url, payload):
                        close_sent_dates.add(trade_day)
                        logger.info("[US_INDEX_CLOSE_PUSHED] trade_date=%s", trade_day)
        except Exception as exc:
            logger.warning("US index tracking failed: %s", exc)

        stop_event.wait(max(config.us_index_poll_interval_seconds, 5))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge all news sources to LINE relay")
    parser.add_argument("--relay-url", default="http://127.0.0.1:18090/events", help="LINE relay /events endpoint")
    parser.add_argument(
        "--relay-direct-push-url",
        default="http://127.0.0.1:18090/push/direct",
        help="LINE relay direct push endpoint",
    )
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--poll-interval-seconds", type=int, default=300, help="Polling interval for RSS/GDELT only")
    parser.add_argument("--limit", type=int, default=5, help="Per-source fetch limit for RSS/GDELT")
    parser.add_argument("--tickers", default="", help="Benzinga stream tickers filter, comma-separated")
    parser.add_argument("--channels", default="", help="Benzinga stream channels filter, comma-separated")
    parser.add_argument("--languages", default="", help="Benzinga stream language filter, comma-separated")
    parser.add_argument("--x-stream-timeout-seconds", type=int, default=90, help="X stream read timeout seconds")
    parser.add_argument(
        "--x-stream-reconnect-max-seconds",
        type=int,
        default=120,
        help="Max reconnect backoff for X stream",
    )
    parser.add_argument("--us-index-poll-interval-seconds", type=int, default=30, help="US index polling cadence")
    parser.add_argument("--disable-us-index", action="store_true", help="Disable US index direct push chain")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
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

    config = BridgeConfig(
        relay_url=args.relay_url,
        relay_direct_push_url=args.relay_direct_push_url,
        env_file=args.env_file,
        poll_interval_seconds=max(args.poll_interval_seconds, 1),
        limit_per_source=max(args.limit, 1),
        log_level=args.log_level,
        benzinga_tickers=[x.strip() for x in args.tickers.split(",") if x.strip()],
        benzinga_channels=[x.strip() for x in args.channels.split(",") if x.strip()],
        benzinga_languages=[_normalize_benzinga_language(x) for x in args.languages.split(",") if x.strip()],
        x_stream_timeout_seconds=max(args.x_stream_timeout_seconds, 15),
        x_stream_reconnect_max_seconds=max(args.x_stream_reconnect_max_seconds, 5),
        us_index_enabled=not args.disable_us_index,
        us_index_poll_interval_seconds=max(args.us_index_poll_interval_seconds, 5),
    )

    stop_event = threading.Event()

    poll_thread = threading.Thread(target=_poll_loop, args=(config, stop_event), daemon=True, name="bridge-poll")
    benzinga_thread = threading.Thread(target=_stream_loop, args=(config, stop_event), daemon=True, name="bridge-benzinga")
    x_stream_thread = threading.Thread(target=_x_stream_loop, args=(config, stop_event), daemon=True, name="bridge-x-stream")
    us_index_thread = threading.Thread(
        target=_us_index_direct_loop,
        args=(config, stop_event),
        daemon=True,
        name="bridge-us-index",
    )

    poll_thread.start()
    benzinga_thread.start()
    x_stream_thread.start()
    us_index_thread.start()
    logger.info("Bridge started relay_url=%s direct_push_url=%s", config.relay_url, config.relay_direct_push_url)

    try:
        poll_thread.join()
        benzinga_thread.join()
        x_stream_thread.join()
        us_index_thread.join()
        return 0
    except KeyboardInterrupt:
        logger.info("Bridge interrupted by user")
        stop_event.set()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
