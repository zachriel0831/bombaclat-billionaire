from __future__ import annotations

# relay 服務主程式：載入設定、初始化處理器並啟動 HTTP 伺服器。
import argparse
import logging
import sys

from line_event_relay.config import load_settings
from line_event_relay.http_server import RelayHttpServer
from line_event_relay.service import RelayProcessor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LINE relay service for incoming news events")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return parser


def main() -> int:
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
        server = RelayHttpServer((settings.host, settings.port), processor)
        logging.info("LINE relay listening on http://%s:%d", settings.host, settings.port)
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        logging.info("LINE relay interrupted by user")
        return 0
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
