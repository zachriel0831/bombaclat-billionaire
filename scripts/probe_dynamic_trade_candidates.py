# -*- coding: utf-8 -*-
"""Create one probe batch of five dynamic Taiwan trade candidates.

This is a guarded one-off utility for validating the new dynamic-candidate
contract before the normal market-analysis pipeline is migrated away from the
historical fixed pool.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json

from event_relay.config import load_settings
from event_relay.service import MarketAnalysisRecord, MySqlEventStore, TradeSignalRecord


TZ = timezone(timedelta(hours=8))
SLOT = "dynamic_trade_candidates_probe"
MODEL = "codex-local-dynamic-candidate-probe"
PROMPT_VERSION = "dyn-probe-v1"

ORDER = ["2330", "2317", "2454", "2308", "2881"]
NAMES = {
    "2330": "台積電",
    "2317": "鴻海",
    "2454": "聯發科",
    "2308": "台達電",
    "2881": "富邦金",
}
EVENTS = {
    "2330": [218261, 218198, 218082, 215880, 215307, 215306],
    "2317": [218261, 218198, 217887, 215879],
    "2454": [217838, 218034, 218065, 215872, 215882],
    "2308": [217839, 218011, 218082, 215878, 215868],
    "2881": [218035, 218084, 215884, 215874, 215867],
}
CONFIDENCE = {
    "2330": "medium",
    "2317": "medium",
    "2454": "low",
    "2308": "low",
    "2881": "medium",
}
LEVELS = {
    "2330": ((Decimal("2365"), Decimal("2395")), Decimal("2340"), (Decimal("2445"), Decimal("2500"))),
    "2317": ((Decimal("298.5"), Decimal("302.0")), Decimal("292.0"), (Decimal("309.0"), Decimal("315.0"))),
    "2454": ((Decimal("4460"), Decimal("4550")), Decimal("4360"), (Decimal("4720"), Decimal("4900"))),
    "2308": ((Decimal("2350"), Decimal("2390")), Decimal("2315"), (Decimal("2460"), Decimal("2520"))),
    "2881": ((Decimal("112.0"), Decimal("114.5")), Decimal("109.0"), (Decimal("118.0"), Decimal("121.5"))),
}
RATIONALE = {
    "2330": "AI/COMPUTEX 與台灣作為 AI 核心基地的新聞動能仍強，今日即時成交價維持在前日價上方；適合做權值股多方拉回監聽。",
    "2317": "AI 伺服器與 COMPUTEX 題材延續，今日盤中高低差足夠，收盤仍高於前日追蹤價；適合用拉回區間觀察短線續航。",
    "2454": "聯發科受 AI PC / 邊緣 AI 題材牽動，但今日震幅過大且收盤低於盤初高點很多，只能列為低追價、等回測的短線候選。",
    "2308": "台達電對 AI 電源/資料中心需求敏感，但今日由高檔回落，候選條件應偏向支撐回測後再進場，不做現價追高。",
    "2881": "金融股提供非 AI 題材分散，前日追蹤價與今日收盤皆偏強，且融資餘額增加；適合作為五檔監聽中的防守/輪動候選。",
}
RISKS = {
    "2330": ["權值股若受大盤千點震盪拖累，可能先回測支撐。", "只適合拉回觸發，不適合追高。"],
    "2317": ["AI 題材擁擠，盤中若跌破前低代表續航不足。", "融資餘額前日下降，籌碼不算全面同向。"],
    "2454": ["今日高低差過大，若隔日開高追價容易被反轉洗出。", "收盤距盤中高點很遠，需等待量價重新站穩。"],
    "2308": ["由高檔回落代表上檔賣壓重，需等支撐確認。", "若跌破今日低點附近，候選失效。"],
    "2881": ["金融股與 AI 主線相關度較低，若資金集中科技股可能落後。", "大盤急跌時仍可能被動回落。"],
}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _set_utf8_connection(store: MySqlEventStore) -> None:
    conn = store._conn
    if conn is not None and hasattr(conn, "set_charset_collation"):
        conn.set_charset_collation(charset="utf8mb4", collation="utf8mb4_unicode_ci")


def _fetch_today_quotes(store: MySqlEventStore, quote_table: str) -> dict[str, tuple]:
    cur = store._cursor()
    try:
        cur.execute(
            f"""
            SELECT symbol,
                   MIN(ts) first_ts,
                   MAX(ts) last_ts,
                   CAST(SUBSTRING_INDEX(GROUP_CONCAT(close_price ORDER BY ts ASC), ',', 1) AS DECIMAL(18,4)) openish,
                   MAX(close_price) highish,
                   MIN(close_price) lowish,
                   CAST(SUBSTRING_INDEX(GROUP_CONCAT(close_price ORDER BY ts DESC), ',', 1) AS DECIMAL(18,4)) closeish,
                   COUNT(*) ticks
            FROM `{quote_table}`
            WHERE DATE(ts)=CURDATE()
            GROUP BY symbol
            """
        )
        return {str(row[0]): row for row in cur.fetchall()}
    finally:
        cur.close()


def _build_stock_watch(quotes: dict[str, tuple]) -> list[dict[str, object]]:
    missing = [ticker for ticker in ORDER if ticker not in quotes]
    if missing:
        raise RuntimeError(f"missing today quote rows: {missing}")

    stock_watch: list[dict[str, object]] = []
    for rank, ticker in enumerate(ORDER, 1):
        row = quotes[ticker]
        (entry_low, entry_high), stop, (target_first, target_second) = LEVELS[ticker]
        stock_watch.append(
            {
                "rank": rank,
                "ticker": ticker,
                "name": NAMES[ticker],
                "market": "TW",
                "signal_type": "codex_dynamic_candidate_probe",
                "strategy_type": "intraday_short_swing",
                "direction": "long",
                "confidence": CONFIDENCE[ticker],
                "quote_evidence": {
                    "first_ts": str(row[1]),
                    "last_ts": str(row[2]),
                    "openish": str(row[3]),
                    "highish": str(row[4]),
                    "lowish": str(row[5]),
                    "closeish": str(row[6]),
                    "ticks": int(row[7]),
                },
                "entry_zone": {
                    "low": float(entry_low),
                    "high": float(entry_high),
                    "basis": "多方拉回觸發區；stock-monitor long entry 使用 high，價格跌到或低於該值才記 entry_hit",
                },
                "invalidation": {
                    "price": float(stop),
                    "basis": "跌破今日支撐/前低附近則候選失效",
                },
                "take_profit_zone": {
                    "first": float(target_first),
                    "second": float(target_second),
                    "basis": "第一段以前高/反彈壓力為主，第二段作短線延伸觀察",
                },
                "holding_horizon": "intraday_or_1_to_3_sessions",
                "rationale": RATIONALE[ticker],
                "risk_notes": RISKS[ticker],
                "source_event_ids": EVENTS[ticker],
            }
        )
    return stock_watch


def _summary_text(today: str, stock_watch: list[dict[str, object]]) -> str:
    lines = [
        f"{today} 五檔動態候選試產",
        "用途：提供 stock-monitor 五檔監聽測試；全部為 pending_review，不是下單建議。",
        "限制：今日即時 quote universe 只有 2308/2317/2330/2454/2881 五檔，因此本次仍是受限試產，不代表全市場動態選股已完成。",
        "候選：",
    ]
    for item in stock_watch:
        quote = item["quote_evidence"]
        entry = item["entry_zone"]
        stop = item["invalidation"]
        target = item["take_profit_zone"]
        lines.append(
            f"{item['rank']}. {item['ticker']} {item['name']} {item['confidence']}："
            f"收 {quote['closeish']}，entry {entry['low']}-{entry['high']}，"
            f"stop {stop['price']}，target {target['first']}/{target['second']}。"
            f"{item['rationale']}"
        )
    return "\n".join(lines)


def main() -> int:
    today = datetime.now(TZ).date().isoformat()
    settings = load_settings(".env")
    store = MySqlEventStore(settings)
    store.initialize()
    _set_utf8_connection(store)

    quotes = _fetch_today_quotes(store, settings.mysql_quote_snapshot_table)
    stock_watch = _build_stock_watch(quotes)
    source_event_ids = sorted({event_id for ids in EVENTS.values() for event_id in ids})
    raw = {
        "kind": "dynamic_trade_candidates_probe",
        "generated_by": "codex",
        "external_provider_api_called": False,
        "analysis_date": today,
        "analysis_slot": SLOT,
        "quote_universe_limited": True,
        "quote_symbols_available": sorted(quotes),
        "not_financial_advice": True,
        "monitor_cap": 5,
        "future_trade_cap": 3,
        "source_event_ids_union": source_event_ids,
    }
    structured = {
        "sector_watch": [
            {
                "sector": "AI/HPC/COMPUTEX",
                "direction": "bullish_but_crowded",
                "evidence": [218287, 218261, 218198, 218082, 217887],
            },
            {
                "sector": "financials",
                "direction": "rotation_watch",
                "evidence": [218035, 218084, 215867],
            },
        ],
        "stock_watch": stock_watch,
        "risks": [
            "今日台股與櫃買震盪很大，所有候選都應等待 entry_hit，不做追價。",
            "本次 quote universe 只有五檔，尚未完成全市場候選生成。",
            "order-dispatcher 尚無交易狀態機與 PnL，不能視為自動交易輸入。",
        ],
        "data_gaps": [
            "缺少全市場即時 quote universe。",
            "缺少候選排序欄位的正式 schema；本次 rank 存在 raw/structured JSON。",
        ],
    }
    analysis_id = store.upsert_market_analysis(
        MarketAnalysisRecord(
            analysis_date=today,
            analysis_slot=SLOT,
            scheduled_time_local=datetime.now(TZ).strftime("%H:%M"),
            model=MODEL,
            prompt_version=PROMPT_VERSION,
            summary_text=_summary_text(today, stock_watch),
            events_used=len(source_event_ids),
            market_rows_used=len(quotes),
            push_enabled=False,
            pushed=False,
            raw_json=_json(raw),
            structured_json=_json(structured),
        )
    )

    signals: list[TradeSignalRecord] = []
    for item in stock_watch:
        ticker = str(item["ticker"])
        base = f"{today}:{SLOT}:{ticker}:codex_dynamic_candidate_probe"
        signal_key = "dynprobe-" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:32]
        idempotency_key = hashlib.sha1(("idempotency:" + base).encode("utf-8")).hexdigest()
        signals.append(
            TradeSignalRecord(
                signal_key=signal_key,
                idempotency_key=idempotency_key,
                analysis_id=analysis_id,
                analysis_date=today,
                analysis_slot=SLOT,
                market="TW",
                ticker=ticker,
                name=str(item["name"]),
                signal_type="codex_dynamic_candidate_probe",
                strategy_type="intraday_short_swing",
                direction="long",
                confidence=str(item["confidence"]),
                entry_zone_json=_json(item["entry_zone"]),
                invalidation_json=_json(item["invalidation"]),
                take_profit_zone_json=_json(item["take_profit_zone"]),
                holding_horizon=str(item["holding_horizon"]),
                rationale=str(item["rationale"]),
                risk_notes_json=_json(item["risk_notes"]),
                source_event_ids_json=_json(item["source_event_ids"]),
                status="pending_review",
                raw_json=_json(
                    {
                        "rank": item["rank"],
                        "quote_evidence": item["quote_evidence"],
                        "source": "codex_dynamic_candidate_probe",
                        "quote_universe_limited": True,
                        "not_financial_advice": True,
                    }
                ),
            )
        )
    stored = store.replace_trade_signals_for_analysis(analysis_id, signals)

    cur = store._cursor()
    try:
        cur.execute(
            f"""
            SELECT id, ticker, name, signal_type, strategy_type, direction, confidence,
                   JSON_UNQUOTE(JSON_EXTRACT(entry_zone,'$.low')),
                   JSON_UNQUOTE(JSON_EXTRACT(entry_zone,'$.high')),
                   JSON_UNQUOTE(JSON_EXTRACT(invalidation,'$.price')),
                   JSON_UNQUOTE(JSON_EXTRACT(take_profit_zone,'$.first')),
                   JSON_UNQUOTE(JSON_EXTRACT(take_profit_zone,'$.second')),
                   status, LEFT(rationale, 120), source_event_ids
            FROM `{settings.mysql_trade_signal_table}`
            WHERE analysis_id=%s
            ORDER BY id ASC
            """,
            (analysis_id,),
        )
        rows = cur.fetchall()
    finally:
        cur.close()

    print(_json({"analysis_id": analysis_id, "signals_stored": stored, "slot": SLOT, "date": today}))
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
