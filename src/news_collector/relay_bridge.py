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
from news_collector.config import load_settings, resolve_benzinga_api_key

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
    env_file: str
    poll_interval_seconds: int
    limit_per_source: int
    log_level: str
    benzinga_tickers: list[str]
    benzinga_channels: list[str]
    benzinga_languages: list[str]


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


def _poll_loop(config: BridgeConfig, stop_event: threading.Event) -> None:
    source_names = ["rss", "gdelt", "x"]

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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge all news sources to LINE relay /events")
    parser.add_argument("--relay-url", default="http://127.0.0.1:18090/events", help="LINE relay /events endpoint")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--poll-interval-seconds", type=int, default=300, help="Polling interval for RSS/GDELT")
    parser.add_argument("--limit", type=int, default=5, help="Per-source fetch limit for RSS/GDELT")
    parser.add_argument("--tickers", default="", help="Benzinga stream tickers filter, comma-separated")
    parser.add_argument("--channels", default="", help="Benzinga stream channels filter, comma-separated")
    parser.add_argument("--languages", default="", help="Benzinga stream language filter, comma-separated")
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
        env_file=args.env_file,
        poll_interval_seconds=max(args.poll_interval_seconds, 1),
        limit_per_source=max(args.limit, 1),
        log_level=args.log_level,
        benzinga_tickers=[x.strip() for x in args.tickers.split(",") if x.strip()],
        benzinga_channels=[x.strip() for x in args.channels.split(",") if x.strip()],
        benzinga_languages=[_normalize_benzinga_language(x) for x in args.languages.split(",") if x.strip()],
    )

    stop_event = threading.Event()

    poll_thread = threading.Thread(target=_poll_loop, args=(config, stop_event), daemon=True, name="bridge-poll")
    stream_thread = threading.Thread(target=_stream_loop, args=(config, stop_event), daemon=True, name="bridge-stream")

    poll_thread.start()
    stream_thread.start()
    logger.info("Bridge started relay_url=%s", config.relay_url)

    try:
        poll_thread.join()
        stream_thread.join()
        return 0
    except KeyboardInterrupt:
        logger.info("Bridge interrupted by user")
        stop_event.set()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
