"""Persist the 2026-10-29 Codex pre-open memo from readable local facts."""
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


DAY = "2026-10-29"
FACTS = {
    1036182: ("change_percent=+0.55%", "2026-10-28T21:15:59+00:00"),
    1036183: ("change_percent=+1.75%", "2026-10-28T21:15:59+00:00"),
    1036184: ("change_percent=-3.48%", "2026-10-28T20:15:01+00:00"),
    1036188: ("change_percent=+0.60%", "2026-10-28T20:00:02+00:00"),
}
SUMMARY = """隔夜市場交易的是半導體風險偏好能否維持，而非全面景氣已經轉強。台股電子權值開盤的背景偏正面，最大不確定性仍是買盤會否從大型晶片股擴散到更廣的供應鏈；若廣度不足，指數與多數電子次族群可能出現差異。

那斯達克百大上漲 0.55%，費城半導體指數上漲 1.75%，顯示資金對成長與晶片題材仍有承接。VIX 下跌 3.48%，避險需求同步降溫，讓科技股走強不只是波動放大時的短線反彈。台積電 ADR 上漲 0.60%，提供台灣半導體權值較直接的海外情緒參考。這組訊號有利於估值情緒，但不足以直接證明終端需求、接單或企業獲利已同步上修。

傳導到台股時，半導體、先進封裝、伺服器與電子權值通常先反應海外晶片股的強勢；若成交擴散，相關零組件的相對表現才較可能延續。若買盤仍集中在少數大型股，指數即使有支撐，供應鏈未必同幅受惠。利率、美元與能源成本仍會影響遠期獲利比重較高族群的評價，因此海外科技上漲不等於所有成長題材都會一起重估。

隔夜科技與半導體走強已成為開盤預期的一部分，下一步仍要看量能與類股廣度。若半導體轉弱、波動率回升，或台積電 ADR 的相對強勢消失，偏正面的盤前判讀應下修；若大型電子帶動成交擴散，且資金成本壓力未惡化，海外風險偏好才可能轉成較廣泛的台股支撐。盤前訊號只界定起點，不能取代開盤後的確認。"""


def main() -> None:
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and "pre_tw_open" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    existing = rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (DAY, "pre_tw_open"))
    assert not existing, "target row already exists; use a targeted repair after inspecting it"
    events = rows(cursor, "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)", tuple(FACTS))
    assert {event["id"] for event in events} == set(FACTS)
    for event in events:
        token, stamp = FACTS[event["id"]]
        assert token in event["summary"] and event["published_at"] == stamp
    structured = {
        "schema_version": "codex-market-analysis-v1",
        "confidence": "medium",
        "thesis": "半導體風險偏好維持，但台股電子仍須等待成交廣度確認。",
        "evidence_event_ids": list(FACTS),
        "tw_sector_transmission": ["半導體與先進封裝", "伺服器與電子權值", "電子次族群的成交擴散"],
        "invalidation": ["半導體轉弱或波動率回升", "台積電 ADR 相對強勢消失", "資金成本壓力惡化"],
    }
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier["ok"] and style["ok"], json.dumps({"verifier": verifier, "style": style}, ensure_ascii=False)
    raw = {
        "automation_id": "market-analysis-codex-guard-pre-open",
        "generator": "codex_automation",
        "display_title": DAY,
        "calendar": calendar.to_dict(),
        "evidence_event_ids": list(FACTS),
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style,
        "external_provider_api_called": False,
        "generated_at": now.isoformat(),
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


if __name__ == "__main__":
    main()
