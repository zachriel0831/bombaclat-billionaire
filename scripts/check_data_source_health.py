"""CLI wrapper for the read-only data source health report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_source_health import build_report, render_text  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check news data-source freshness and local collector health.")
    parser.add_argument("--env-file", default=".env", help="Path to env file, relative to repo root by default.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--skip-processes",
        action="store_true",
        help="Skip local Windows process-count probes.",
    )
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="Exit non-zero when the overall status is warn or worse.",
    )
    parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Exit non-zero when the overall status is stale/missing/error.",
    )
    args = parser.parse_args(argv)

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = PROJECT_ROOT / env_file

    report = build_report(str(env_file), include_processes=not args.skip_processes)
    print(report.to_json() if args.json else render_text(report))

    status = report.overall_status
    if args.fail_on_warn and status in {"warn", "stale", "missing", "error"}:
        return 1
    if args.fail_on_stale and status in {"stale", "missing", "error"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

