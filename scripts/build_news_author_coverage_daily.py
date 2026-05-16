"""Build daily source/category author coverage aggregates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news_platform.config import load_settings
from news_platform.store import NewsPlatformStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    settings = load_settings(args.env_file)
    store = NewsPlatformStore(settings)
    store.initialize()
    try:
        affected = store.refresh_author_coverage_daily(lookback_days=args.days)
        print(f"coverage_rows_affected={affected}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
