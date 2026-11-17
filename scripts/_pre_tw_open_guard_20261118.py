"""Persist the 2026-11-18 Codex pre-open memo from readable local facts."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _pre_tw_open_guard_20261113 import (
    MarketAnalysisRecord,
    MySqlEventStore,
    allowed_analysis_slots,
    load_settings,
    rows,
    resolve_market_calendar_state,
    style_check,
    verify_claim_coverage,
)


DAY = "2026-11-18"
FACTS = {
    1038175: ("change_percent=-0.72%", "2026-11-17T22:15:59+00:00"),
    1038176: ("change_percent=+0.34%", "2026-11-17T22:15:59+00:00"),
    1038177: ("change_percent=+11.13%", "2026-11-17T21:15:01+00:00"),
    1038181: ("change_percent=-3.68%", "2026-11-17T21:00:02+00:00"),
}
SUMMARY = """隔夜市場交易的是風險偏好轉弱能否止於大型科技，還是會演變成更廣泛的成長股折價。台股盤前對電子權值的起始判讀偏保守：那斯達克百大走弱、台積電 ADR 明顯回落，波動率同步升高；最大的未知是半導體族群能否維持相對韌性，而不是單看美股指數漲跌。

那斯達克百大下跌 0.72%，反映成長題材的估值承擔正在收縮；VIX 上升 11.13%，表示避險需求的增加不只是一般性的獲利回吐。台積電 ADR 下跌 3.68%，提供台灣電子權值較直接的海外情緒壓力參考。不過，費城半導體指數仍上漲 0.34%，顯示晶片族群內部並非全面走弱，市場現在真正交易的是風險折價會不會由大型科技擴散至整個供應鏈。

傳導到台股時，先進製程、伺服器、半導體設備與電子權值會先面對海外評價修正；若開盤壓力集中在少數大型股，而晶片相關族群仍能維持相對強度，零組件與其他電子類股未必等比例承壓。反過來，若成交萎縮、電子多數類股同步轉弱，市場會把美股的波動解讀為資金降低成長曝險，盤面折價範圍便可能擴大。

目前已反映的是大型科技走弱與避險升溫；仍可能重新定價的是半導體相對強勢能否維持，以及波動率是否繼續上行。若台積電 ADR 止穩、費城半導體延續相對韌性且 VIX 回落，偏保守的盤前框架應下修；若科技指數續弱、波動率再升且電子賣壓擴散，台股電子的評價壓力可能加大。盤前訊號只界定風險起點，仍須由開盤後量能與類股參與確認。"""


def main() -> None:
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and "pre_tw_open" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    try:
        existing = rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (DAY, "pre_tw_open"))
        assert not existing, "target row already exists; inspect before replacing it"
        events = rows(cursor, "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)", tuple(FACTS))
        assert {event["id"] for event in events} == set(FACTS)
        for event in events:
            token, published_at = FACTS[event["id"]]
            assert token in event["summary"] and event["published_at"] == published_at
        structured = {
            "schema_version": "codex-market-analysis-v1",
            "confidence": "medium",
            "thesis": "大型科技風險偏好轉弱，台股電子盤前偏保守，須確認半導體相對強勢能否維持。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["先進製程與半導體設備", "伺服器與電子權值", "電子零組件的量能與評價"],
            "invalidation": ["台積電 ADR 止穩且費城半導體維持相對韌性", "波動率回落且電子賣壓未擴散"],
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
            "evidence_freshness": {str(key): stamp for key, (_, stamp) in FACTS.items()},
            "evidence_limits": ["Taiwan opening breadth and corporate outlook remain unconfirmed"],
        }
        if "--write" not in sys.argv:
            print(json.dumps({"dry_run": True, "claim_verifier": verifier, "style_checks": style, "push_enabled": True}, ensure_ascii=False))
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
