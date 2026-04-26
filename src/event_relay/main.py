from __future__ import annotations

# Event relay service: load settings, initialize storage, and expose /events.
import argparse
import logging
import sys

from event_relay.config import load_settings
from event_relay.http_server import RelayHttpServer
from event_relay.service import RelayProcessor


def build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(description="Event relay service for incoming data events")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return parser


def main() -> int:
    """程式入口，負責執行此模組的主要流程。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = build_parser().parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )

    try:
        settings = load_settings(args.env_file)
        processor = RelayProcessor(settings)
        server = RelayHttpServer((settings.host, settings.port), processor, env_file=args.env_file)
        logging.info("Event relay listening on http://%s:%d", settings.host, settings.port)
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        logging.info("Event relay interrupted by user")
        return 0
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
