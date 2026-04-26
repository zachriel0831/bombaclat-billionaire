"""Query historical t_market_analyses by structured_json fields.

Examples:
    python scripts/query_analyses.py --sentiment bearish --since 2026-04-01
    python scripts/query_analyses.py --confidence high --sector 半導體
    python scripts/query_analyses.py --ticker 2330 --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from event_relay.config import load_settings  # noqa: E402
from event_relay.service import MySqlEventStore  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(description="Query t_market_analyses by structured fields.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--sentiment", choices=["bullish", "bearish", "neutral"])
    parser.add_argument("--confidence", choices=["low", "medium", "high"])
    parser.add_argument("--sector", help="Match against tw_sector_watch[].sector (substring).")
    parser.add_argument("--ticker", help="Match against stock_watch[].ticker (exact).")
    parser.add_argument("--slot", help="Filter by analysis_slot (e.g. pre_tw_open).")
    parser.add_argument("--since", help="Filter analysis_date >= YYYY-MM-DD.")
    parser.add_argument("--limit", type=int, default=20)
    return parser


def _matches(structured: dict, args: argparse.Namespace) -> bool:
    """執行 matches 的主要流程。"""
    if args.sentiment and structured.get("sentiment") != args.sentiment:
        return False
    if args.confidence and structured.get("confidence") != args.confidence:
        return False
    if args.sector:
        sectors = structured.get("tw_sector_watch") or []
        if not any(args.sector in (item.get("sector") or "") for item in sectors):
            return False
    if args.ticker:
        stocks = structured.get("stock_watch") or []
        if not any((item.get("ticker") or "") == args.ticker for item in stocks):
            return False
    return True


def main() -> int:
    """程式入口，負責執行此模組的主要流程。"""
    args = _build_parser().parse_args()
    settings = load_settings(args.env_file)
    if not settings.mysql_enabled:
        print("MySQL disabled; cannot query.", file=sys.stderr)
        return 1

    store = MySqlEventStore(settings)
    store.initialize()
    if store._conn is None:
        print("MySQL connection failed.", file=sys.stderr)
        return 1

    where = ["structured_json IS NOT NULL"]
    params: list = []
    if args.slot:
        where.append("analysis_slot = %s")
        params.append(args.slot)
    if args.since:
        where.append("analysis_date >= %s")
        params.append(args.since)
    sql = (
        f"SELECT analysis_date, analysis_slot, model, summary_text, structured_json "
        f"FROM {settings.mysql_analysis_table} "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY analysis_date DESC, analysis_slot DESC "
        "LIMIT %s"
    )
    params.append(max(int(args.limit) * 4, args.limit))

    cur = store._conn.cursor()
    try:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    finally:
        cur.close()

    matched = 0
    for row in rows:
        analysis_date, analysis_slot, model, summary_text, structured_text = row
        try:
            structured = json.loads(structured_text) if structured_text else {}
        except json.JSONDecodeError:
            continue
        if not _matches(structured, args):
            continue

        print(f"=== {analysis_date} {analysis_slot} ({model}) ===")
        print(
            f"sentiment={structured.get('sentiment')} "
            f"confidence={structured.get('confidence')} "
            f"headline={structured.get('headline')}"
        )
        sectors = structured.get("tw_sector_watch") or []
        if sectors:
            print("  sectors:")
            for item in sectors[:5]:
                print(f"    - {item.get('sector')} ({item.get('direction')}): {item.get('rationale')}")
        stocks = structured.get("stock_watch") or []
        if stocks:
            print("  stocks:")
            for item in stocks[:5]:
                print(f"    - {item.get('ticker')} ({item.get('direction')}): {item.get('rationale')}")
        risks = structured.get("risks") or []
        if risks:
            print(f"  risks: {', '.join(risks[:3])}")
        print(f"  summary: {(summary_text or '')[:120]}...")
        print()
        matched += 1
        if matched >= args.limit:
            break

    print(f"Matched {matched} record(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
