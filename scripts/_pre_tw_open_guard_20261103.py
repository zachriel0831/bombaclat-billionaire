"""Persist the 2026-11-03 Codex pre-open memo from readable local facts."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _us_close_guard_20261024 import (
    MarketAnalysisRecord,
    MySqlEventStore,
    allowed_analysis_slots,
    load_settings,
    rows,
    resolve_market_calendar_state,
    style_check,
    verify_claim_coverage,
)


DAY = "2026-11-03"
FACTS = {
    1036677: ("change_percent=-1.39%", "2026-11-02T22:15:59+00:00"),
    1036678: ("change_percent=-3.37%", "2026-11-02T22:15:59+00:00"),
    1036679: ("change_percent=+8.91%", "2026-11-02T21:15:01+00:00"),
    1036683: ("change_percent=-1.85%", "2026-11-02T21:00:02+00:00"),
}
SUMMARY = """隔夜市場交易的是科技與半導體的估值壓力是否擴大，而不只是大盤的單日回檔。台股電子權值的開盤背景偏保守，最大不確定性是賣壓會否由少數晶片股擴散到更廣的供應鏈；若情緒很快穩住，指數的弱勢未必等同於所有電子需求轉差。

那斯達克百大下跌 1.39%，費城半導體指數下跌 3.37%，顯示資金先收縮對成長與晶片題材的風險承擔。VIX 上升 8.91%，說明避險需求同步升高，市場對短期波動的容忍度下降。台積電 ADR 下跌 1.85%，提供台灣半導體權值較直接的海外情緒參考。這組訊號反映的是評價與風險偏好轉弱，不能直接推論終端需求或企業獲利已全面惡化。

傳導到台股時，半導體、先進封裝、伺服器與電子權值可能先承受海外晶片股回檔的壓力；若開盤後賣壓擴大且成交集中於大型股，相關零組件的相對表現也可能轉弱。反過來說，若權值股止穩、成交沒有繼續萎縮，市場仍可能把這次回檔視為風險溢價的調整，而非供應鏈基本面的立即改變。利率、美元與能源成本仍會影響遠期獲利比重較高族群的評價，因此海外科技走弱不等於所有台灣電子題材都以相同幅度重新定價。

隔夜下跌已會影響盤前預期，接下來仍可能重新定價的是波動是否延續，以及半導體弱勢會否擴散。若費城半導體指數與台積電 ADR 轉穩、波動率回落，偏保守的盤前判讀應下修；若晶片股續弱且避險需求再升，台股電子的評價壓力可能加大。盤前訊號只界定風險起點，仍須由開盤後的量能與類股表現確認。"""


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
            "thesis": "科技與半導體風險偏好轉弱，台股電子開盤偏保守，須觀察賣壓是否擴散。",
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
        assert row["push_enabled"] == 1 and not row["pushed"] and signals == 0 and final_style["ok"]
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
