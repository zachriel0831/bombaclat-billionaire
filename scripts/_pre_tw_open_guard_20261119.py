"""Persist the 2026-11-19 Codex pre-open memo from readable local facts."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _pre_tw_open_guard_20261118 import (
    MarketAnalysisRecord,
    MySqlEventStore,
    allowed_analysis_slots,
    load_settings,
    rows,
    resolve_market_calendar_state,
    style_check,
    verify_claim_coverage,
)


DAY = "2026-11-19"
FACTS = {
    1038274: ("change_percent=-0.13%", "2026-11-18T15:52:49+00:00"),
    1038275: ("change_percent=-0.37%", "2026-11-18T15:52:52+00:00"),
    1038276: ("change_percent=-3.02%", "2026-11-18T15:37:46+00:00"),
    1038280: ("change_percent=+0.38%", "2026-11-18T15:52:53+00:00"),
}
SUMMARY = """隔夜市場交易的是科技評價的小幅降溫會不會擴大，而非單一方向的避險。台股電子盤前基調偏中性略謹慎：美國科技與半導體指數走低，但波動率回落、台積電 ADR 逆勢收高；最大的未知是海外賣壓會停在少數題材，還是演成電子供應鏈更廣泛的評價修正。

那斯達克百大下跌 0.13%，費城半導體指數下跌 0.37%，顯示科技與晶片族群仍有輕微的風險折價。VIX 下跌 3.02%，則表示市場並未把這段回檔解讀為波動風險快速升高；台積電 ADR 上漲 0.38%，提供台灣電子權值相對穩定的海外參考。這組訊號更像是題材內部的分化，而不是需求或信用條件出現全面惡化。

傳導到台股時，先進製程、半導體設備、伺服器與電子權值仍會受美國晶片股的評價變化牽動，但權值股若維持相對韌性，壓力未必等比例延伸至零組件與其他電子類股。反過來，若開盤後電子族群普遍轉弱，市場就可能把隔夜的輕微回檔重新解讀為資金降低成長曝險，折價範圍才會擴大。

目前已反映的是科技與半導體指數的溫和走弱；尚待重新定價的是台積電 ADR 的相對強勢能否帶動台灣電子的承接，以及波動率是否維持回落。若費城半導體續弱且權值股失去支撐，盤前的中性框架應轉為保守；若台積電 ADR 維持韌性、波動率未反彈且電子參與改善，海外回檔對台股的影響就應降級。盤前訊號只提供風險起點，仍須以開盤後量能與類股參與確認。"""


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
            "thesis": "科技與半導體小幅走弱但權值相對韌性，台股電子盤前中性略謹慎。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["先進製程與半導體設備", "伺服器與電子權值", "電子零組件的量能與評價"],
            "invalidation": ["半導體續弱且權值股失去支撐", "台積電 ADR 維持韌性、波動率未反彈且電子參與改善"],
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
