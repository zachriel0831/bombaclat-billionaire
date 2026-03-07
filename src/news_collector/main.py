from __future__ import annotations

import argparse
import html
import json
import logging
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from news_collector.benzinga_stream import BenzingaNewsStreamer, StreamConfig
from news_collector.collector import build_sources, fetch_news
from news_collector.config import load_settings, resolve_benzinga_api_key
from news_collector.models import NewsItem


def _url_status_200(url: str, timeout_seconds: int = 3) -> bool:
    # 連結有效性檢查：限定 3 秒 timeout，僅接受 HTTP 200。
    req = Request(url, method="GET")
    req.add_header("User-Agent", "news-collector/0.1 (+https://local.dev)")
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            return int(getattr(resp, "status", 0)) == 200
    except HTTPError:
        return False
    except URLError:
        return False
    except Exception:
        return False


def _normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    alias_map = {
        "en": "english",
        "english": "english",
        "zh": "chinese",
        "zh-cn": "chinese",
        "zh-tw": "chinese",
        "chinese": "chinese",
    }
    return alias_map.get(normalized, normalized)


def _item_language(item: NewsItem) -> str | None:
    raw = item.raw if isinstance(item.raw, dict) else {}
    raw_lang = raw.get("language")
    if isinstance(raw_lang, str):
        normalized = _normalize_language(raw_lang)
        if normalized:
            return normalized

    for tag in item.tags:
        normalized = _normalize_language(tag)
        if normalized:
            return normalized
    return None


def _normalize_summary(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text


class _RecentEventDeduper:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = max(ttl_seconds, 1)
        self._expires: dict[str, float] = {}

    def seen_recently(self, title: str, url: str) -> bool:
        now = time.monotonic()
        self._evict_expired(now)

        key = self._build_key(title, url)
        if key in self._expires:
            return True

        self._expires[key] = now + float(self.ttl_seconds)
        return False

    def _evict_expired(self, now: float) -> None:
        expired_keys = [key for key, expires_at in self._expires.items() if expires_at <= now]
        for key in expired_keys:
            self._expires.pop(key, None)

    @staticmethod
    def _build_key(title: str, url: str) -> str:
        normalized_title = " ".join(title.split()).strip().lower()
        normalized_url = url.strip().lower()
        return f"{normalized_title}::{normalized_url}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect breaking international finance news.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch normalized news items")
    fetch_parser.add_argument(
        "--source",
        default="all",
        choices=["all", "rss", "gdelt", "benzinga", "x"],
        help="Source selector",
    )
    fetch_parser.add_argument("--limit", type=int, default=20, help="Max records per source")
    fetch_parser.add_argument("--env-file", default=".env", help="Path to .env file")
    fetch_parser.add_argument(
        "--languages",
        default="",
        help="Comma-separated languages filter, e.g. english,chinese or en,zh",
    )
    fetch_parser.add_argument("--title-url-only", action="store_true", help="Output only title and url")
    fetch_parser.add_argument("--pretty", action="store_true", help="Pretty JSON output")
    fetch_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )

    stream_parser = subparsers.add_parser("stream", help="Run Benzinga websocket stream")
    stream_parser.add_argument("--env-file", default=".env", help="Path to .env file")
    stream_parser.add_argument("--tickers", default="", help="Comma-separated tickers filter, e.g. AAPL,TSLA")
    stream_parser.add_argument("--channels", default="", help="Comma-separated channels filter")
    stream_parser.add_argument("--languages", default="", help="Comma-separated language codes, e.g. en,ja,ko")
    stream_parser.add_argument("--url-only", action="store_true", help="Output only top-level url per event")
    stream_parser.add_argument("--max-messages", type=int, default=20, help="Stop after N messages")
    stream_parser.add_argument("--duration-seconds", type=int, default=0, help="Stop after N seconds (0 = disabled)")
    stream_parser.add_argument("--reconnect-max-seconds", type=int, default=60, help="Max reconnect backoff seconds")
    stream_parser.add_argument("--timeout-seconds", type=int, default=30, help="WebSocket read timeout seconds")
    stream_parser.add_argument("--output-file", default="", help="Optional jsonl output file path")
    stream_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )

    return parser


def main() -> int:
    # 強制使用 UTF-8，避免 Windows 主控台輸出中文或多語內容時亂碼。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "fetch":
        try:
            # 日誌只輸出運行資訊，不包含任何敏感憑證。
            logging.basicConfig(
                level=getattr(logging, args.log_level),
                format="%(asctime)s %(levelname)s %(name)s - %(message)s",
                stream=sys.stdout,
            )
            settings = load_settings(args.env_file)
            sources = build_sources(settings, args.source)
            items = fetch_news(sources, args.limit)
            if args.languages:
                allowed = {
                    normalized
                    for normalized in (_normalize_language(x) for x in args.languages.split(","))
                    if normalized
                }
                items = [item for item in items if _item_language(item) in allowed]

            if args.title_url_only:
                simplified = [{"title": i.title, "url": i.url} for i in items if i.url]
                if args.pretty:
                    print(json.dumps(simplified, ensure_ascii=False, indent=2))
                else:
                    for row in simplified:
                        print(json.dumps(row, ensure_ascii=False))
            else:
                if args.pretty:
                    text = json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2)
                    print(text)
                else:
                    # 逐行 JSON，方便串接管線與日誌系統收集。
                    for item in items:
                        print(json.dumps(item.to_dict(), ensure_ascii=False))
            return 0
        except ValueError as exc:
            print(f"Config error: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:  # pragma: no cover - runtime guard
            print(f"Runtime error: {exc}", file=sys.stderr)
            return 1

    if args.command == "stream":
        try:
            logging.basicConfig(
                level=getattr(logging, args.log_level),
                format="%(asctime)s %(levelname)s %(name)s - %(message)s",
                stream=sys.stdout,
            )

            settings = load_settings(args.env_file)
            if not settings.benzinga_enabled:
                print(
                    "Config error: Benzinga stream is disabled. Set BENZINGA_ENABLED=true to enable.",
                    file=sys.stderr,
                )
                return 2
            api_key = resolve_benzinga_api_key(settings)
            if not api_key:
                print(
                    (
                        "Config error: missing benzinga key. "
                        "Set BENZINGA_API_KEY or store encrypted key in BENZINGA_API_KEY_FILE."
                    ),
                    file=sys.stderr,
                )
                return 2

            tickers = [x.strip() for x in args.tickers.split(",") if x.strip()]
            channels = [x.strip() for x in args.channels.split(",") if x.strip()]
            languages = [x.strip().lower() for x in args.languages.split(",") if x.strip()]
            output_path = Path(args.output_file).resolve() if args.output_file else None
            output_fp = None

            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_fp = output_path.open("a", encoding="utf-8")
            # 以 title+url 去重，避免同一新聞不同 id 在短時間重複打印。
            deduper = _RecentEventDeduper(ttl_seconds=300)

            def on_event(event: dict) -> None:
                event_id = str(event.get("id") or "-").strip() or "-"
                source = str(event.get("source") or "-").strip() or "-"
                title = " ".join(str(event.get("title") or "").split())
                url = str(event.get("url") or "").strip()
                summary = _normalize_summary(str(event.get("summary") or ""))
                if not url:
                    return
                if deduper.seen_recently(title=title, url=url):
                    logging.debug("Drop duplicate event within 5m id=%s url=%s", event_id, url)
                    return
                if not _url_status_200(url, timeout_seconds=3):
                    logging.debug("Drop event: non-200 url id=%s url=%s", event_id, url)
                    return

                # 流式模式固定輸出精簡事件，避免列印完整事件體造成雜訊。
                line = (
                    f"[STREAM_URL_EVENT] id={event_id} source={source} "
                    f"title={title} url={url} summary={summary or '-'}"
                )
                print(line)
                if output_fp is not None:
                    output_fp.write(line + "\n")
                    output_fp.flush()

            streamer = BenzingaNewsStreamer(
                StreamConfig(
                    api_key=api_key,
                    tickers=tickers,
                    channels=channels,
                    languages=languages,
                    timeout_seconds=args.timeout_seconds,
                    reconnect_max_seconds=args.reconnect_max_seconds,
                    stop_on_429=settings.benzinga_stop_on_429,
                )
            )
            streamer.run(
                on_event=on_event,
                max_messages=args.max_messages if args.max_messages > 0 else None,
                duration_seconds=args.duration_seconds if args.duration_seconds > 0 else None,
            )

            if output_fp is not None:
                output_fp.close()
            return 0
        except ValueError as exc:
            print(f"Config error: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:
            print(f"Runtime error: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
