"""Collect international homepage headlines and write them to the relay store."""

from __future__ import annotations

import argparse
import logging
import sys

from event_relay.config import load_settings as load_relay_settings
from event_relay.service import MySqlEventStore
from news_collector.collector import build_sources, fetch_news
from news_collector.config import load_settings
from news_collector.relay_bridge import DirectDbEventSink, _allow_event_date, _allow_event_topic, _submit_event


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect low-frequency international homepage headlines.")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--limit", type=int, default=3, help="Max headlines per homepage")
    parser.add_argument(
        "--event-sink",
        default="direct-db",
        choices=["direct-db", "relay"],
        help="Where normalized events are written.",
    )
    parser.add_argument("--relay-url", default="http://127.0.0.1:18090/events")
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

    settings = load_settings(args.env_file)
    sources = build_sources(settings, "homepage")
    items = fetch_news(sources, max(args.limit, 1))

    event_sink = None
    store = None
    if args.event_sink == "direct-db":
        relay_settings = load_relay_settings(args.env_file)
        if not relay_settings.mysql_enabled:
            raise RuntimeError("direct-db event sink requires RELAY_MYSQL_ENABLED=true")
        store = MySqlEventStore(relay_settings)
        store.initialize()
        event_sink = DirectDbEventSink(store)

    counters = {"fetched": len(items), "accepted": 0, "stored": 0, "duplicates": 0, "failed": 0, "dropped_by_date": 0, "dropped_by_topic": 0}
    for item in items:
        event = item.to_dict()
        if not _allow_event_date(event):
            counters["dropped_by_date"] += 1
            continue
        if not _allow_event_topic(event):
            counters["dropped_by_topic"] += 1
            continue
        result = _submit_event(event_sink, args.relay_url, event)
        if result.accepted:
            counters["accepted"] += 1
        if result.stored:
            counters["stored"] += 1
        elif result.status == "duplicate":
            counters["duplicates"] += 1
        elif result.status == "failed":
            counters["failed"] += 1

    logging.info(
        "Homepage headline collection complete fetched=%d accepted=%d stored=%d duplicates=%d failed=%d dropped_by_date=%d dropped_by_topic=%d",
        counters["fetched"],
        counters["accepted"],
        counters["stored"],
        counters["duplicates"],
        counters["failed"],
        counters["dropped_by_date"],
        counters["dropped_by_topic"],
    )
    return 1 if counters["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
