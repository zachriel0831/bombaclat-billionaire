"""Persist the 2026-10-21 Codex U.S.-close memo from local evidence only."""
import json
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


DAY = "2026-10-21"
FACTS = {
    1035312: ("change_percent=+1.61%", "2026-10-19T21:15:59+00:00"),
    1035313: ("value=18.44", "2026-10-19T20:15:01+00:00"),
    1035315: ("value=98.29", "2026-10-19T23:09:48+00:00"),
    1035332: ("value=5.15", "2026-10-19T00:00:00"),
}
SUMMARY = """這個美股收盤時點對台灣投資人改變的，不是立刻出現一個可交易的方向，而是電子評價仍同時受半導體情緒、長債利率與能源成本牽制。最近可核對的一筆美國市場資料顯示晶片類股較強、波動下降，但最新一晚的美股收盤尚未進入本地資料，不能把既有背景延伸成今天台股開盤的結論。

科技情緒有支撐，評價仍受利率約束

費城半導體指數最近一筆上漲 1.61%，代表當時市場沒有全面撤離晶片風險資產；同一批資料中的 VIX 為 18.44，較前值下降。兩項變化合在一起，只能說風險偏好當時有所改善，不能證明新訂單、價格或毛利率已經上修。對台灣先進製程、封裝與伺服器供應鏈而言，情緒面的支撐仍要由客戶資本支出與企業展望接手，不能只用一個市場時點替代基本面。

十年期美債殖利率最近一筆為 5.15%。這個水準本身不說明利率下一步方向，卻提醒成長產業的遠期獲利仍要通過較高折現門檻。若殖利率後續上行，即使科技題材未變，台灣電子權值與高本益比供應鏈仍可能先面對評價壓力；若殖利率回落且企業展望同步改善，前述壓力才有緩和依據。

能源是另一條不能忽略的傳導線。西德州原油最近一筆為每桶 98.29 美元，較前值小幅回落，但單一報價不足以宣告成本風險解除。航空、物流與耗能製造要觀察燃料及運輸成本是否持續下降；石化業則仍須比較產品售價與原料價格。能源若重新走高，成本與通膨預期可能一起限制估值擴張。

目前市場已反映的是最近一筆晶片情緒較佳、波動下降，而不是已確認的新一晚收盤結果。若半導體強勢擴散、企業展望改善，且殖利率與能源成本回落，這個偏中性的判斷可上修；若科技走勢反轉、獲利預期下修，或利率與油價再度走高，電子情緒支撐就應撤回。最新一晚股債行情尚待本地資料確認，本文只提供有時間邊界的背景判讀。"""


def main() -> None:
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(calendar.local_date) == DAY and "us_close" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    assert not rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows(cursor, "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1035312,1035313,1035315,1035332)")
    assert {event["id"] for event in events} == set(FACTS)
    for event in events:
        token, published_at = FACTS[event["id"]]
        assert token in event["summary"] and event["published_at"] == published_at
    structured = {
        "schema_version": "codex-market-analysis-v1",
        "confidence": "low",
        "thesis": "晶片情緒背景偏正面，但最新收盤未確認，台灣電子評價仍受利率與能源成本限制。",
        "evidence_event_ids": list(FACTS),
        "tw_sector_transmission": ["電子估值與企業展望", "運輸與耗能製造成本", "石化原料與產品報價"],
        "invalidation": ["半導體強勢擴散、展望改善且利率與能源成本回落", "科技反轉、獲利下修或利率與油價走高"],
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
        "evidence_limits": ["latest U.S. close snapshot unavailable in local evidence"],
        "external_provider_api_called": False,
    }
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=DAY,
        analysis_slot="us_close",
        scheduled_time_local="05:00",
        model="codex-local-judgment",
        prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY,
        events_used=len(events),
        market_rows_used=0,
        push_enabled=not calendar.tw.is_trading_day,
        pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False),
        structured_json=json.dumps(structured, ensure_ascii=False),
    ))
    reader = MySqlEventStore(load_settings(".env"))
    read_cursor = reader._cursor()
    row = rows(read_cursor, "SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s", (row_id,))[0]
    signals = rows(read_cursor, "SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["n"]
    stored_raw = json.loads(row["raw_json"])
    stored_structured = json.loads(row["structured_json"])
    assert row["summary_text"] == SUMMARY and stored_raw == raw and stored_structured == structured
    assert not row["push_enabled"] and not row["pushed"] and signals == 0
    assert "stock_watch" not in row["structured_json"] and style_check(row["summary_text"])["ok"]
    print(json.dumps({
        "analysis_id": row_id,
        "claim_verifier_ok": stored_raw["claim_verifier"]["ok"],
        "claim_support_rate": stored_raw["claim_verifier"]["support_rate"],
        "trust_gate": stored_raw["trust_gate"],
        "push_enabled": bool(row["push_enabled"]),
        "pushed": bool(row["pushed"]),
        "structured_json_present": bool(stored_structured),
        "garbled_text": style_check(row["summary_text"])["garbled_text"],
        "style_checks": style_check(row["summary_text"]),
        "external_provider_api_called": stored_raw["external_provider_api_called"],
        "trade_signal_count": signals,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
