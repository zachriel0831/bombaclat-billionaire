"""CLI wrapper for news-platform official-list coverage audits."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from news_platform.config import load_settings  # noqa: E402
from news_platform.main import parse_categories  # noqa: E402
from news_platform.source_accuracy_audit import render_text, run_accuracy_audit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare current official news source lists with locally stored articles."
    )
    parser.add_argument("--env-file", default=".env", help="Path to env file, relative to repo root by default.")
    parser.add_argument("--categories", default=None, help="Comma-separated categories; default from env.")
    parser.add_argument(
        "--source-ids",
        default=None,
        help="Comma-separated source ids. Default audits active sources plus TVBS/UDN/SETN; use all for every registered source.",
    )
    parser.add_argument("--skip-source-ids", default="ctee", help="Comma-separated source ids skipped from audit.")
    parser.add_argument("--limit", type=int, default=20, help="Official-list items checked per source/category.")
    parser.add_argument("--min-coverage", type=float, default=0.85, help="Minimum matched official-list ratio.")
    parser.add_argument("--min-items", type=int, default=3, help="Warn when an official list exposes fewer items.")
    parser.add_argument("--compensate", action="store_true", help="Run one bounded crawl for sources below coverage.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of text.")
    parser.add_argument("--json-out", default="", help="Optional path for the JSON report.")
    parser.add_argument("--text-out", default="", help="Optional path for the text report.")
    parser.add_argument("--fail-on-warn", action="store_true", help="Exit non-zero for warn/missing/error.")
    args = parser.parse_args(argv)

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = PROJECT_ROOT / env_file

    categories = parse_categories(args.categories)
    source_ids = _parse_csv(args.source_ids)
    skip_source_ids = _parse_csv(args.skip_source_ids)
    settings = load_settings(str(env_file))
    report = run_accuracy_audit(
        settings,
        categories=categories,
        source_ids=source_ids,
        skip_source_ids=skip_source_ids,
        limit_per_source=max(1, args.limit),
        min_coverage=max(0.0, min(1.0, args.min_coverage)),
        min_items=max(1, args.min_items),
        compensate=args.compensate,
    )
    text = render_text(report)
    json_report = report.to_json()

    if args.json_out:
        _write_report(Path(args.json_out), json_report)
    if args.text_out:
        _write_report(Path(args.text_out), text)
    print(json_report if args.json else text)

    if args.fail_on_warn and report.overall_status in {"warn", "missing", "error"}:
        return 1
    return 0


def _parse_csv(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return tuple(dict.fromkeys(item.strip().lower() for item in value.split(",") if item.strip()))


def _write_report(path: Path, content: str) -> None:
    target = path if path.is_absolute() else PROJECT_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
