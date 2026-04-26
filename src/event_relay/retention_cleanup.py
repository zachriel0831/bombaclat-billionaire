from __future__ import annotations

import argparse
import logging
import sys

from event_relay.config import load_settings
from event_relay.service import MySqlEventStore


logger = logging.getLogger(__name__)


def run_once(env_file: str = ".env", keep_days: int | None = None, dry_run: bool = False) -> dict[str, int]:
    """執行單次任務流程並回傳結果。"""
    settings = load_settings(env_file)
    if not settings.mysql_enabled:
        raise RuntimeError("Retention cleanup requires RELAY_MYSQL_ENABLED=true")

    effective_keep_days = keep_days if keep_days is not None else settings.retention_keep_days
    effective_keep_days = max(1, min(365, int(effective_keep_days)))

    store = MySqlEventStore(settings)
    store.initialize()
    if dry_run:
        logger.info("Retention cleanup dry-run only: keep_days=%d", effective_keep_days)
        return {"events": 0, "x_posts": 0}

    result = store.delete_retention_older_than_days(effective_keep_days)
    logger.info(
        "Retention cleanup complete: keep_days=%d events_deleted=%d x_posts_deleted=%d",
        effective_keep_days,
        int(result.get("events", 0)),
        int(result.get("x_posts", 0)),
    )
    return result


def _build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(description="Delete old relay event and X post rows from MySQL")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--keep-days", type=int, default=None, help="Override retention days")
    parser.add_argument("--dry-run", action="store_true", help="Validate config without deleting rows")
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

    try:
        run_once(env_file=args.env_file, keep_days=args.keep_days, dry_run=args.dry_run)
        return 0
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
