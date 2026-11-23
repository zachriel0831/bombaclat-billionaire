"""Persist the 2026-11-24 Codex pre-open memo from readable local facts."""
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


DAY = "2026-11-24"
FACTS = {
    1038759: ("change_percent=+6.86%", "2026-11-23T22:15:59+00:00"),
    1038760: ("change_percent=+14.03%", "2026-11-23T22:15:59+00:00"),
    1038761: ("change_percent=-25.83%", "2026-11-23T21:15:01+00:00"),
    1038765: ("change_percent=+14.08%", "2026-11-23T21:00:02+00:00"),
}
SUMMARY = """隔夜市場交易的核心是科技風險折價能否快速收斂，而不是單一消息本身。台股盤前對電子權值的起始判讀偏正向：美國科技、半導體與台積電 ADR 同步反彈，波動率也明顯降溫；最大的未知是這波修復能否從少數高權重科技股擴大到更廣的電子供應鏈與市場參與度。

那斯達克百大上漲 6.86%，費城半導體指數上漲 14.03%，顯示前一輪對成長與晶片題材的風險折價出現大幅回補。VIX 下跌 25.83%，代表短期避險需求下降；台積電 ADR 上漲 14.08%，則為台灣半導體權值提供直接的海外情緒參考。這組訊號反映的是風險偏好修復與評價回補，不應直接等同於終端需求或企業獲利趨勢已經確認。

傳導到台股時，先進製程、半導體設備、伺服器與電子權值較可能先受惠於海外晶片股的評價回升。若開盤後買盤由大型電子擴散至零組件與其他科技類股，市場會把隔夜強勢解讀為較廣泛的風險偏好改善；若漲勢只停留在少數權值股而成交未跟上，則較接近海外急彈後的短期重新定價。

目前已反映的是海外科技與晶片股的快速修復，仍可能重新定價的是這個修復是否有足夠的類股參與和量能支持。若費城半導體與台積電 ADR 再度轉弱、VIX 回升，或台股開盤後電子漲勢明顯收斂，偏正向的盤前判讀就應降級。隔夜訊號界定的是風險偏好的起點，開盤後的成交與類股廣度才決定它能否延續。"""


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
            "thesis": "科技與半導體風險折價收斂，台股電子盤前偏正向，仍須確認漲勢是否擴散。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["先進製程與半導體設備", "伺服器與電子權值", "零組件與其他科技類股的成交及評價"],
            "invalidation": ["費城半導體與台積電 ADR 再度轉弱", "波動率回升或台股電子漲勢明顯收斂"],
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
