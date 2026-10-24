"""Create the 2026-10-24 Codex U.S.-close memo from local evidence only."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _us_close_guard_20260917 import (
    MarketAnalysisRecord,
    MySqlEventStore,
    allowed_analysis_slots,
    load_settings,
    resolve_market_calendar_state,
    rows,
    style_check,
    verify_claim_coverage,
)


DAY = "2026-10-24"
SLOT = "us_close"
FACTS = {
    1035691: ("change_percent=+0.44%", "2026-10-23T21:15:59+00:00"),
    1035708: ("change_percent=-0.52%", "2026-10-23T20:00:00+00:00"),
    1035692: ("change_percent=+2.21%", "2026-10-23T20:15:01+00:00"),
    1035694: ("change_percent=+3.99%", "2026-10-23T20:59:58+00:00"),
}
SUMMARY = """這次美股收盤給台灣投資人的訊號偏向「科技供應鏈尚有韌性，但風險溢價正在回來」。半導體指數小幅走高，未出現全面撤離科技股的訊號；不過大盤走弱、波動升高與油價急漲同時發生，代表市場並沒有把這種韌性解讀成可以忽略利率、通膨與地緣風險。

收盤結構比單一指數更值得留意。費城半導體指數上漲 0.44%，顯示晶片鏈相對抗跌；標普 500 ETF 下跌 0.52%，VIX 上升 2.21%，則說明風險偏好沒有同步擴散。這種分化下，市場仍願意保留與運算需求相關的敘事，但對整體景氣、資金成本與企業獲利的容忍度正在下降。若只有少數題材支撐，估值上修會比指數反彈更挑剔。

油價是這一晚新增的壓力來源。西德州原油上漲 3.99%，會先透過運輸、石化原料與耗能製造成本影響台灣產業；若油價持續偏高，也可能讓通膨預期回升，進一步壓縮長天期成長資產的評價空間。因此，先進製程、伺服器、封裝與記憶體供應鏈雖可受惠於半導體情緒相對穩定，仍須面對資金成本與終端需求是否承接的檢驗。航空、物流與石化等成本敏感族群，則對能源價格更直接。

目前較可能已被市場反映的是：科技主題尚未失速，但整體風險胃納轉弱。仍可能重新定價的，是油價上行是否延續、波動是否繼續擴大，以及晶片相對強勢能否由客戶支出與獲利展望證實。若半導體強度擴散到更廣的風險資產，且油價與波動回落，這個偏審慎的判斷需要下修；反之，若大盤續弱、油價再升而企業展望轉差，台灣電子估值與成本敏感產業的壓力可能同步加大。單日收盤只能界定風險邊界，不能替代後續基本面確認。"""


def main() -> None:
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and SLOT in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    assert not rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (DAY, SLOT))
    events = rows(cursor, "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1035691,1035708,1035692,1035694)")
    assert {event["id"] for event in events} == set(FACTS)
    for event in events:
        token, published_at = FACTS[event["id"]]
        assert token in event["summary"] and event["published_at"] == published_at
    structured = {
        "schema_version": "codex-market-analysis-v1",
        "confidence": "medium",
        "thesis": "晶片鏈相對有韌性，但大盤、波動與油價顯示風險溢價回升，台灣產業須分別檢驗需求與成本。",
        "evidence_event_ids": list(FACTS),
        "tw_sector_transmission": ["先進製程、伺服器、封裝與記憶體的估值及需求驗證", "航空、物流與耗能製造的燃料及運輸成本", "石化業的原料與產品價差"],
        "invalidation": ["半導體強度擴散且油價、波動回落", "大盤續弱、油價再升且企業展望轉差"],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY,
        structured_payload=structured,
        events_payload=events,
        market_payload=[],
    )
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
        "external_provider_api_called": False,
    }
    result = {"dry_run": "--write" not in sys.argv, "claim_verifier_ok": verifier["ok"], "style_ok": style["ok"], "push_enabled": not calendar.tw.is_trading_day}
    if "--write" not in sys.argv:
        print(json.dumps(result, ensure_ascii=False))
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
    assert bool(row["push_enabled"]) and not bool(row["pushed"]) and signals == 0
    assert "stock_watch" not in row["summary_text"] and "stock_watch" not in row["structured_json"] and final_style["ok"]
    print(json.dumps({"analysis_id": row_id, "claim_verifier_ok": stored_raw["claim_verifier"]["ok"], "claim_support_rate": stored_raw["claim_verifier"]["support_rate"], "trust_gate": stored_raw["trust_gate"], "push_enabled": bool(row["push_enabled"]), "pushed": bool(row["pushed"]), "structured_json_present": bool(stored_structured), "garbled_text": final_style["garbled_text"], "style_checks": final_style, "external_provider_api_called": stored_raw["external_provider_api_called"], "trade_signal_count": signals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
