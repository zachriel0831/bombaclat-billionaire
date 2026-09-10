"""Local Codex memo; dry-run by default, --write creates the missing row."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _us_close_guard_20260909 import (
    MarketAnalysisRecord, MySqlEventStore, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = "2026-09-11"
EVENT_IDS = [894201, 892638, 892889]
MARKET_IDS = [383, 384, 387, 388]
SUMMARY = """這次美股收盤讓台灣投資人更難只用需求成長解釋股價。道瓊與標普都低於前一交易日收盤，能源供應風險又伴隨利率壓力；我的判斷是，台股電子與設備供應鏈仍有訂單支撐，但市場願意付出的估值可能先收縮。最大的變數，是這輪油價上漲會停留在短期風險溢價，還是延長通膨與高利率的壓力。

中央社報導，油輪遇襲增加，兩大基準原油均突破每桶 100 美元，當日漲幅超過 6%。這是報導當時的行情，不能直接當成期貨結算價。它對台灣的意義在於：航運受阻若持續，進口能源、運輸與製造成本可能一起上升，企業即使接單增加，也未必能把收入成長完整留在毛利。航空與高耗能製造較直接承受成本壓力；石化則要看產品報價能否跟上原料，不能把油價上漲一概視為產業利多。

利率端已出現同方向訊號。經濟日報報導，美國 10 年期公債殖利率盤中衝上 4.92%，並將油價與生產者物價帶來的通膨疑慮列為背景。這支持資金成本壓力升高的解讀，但不足以分辨通膨預期、政策預期與期限溢價各占多少。對先進製程、AI伺服器和電源散熱鏈，較高利率會降低遠期獲利的現值；因此需求沒有轉弱，也可能先看到估值調整。若美元同步走強，台灣還可能面對外資資金流與進口成本的額外壓力，這仍是待確認的傳導條件。

需求一端並非沒有緩衝。經濟日報引述台灣機械公會，8 月機械出口年增 19%，受惠半導體與AI伺服器供應鏈需求。這筆已發生的出口數據，比單純的題材敘事更能支持設備需求韌性；但全年創高仍是展望，不能當成已實現成果。台灣設備與電子供應鏈接下來的關鍵，是出口與訂單能否持續轉成獲利，以及能源、運費與融資成本是否侵蝕成長。

收盤走弱至少顯示風險已進入價格，卻不能据此判定市場已充分反映供應中斷，也不能把全部跌幅歸因於油價。若航運風險緩解、油價回落、殖利率降溫，而台灣設備出口維持成長，這份偏審慎的判斷就需要修正；反過來，若能源壓力持續、利率居高不下，又出現訂單或毛利走弱，市場可能從調整估值轉向下修獲利。對台灣而言，下一步應確認成本、資金與需求是否同時惡化，而不是把美股單晚下跌直接延伸成台股的既定方向。""".replace("据此", "據此")


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DAY and "us_close" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cur = store._cursor()

    def rows(sql, params=()):
        cur.execute(sql, params)
        names = [c[0] for c in cur.description]
        return json.loads(json.dumps([dict(zip(names, r)) for r in cur.fetchall()], default=str))

    assert not rows("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,)), "Review existing row before repair"
    events = rows("SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (894201,892638,892889)")
    market = rows("SELECT id,trade_date,market_session,symbol,recorded_price FROM t_market_index_snapshots WHERE id IN (383,384,387,388)")
    assert len(events) == 3 and len(market) == 4
    assert all("2026-09-10" <= e["published_at"][:10] <= DAY for e in events)
    for symbol in ("DJIA", "S&P 500"):
        prices = {m["trade_date"]: float(m["recorded_price"]) for m in market if m["symbol"] == symbol}
        assert prices["2026-09-10"] < prices["2026-09-09"]
    structured = dict(schema_version="codex-market-analysis-v1", confidence="medium",
        headline="能源與利率壓力抵銷設備需求支撐", thesis="台灣供應鏈需求仍有支撐，但能源與資金成本提高估值壓力。",
        evidence=[dict(event_id=i) for i in EVENT_IDS] + [dict(market_snapshot_ids=MARKET_IDS)],
        tw_sector_transmission=["電子與設備估值承受利率壓力", "航空與高耗能製造面臨能源成本風險"],
        invalidation=["航運風險緩解、油價與殖利率回落，出口續強", "訂單與毛利轉弱使風險擴大至獲利"])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    style = style_check(SUMMARY)
    assert verifier["ok"] and style["ok"], json.dumps(dict(verifier=verifier, style=style))
    push = not calendar.tw.is_trading_day
    raw = dict(automation_id="market-analysis-codex-guard-us-close", generator="codex_automation", display_title=DAY,
        calendar=calendar.to_dict(), evidence_event_ids=EVENT_IDS, market_snapshot_ids=MARKET_IDS,
        claim_verifier=verifier, trust_gate=dict(version="market-analysis-trust-gate-v1", ok=True, reason="claim_verifier_ok"),
        style_checks=style, external_provider_api_called=False)
    print(json.dumps(dict(dry_run=True, claim_verifier=verifier, style_checks=style, push_enabled=push)))
    if "--write" not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot="us_close",
        scheduled_time_local="05:00", model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY, events_used=len(events), market_rows_used=len(market), push_enabled=push, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    row = rows("SELECT * FROM t_market_analyses WHERE id=%s", (row_id,))[0]
    signals = rows("SELECT COUNT(*) AS count FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["count"]
    assert row["summary_text"] == SUMMARY and json.loads(row["structured_json"]) == structured
    assert json.loads(row["raw_json"]) == raw and style_check(row["summary_text"])["ok"]
    assert bool(row["push_enabled"]) == push and not row["pushed"] and signals == 0
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier["ok"], trust_gate=raw["trust_gate"],
        push_enabled=bool(row["push_enabled"]), pushed=bool(row["pushed"]), structured_json_present=True,
        style_checks=style_check(row["summary_text"]), external_provider_api_called=False, trade_signal_count=signals)))


if __name__ == "__main__":
    main()
