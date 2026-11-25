"""Persist the 2026-11-26 Codex pre-open memo from readable local facts."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _pre_tw_open_guard_20261119 import (
    MarketAnalysisRecord,
    MySqlEventStore,
    allowed_analysis_slots,
    load_settings,
    rows,
    resolve_market_calendar_state,
    style_check,
    verify_claim_coverage,
)


DAY = "2026-11-26"
FACTS = {
    1038960: ("change_percent=-0.64%", "2026-11-25T22:15:59+00:00"),
    1038961: ("change_percent=-0.65%", "2026-11-25T22:15:59+00:00"),
    1038962: ("change_percent=+7.32%", "2026-11-25T21:15:01+00:00"),
    1038966: ("change_percent=-1.96%", "2026-11-25T21:00:02+00:00"),
}
SUMMARY = """隔夜市場交易的是科技與晶片評價能否守住，而不是全面的風險事件。台股盤前對電子權值的起始判讀偏保守：那斯達克百大與費城半導體指數小幅回落，台積電 ADR 跌幅較大，波動率也上升；最大的未知是這波壓力只屬於前一日震盪後的再平衡，還是會擴大為台灣電子供應鏈的評價收縮。

那斯達克百大下跌 0.64%，費城半導體指數下跌 0.65%，顯示成長與晶片題材仍有溫和的風險折價。VIX 上升 7.32%，代表短期避險需求增加；台積電 ADR 下跌 1.96%，則提供台灣半導體權值較直接的海外情緒參考。這組訊號指向評價與風險偏好的收斂，尚不足以推論終端需求或企業獲利趨勢已出現全面轉折。

傳導到台股時，先進製程、半導體設備、伺服器與大型電子權值較可能先反映海外晶片股的壓力。若開盤後賣壓主要集中在少數高權重電子股，而其他電子類股與成交仍具承接，市場較可能把它視為短線調整；若權值、設備與零組件同步轉弱，則風險折價的範圍可能擴大。

目前已反映的是海外科技與晶片股的溫和回檔，接下來仍可能重新定價的是波動率是否持續上升，以及台積電 ADR 的弱勢是否帶動更廣泛的電子賣壓。若費城半導體與台積電 ADR 轉穩、VIX 回落，偏保守的盤前判讀應降級；若晶片股續弱、波動率再升且台股電子壓力擴散，評價修正就可能加深。盤前訊號只界定風險起點，開盤後的量能與類股參與仍是關鍵確認。"""


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
            "thesis": "科技與半導體溫和回檔且避險升溫，台股電子盤前偏保守，須確認壓力是否擴散。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["先進製程與半導體設備", "伺服器與大型電子權值", "電子零組件的量能與評價"],
            "invalidation": ["費城半導體與台積電 ADR 轉穩", "波動率回落且電子賣壓未擴散"],
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
