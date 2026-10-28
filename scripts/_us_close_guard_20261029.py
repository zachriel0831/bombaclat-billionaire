"""Store the 2026-10-29 local-evidence U.S.-close memo; dry-run by default."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _us_close_guard_20261024 import (
    MarketAnalysisRecord,
    MySqlEventStore,
    allowed_analysis_slots,
    load_settings,
    rows,
    style_check,
    verify_claim_coverage,
    resolve_market_calendar_state,
)


DAY = "2026-10-29"
SLOT = "us_close"
FACTS = {
    1036081: ("change_percent=+1.29%", "2026-10-27T21:15:59+00:00"),
    1036082: ("change_percent=+3.60%", "2026-10-27T21:15:59+00:00"),
    1036083: ("change_percent=-4.73%", "2026-10-27T20:15:01+00:00"),
    1036084: ("change_percent=+0.04%", "2026-10-27T22:04:59+00:00"),
}
SUMMARY = """這次美股收盤對台灣投資人的可用訊息，是科技風險偏好仍有支撐，但不能把前一交易日的漲勢當成最新一晚已確認的延續。本機尚未取得最新美股收盤快照，因此台灣電子供應鏈今天應把隔夜情緒視為背景，並以後續需求、利率與匯率變化確認，而非直接外推為台股趨勢。

最後可核對的一組本機行情中，那斯達克百大與費城半導體指數同步上漲，波動指數則回落，顯示資金當時願意回到成長與晶片題材。這條證據鏈有利於先進製程、伺服器、封裝與記憶體等台灣供應鏈的情緒面，但它只能說明風險偏好改善，不能證明接單、毛利率或終端需求已同步轉強。

美元指數小幅走高，提醒估值與匯率傳導仍須分開看。若美元延續走強或長天期資金成本上行，電子成長題材的折現壓力可能先增加；若半導體強勢持續擴散，且企業展望能接住市場期待，台灣科技權值與相關零組件才有較完整的支撐。出口導向製造亦須觀察匯率對報價與成本的雙向影響，不能只用單一行情判斷受惠與否。

目前較可能被重新定價的，是科技漲勢能否從題材擴大為更廣的風險偏好，以及美元與利率會不會限制估值。若最新收盤顯示半導體轉弱、波動回升，或美元持續升值，這份偏正向但保留的判讀便應撤回；反之，若科技強勢擴散且資金成本壓力緩和，台灣電子情緒的支撐才會更可靠。最新一晚資料仍待本機來源補齊，本文不替代後續開盤與基本面確認。"""


def main() -> None:
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and SLOT in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    assert not rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (DAY, SLOT))
    events = rows(cursor, "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1036081,1036082,1036083,1036084)")
    assert {event["id"] for event in events} == set(FACTS)
    for event in events:
        token, published_at = FACTS[event["id"]]
        assert token in event["summary"] and event["published_at"] == published_at
    structured = {
        "schema_version": "codex-market-analysis-v1",
        "confidence": "low",
        "thesis": "科技風險偏好曾改善，但最新一晚收盤未由本機資料確認；台灣電子須以需求與資金成本驗證。",
        "evidence_event_ids": list(FACTS),
        "tw_sector_transmission": ["先進製程、伺服器、封裝與記憶體的情緒與需求驗證", "出口製造的匯率與報價傳導", "電子成長題材的估值折現壓力"],
        "invalidation": ["半導體轉弱、波動回升或美元續升", "科技強勢擴散且資金成本壓力緩和"],
    }
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier["ok"] and style["ok"], json.dumps({"verifier": verifier, "style": style}, ensure_ascii=False)
    raw = {
        "automation_id": "market-analysis-codex-guard-us-close",
        "generator": "codex_automation",
        "display_title": DAY,
        "calendar": calendar.to_dict(),
        "evidence_event_ids": list(FACTS),
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style,
        "evidence_freshness": {str(event_id): published_at for event_id, (_, published_at) in FACTS.items()},
        "evidence_limits": ["latest U.S. close snapshot unavailable locally", "previous session market data used as background only"],
        "external_provider_api_called": False,
    }
    if "--write" not in sys.argv:
        print(json.dumps({"dry_run": True, "claim_verifier": verifier, "style_checks": style, "push_enabled": not calendar.tw.is_trading_day}, ensure_ascii=False))
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=DAY, analysis_slot=SLOT, scheduled_time_local="05:00", model="codex-local-judgment",
        prompt_version="codex-flexible-briefing-memo-v1", summary_text=SUMMARY, events_used=len(events), market_rows_used=0,
        push_enabled=not calendar.tw.is_trading_day, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False),
        structured_json=json.dumps(structured, ensure_ascii=False),
    ))
    reader = MySqlEventStore(load_settings(".env"))
    read_cursor = reader._cursor()
    row = rows(read_cursor, "SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s", (row_id,))[0]
    signals = rows(read_cursor, "SELECT COUNT(*) AS n FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["n"]
    stored_raw, stored_structured = json.loads(row["raw_json"]), json.loads(row["structured_json"])
    final_style = style_check(row["summary_text"])
    assert row["summary_text"] == SUMMARY and stored_raw == raw and stored_structured == structured
    assert bool(row["push_enabled"]) == (not calendar.tw.is_trading_day) and not bool(row["pushed"]) and signals == 0
    assert "stock_watch" not in row["summary_text"] and "stock_watch" not in row["structured_json"] and final_style["ok"]
    print(json.dumps({"analysis_id": row_id, "claim_verifier_ok": stored_raw["claim_verifier"]["ok"], "claim_support_rate": stored_raw["claim_verifier"]["support_rate"], "trust_gate": stored_raw["trust_gate"], "push_enabled": bool(row["push_enabled"]), "pushed": bool(row["pushed"]), "structured_json_present": bool(stored_structured), "garbled_text": final_style["garbled_text"], "style_checks": final_style, "external_provider_api_called": stored_raw["external_provider_api_called"], "trade_signal_count": signals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
