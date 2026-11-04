"""Persist the 2026-11-05 Codex pre-open memo from readable local facts."""
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


DAY = "2026-11-05"
FACTS = {
    1036875: "change_percent=+0.91%",
    1036876: "change_percent=-3.13%",
    1036877: "change_percent=-20.26%",
    1036881: "change_percent=-2.24%",
}
SUMMARY = """隔夜市場交易的是風險偏好回升能否跨過半導體的壓力，而非單純的科技指數反彈。台股開盤背景因此偏向分化：大盤與成長型資產的氣氛改善，但電子權值仍可能承受較謹慎的評價；最大的變數是晶片鏈的下跌究竟只是個別獲利與評價調整，還是會擴大為供應鏈風險。

那斯達克百大上漲 0.91%、VIX 下跌 20.26%，代表整體避險需求明顯回落，資金願意重新承擔部分成長風險。不過費城半導體指數下跌 3.13%，台積電 ADR 下跌 2.24%，說明資金回流並沒有平均地落在晶片鏈。這個背離對盤前較重要：若市場把它視為少數權值或評價調整，台灣電子未必跟隨全面轉弱；若半導體賣壓持續，則大盤反彈對台股權值的支撐會較有限。

傳導到台股，先進製程、封裝、伺服器與電子零組件會先看海外半導體跌勢能否收斂，再決定是否跟隨大盤風險偏好改善。權值股若開低後能穩住，資金可能轉向受惠於整體科技情緒回暖的族群；反之，若成交與賣壓集中在晶片相關大型股，供應鏈的評價壓力仍可能放大。台積電在這裡僅是海外半導體情緒的傳導指標，不能替代台股開盤後的實際資金選擇。

隔夜已反映的是波動回落與廣泛風險偏好改善，尚待重估的是半導體弱勢能否止步。若費城半導體指數和台積電 ADR 轉穩，且台股電子沒有出現擴散賣壓，偏保守的盤前判讀就應下修；若晶片股續弱而大盤反彈失去廣度，台灣電子仍可能面臨較高的估值折價。盤前訊號只提供開盤的風險地圖，後續仍要由量能與類股強弱確認。"""


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
            "thesis": "整體風險偏好回升，但半導體仍走弱，台股電子開盤可能分化。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["先進製程與封裝", "伺服器與電子權值", "電子零組件的評價與成交"],
            "invalidation": ["半導體與台積電 ADR 轉穩", "台股電子賣壓未擴散"],
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
