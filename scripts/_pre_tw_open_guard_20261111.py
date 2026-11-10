"""Persist the 2026-11-11 Codex pre-open memo from readable local facts."""
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


DAY = "2026-11-11"
FACTS = {
    1037475: "change_percent=-0.60%",
    1037476: "change_percent=-0.35%",
    1037477: "change_percent=-2.31%",
    1037481: "change_percent=+2.02%",
}
SUMMARY = """隔夜市場交易的重點不是全面撤出科技股，而是大型成長股與半導體權值出現分化。台股盤前對電子的判讀偏中性略保守：海外指數仍有壓力，但台積電 ADR 逆勢走高，讓半導體主線不宜直接等同於整體風險偏好轉弱。最大的未知，是這種分化能否在台股開盤後轉成電子權值的支撐，或只是少數公司承接資金。

那斯達克百大下跌 0.60%，費城半導體指數下跌 0.35%，顯示高估值與晶片題材仍在調整；但 VIX 下跌 2.31%，避險需求沒有同步升高，較像資金重新排序而非明顯的風險事件。台積電 ADR 上漲 2.02%，則提供台灣先進製程與相關供應鏈較具韌性的海外參考。這四項訊號合在一起，代表盤前不宜只看指數方向，更要分辨資金是否仍集中在具代表性的半導體權值。

傳導到台灣時，電子權值若能維持相對強勢，先進製程、封裝測試、伺服器與部分零組件的情緒可能先獲支撐；若大型電子撐住但廣度沒有改善，其他成長族群仍可能跟隨海外指數承壓。非電子表現則較依賴本地成交與資金輪動，因此不應把 ADR 的單日表現延伸為整體市場的方向判斷。

海外指數回落已先被市場看見，接下來仍可能重估的是半導體相對強勢能否擴散。若台積電 ADR 回吐漲幅、費城半導體指數續弱，且波動率重新上升，盤前的分化判讀就要轉為更保守；反之，若電子權值穩住並帶動成交擴散，市場可能把隔夜回檔視為評價整理，而非需求全面降溫。"""


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
            "thesis": "科技風險偏好分化，台股電子盤前中性略保守，仍須確認半導體強勢能否擴散。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["先進製程與封裝測試", "伺服器與電子權值", "零組件的成交擴散"],
            "invalidation": ["台積電 ADR 回吐且半導體續弱", "波動率回升並壓抑電子成交"],
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
