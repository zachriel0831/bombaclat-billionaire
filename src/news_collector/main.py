from __future__ import annotations

import argparse
import json
import logging
import sys

from news_collector.collector import build_sources, fetch_news
from news_collector.config import load_settings


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

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect breaking international finance news.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch normalized news items")
    fetch_parser.add_argument(
        "--source",
        default="all",
        choices=["all", "rss", "x"],
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
