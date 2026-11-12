"""Persist the 2026-11-13 Codex pre-open memo from readable local facts."""
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


DAY = "2026-11-13"
FACTS = {
    1037675: ("change_percent=-0.30%", "2026-11-12T22:15:59+00:00"),
    1037676: ("change_percent=-0.54%", "2026-11-12T22:15:59+00:00"),
    1037677: ("change_percent=+6.92%", "2026-11-12T21:15:01+00:00"),
    1037681: ("change_percent=-1.90%", "2026-11-12T21:00:02+00:00"),
}
SUMMARY = """隔夜市場交易的是科技估值與風險承擔是否繼續收縮，而不只是指數小幅回落。台股盤前對電子權值的背景偏保守：美國科技、半導體與台積電 ADR 同步走弱，波動率卻上升；最大的未知是壓力會只停在權值與晶片股，還是擴散到更廣的電子供應鏈。

那斯達克百大下跌 0.30%，費城半導體指數下跌 0.54%，顯示成長與晶片題材的風險偏好尚未回穩。VIX 上升 6.92%，表示市場對短期波動要求較高的風險補償；台積電 ADR 下跌 1.90%，則為台灣半導體權值提供較直接的海外情緒參考。這四項訊號指向評價壓力增加，但尚不足以推論終端需求或企業獲利已全面惡化。

傳導到台股時，半導體、先進封裝、伺服器與電子權值較可能先反映海外晶片股的壓力；若開盤後成交與賣壓仍集中於少數大型股，零組件與其他成長族群未必同步走弱。反之，若權值股轉穩且類股參與沒有繼續收斂，市場可能把隔夜回檔視為風險溢價調整，而非供應鏈基本面的立即改變。

隔夜弱勢已會影響盤前預期，接下來仍可能重新定價的是半導體賣壓是否擴散，以及避險需求能否回落。若費城半導體指數與台積電 ADR 轉穩、VIX 回落，偏保守的判讀應下修；若晶片股續弱且波動率再升，台股電子的評價壓力可能加大。盤前訊號只界定風險起點，仍須由開盤後的量能與類股表現確認。"""


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
        for event in events:
            token, published_at = FACTS[event["id"]]
            assert token in event["summary"] and event["published_at"] == published_at
        structured = {
            "schema_version": "codex-market-analysis-v1",
            "confidence": "medium",
            "thesis": "科技與半導體風險偏好轉弱，台股電子開盤偏保守，須觀察壓力是否擴散。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["半導體與先進封裝", "伺服器與電子權值", "電子零組件的成交與評價"],
            "invalidation": ["半導體與台積電 ADR 轉穩", "波動率回落且賣壓未擴散"],
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
