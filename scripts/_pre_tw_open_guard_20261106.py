"""Persist the 2026-11-06 Codex pre-open memo from readable local facts."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _pre_tw_open_guard_20261103 import (
    MarketAnalysisRecord,
    MySqlEventStore,
    allowed_analysis_slots,
    load_settings,
    rows,
    resolve_market_calendar_state,
    style_check,
    verify_claim_coverage,
)


DAY = "2026-11-06"
FACTS = {
    1036975: "change_percent=-6.36%",
    1036976: "change_percent=-12.25%",
    1036977: "change_percent=+69.66%",
    1036981: "change_percent=-10.78%",
}
SUMMARY = """隔夜市場交易的不是一般性回檔，而是科技與半導體風險突然被重新定價。台股盤前因此偏空，電子權值與供應鏈的壓力可能大於其他族群；最大不確定性在於這波賣壓會否在開盤後由海外科技情緒延伸成更廣泛的流動性收縮。

那斯達克百大下跌 6.36%，費城半導體指數下跌 12.25%，台積電 ADR 下跌 10.78%，同時 VIX 上升 69.66% 至 28.18。這組訊號同時指向成長資產評價收縮與避險需求急升，而不只是單一公司的消息反應；對今天而言，海外資金如何處理半導體風險，會直接影響台股開盤後電子權值是否出現連鎖性賣壓。

傳導到台灣，先進製程、封裝、伺服器與電子零組件都會先承接半導體指數的折價壓力；若大型權值開低後無法止穩，賣壓容易從晶片鏈擴散至高本益比科技股。相對地，與科技景氣連動較低的族群未必同步反映相同跌幅，盤面重點將是資金是否只撤出高評價電子，或轉為全面降低風險部位。台積電 ADR在此僅是海外半導體情緒的傳導指標，不能替代台股開盤後的實際資金選擇。

隔夜已反映的是高成長與晶片類股的大幅估值調整，尚待確認的是恐慌是否由期貨與現貨量能延續。若半導體指數與台積電 ADR 能迅速收斂跌幅，且台股電子賣壓未擴散，盤前偏空判讀就需要下修；若 VIX 維持高檔、電子權值持續放量走弱，市場可能繼續重估科技供應鏈的風險溢酬。劇烈波動日的早盤價格容易失真，應先觀察成交結構與類股強弱是否一致。"""


def main() -> None:
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and "pre_tw_open" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    try:
        assert not rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (DAY, "pre_tw_open"))
        events = rows(cursor, "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)", tuple(FACTS))
        assert {event["id"] for event in events} == set(FACTS)
        assert all(FACTS[event["id"]] in event["summary"] for event in events)
        structured = {
            "schema_version": "codex-market-analysis-v1",
            "confidence": "medium",
            "thesis": "海外科技與半導體風險急升，台股電子開盤壓力較大。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["先進製程與封裝", "伺服器與電子權值", "電子零組件與高評價科技股"],
            "invalidation": ["半導體指數與台積電 ADR 收斂跌幅", "台股電子賣壓未擴散"],
        }
        verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
        style = style_check(SUMMARY)
        assert verifier["ok"] and style["ok"], json.dumps({"verifier": verifier, "style": style}, ensure_ascii=False)
        raw = {
            "automation_id": "market-analysis-codex-guard-pre-open", "generator": "codex_automation",
            "display_title": DAY, "calendar": calendar.to_dict(), "evidence_event_ids": list(FACTS),
            "claim_verifier": verifier,
            "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
            "style_checks": style, "external_provider_api_called": False, "generated_at": now.isoformat(),
        }
        if "--write" not in sys.argv:
            print(json.dumps({"dry_run": True, "claim_verifier": verifier, "style_checks": style}, ensure_ascii=False))
            return
        row_id = store.upsert_market_analysis(MarketAnalysisRecord(
            analysis_date=DAY, analysis_slot="pre_tw_open", scheduled_time_local="07:30",
            model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1",
            summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=True, pushed=False,
            raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False),
        ))
        row = rows(cursor, "SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s", (row_id,))[0]
        signals = rows(cursor, "SELECT COUNT(*) AS n FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["n"]
        stored_raw, stored_structured = json.loads(row["raw_json"]), json.loads(row["structured_json"])
        final_style = style_check(row["summary_text"])
        assert row["summary_text"] == SUMMARY and stored_raw == raw and stored_structured == structured
        assert bool(row["push_enabled"]) and not bool(row["pushed"]) and signals == 0 and final_style["ok"]
        assert "stock_watch" not in row["summary_text"] and "stock_watch" not in row["structured_json"]
        print(json.dumps({
            "analysis_id": row_id, "claim_verifier_ok": stored_raw["claim_verifier"]["ok"],
            "claim_support_rate": stored_raw["claim_verifier"]["support_rate"], "trust_gate": stored_raw["trust_gate"],
            "push_enabled": bool(row["push_enabled"]), "pushed": bool(row["pushed"]),
            "structured_json_present": bool(stored_structured), "garbled_text": final_style["garbled_text"],
            "style_checks": final_style, "external_provider_api_called": stored_raw["external_provider_api_called"],
            "trade_signal_count": signals,
        }, ensure_ascii=False))
    finally:
        cursor.close()


if __name__ == "__main__":
    main()
