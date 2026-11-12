"""Persist the 2026-11-12 Codex pre-open memo from readable local facts."""
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


DAY = "2026-11-12"
FACTS = {
    1037575: ("change_percent=+2.28%", "2026-11-11T22:15:59+00:00"),
    1037576: ("change_percent=+5.66%", "2026-11-11T22:15:59+00:00"),
    1037577: ("change_percent=-10.12%", "2026-11-11T21:15:01+00:00"),
    1037581: ("change_percent=+4.25%", "2026-11-11T21:00:03+00:00"),
}
SUMMARY = """隔夜市場交易的是科技風險偏好是否重新擴散，而不只是指數反彈。台股盤前對電子的背景偏正向：美國科技、半導體與台積電 ADR 同步走強，避險需求也回落；最大的未知是這波上漲能否從少數權值與晶片股，延伸成開盤後更廣的成交與類股參與。

那斯達克百大上漲 2.28%，費城半導體指數上漲 5.66%，顯示資金重新提高對成長與晶片題材的承擔。VIX 下跌 10.12%，代表波動溢價沒有伴隨反彈而升高，較接近風險胃納改善。台積電 ADR 上漲 4.25%，則為台灣先進製程及其供應鏈提供較直接的海外情緒參考。四項訊號合在一起，市場正在修正前一日對科技與半導體的保守定價，但單日漲勢尚不足以替代需求與獲利的後續確認。

傳導到台股時，電子權值若能承接海外強勢，先進製程、封裝測試、伺服器與部分電子零組件的評價情緒有機會先改善；若成交只集中於少數大型股，其他成長族群未必同步受惠。非電子則仍須看本地資金輪動，不能直接由美股科技反彈推論整體市場都將走強。

海外科技回升與波動下降已是盤前可見的利多，接下來仍可能重新定價的是半導體強勢能否擴散，以及台積電 ADR 的表現能否獲得台股量能呼應。若費城半導體與台積電 ADR 很快回吐、VIX 再度上升，這個偏正向判讀就要降級；反之，若電子權值穩住並帶動參與擴大，市場可能把隔夜走勢解讀為風險偏好回補，而非短暫的技術性反彈。"""


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
            "thesis": "科技風險偏好回補，台股電子盤前偏正向，仍須確認半導體強勢能否擴散。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["先進製程與封裝測試", "伺服器與電子權值", "電子零組件的成交擴散"],
            "invalidation": ["半導體與台積電 ADR 回吐漲幅", "波動率回升且電子參與未擴大"],
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
            "evidence_freshness": {str(event_id): published_at for event_id, (_, published_at) in FACTS.items()},
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
