"""Persist the 2026-11-10 Codex pre-open memo from readable local facts."""
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


DAY = "2026-11-10"
FACTS = {
    1037375: "change_percent=+3.40%",
    1037376: "change_percent=+6.85%",
    1037377: "change_percent=-22.31%",
    1037381: "change_percent=+3.51%",
}
SUMMARY = """隔夜市場交易的核心是科技風險偏好重新回升，而非單靠指數反彈。台股盤前的電子權值與半導體供應鏈背景偏正向；最大不確定性在於這波回補能否延續到台股開盤後的成交與類股擴散，而不是只停留在海外大型科技股。

那斯達克百大上漲 3.40%，費城半導體指數上漲 6.85%，台積電 ADR 上漲 3.51%，三者同步走強，代表市場願意重新承擔晶片與成長題材的評價風險。VIX 回落 22.31%，使這次上漲不只是少數權值拉抬，也伴隨避險需求下降；但波動率快速收斂後，盤面仍需確認是否有足夠量能承接。

傳導到台灣時，先進製程、封裝測試、伺服器與電子零組件通常會先反映海外半導體情緒的改善；若大型電子權值開高後仍能維持相對強勢，資金才可能由指數層面延伸到供應鏈。台積電 ADR在這裡只是海外半導體情緒的參考，不等同於台股現貨開盤後的實際資金流向；非電子族群的表現仍取決於本地成交結構。

隔夜價格已先反映科技股回暖，接下來尚未完全定價的是強勢能否轉成更廣的風險承擔。若半導體指數與台積電 ADR 很快回吐漲幅，或台股電子開盤後無法擴散、成交反而縮減，盤前偏正向的判讀就要下修；反之，波動率維持回落且電子類股強弱一致，市場對供應鏈風險溢酬的調整可能延續。"""


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
        assert all(FACTS[event["id"]] in event["summary"] for event in events)
        structured = {
            "schema_version": "codex-market-analysis-v1",
            "confidence": "medium",
            "thesis": "海外科技與半導體風險偏好回升，台股電子盤前偏正向，仍須確認開盤後的成交擴散。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["先進製程與封裝測試", "伺服器與電子權值", "電子零組件的成交擴散"],
            "invalidation": ["半導體與台積電 ADR 回吐漲幅", "電子類股無法擴散且成交縮減"],
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
            "evidence_freshness": {str(event["id"]): event["published_at"] for event in events},
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
