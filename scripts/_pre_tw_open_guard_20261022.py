"""Persist the 2026-10-22 Codex pre-open memo from readable local facts."""
import json
from datetime import datetime, timedelta, timezone

from _us_close_guard_20260917 import (
    MarketAnalysisRecord,
    MySqlEventStore,
    allowed_analysis_slots,
    load_settings,
    resolve_market_calendar_state,
    style_check,
    verify_claim_coverage,
)


DAY = "2026-10-22"
FACTS = {
    1035512: ("change_percent=+1.13%", "2026-10-21T21:15:59+00:00"),
    1035513: ("change_percent=+1.97%", "2026-10-21T21:15:59+00:00"),
    1035514: ("change_percent=-3.64%", "2026-10-21T20:15:01+00:00"),
    1035518: ("change_percent=+1.60%", "2026-10-21T20:00:03+00:00"),
}
SUMMARY = """台股開盤前，市場交易的是科技風險偏好回升能否從少數權值股擴散，而非單純追逐隔夜漲幅。基調可先偏正面但保留分歧：半導體與大型科技同步走強，波動率回落，為電子權值提供情緒支撐；最大不確定性仍是這股買盤是否能延伸到台灣開盤後的成交廣度，而不是只停留在海外龍頭。

那斯達克百大上漲 1.13%，費城半導體指數上漲 1.97%，代表隔夜資金願意重新提高對成長與晶片題材的曝險。VIX 下跌 3.64%，使這波上漲較不像避險需求驟升下的短暫反彈。台積電 ADR 上漲 1.60%，則把海外半導體情緒帶到台灣權值股的開盤參考。四個訊號共同指向風險偏好改善，但它們只說明估值壓力暫時放鬆，還不能直接推論終端需求或企業獲利已全面上修。

傳導至台股時，半導體、先進封裝、伺服器與電子權值會先受惠於海外情緒改善；若台積電與大型電子帶動成交擴散，供應鏈的相對表現才較有延續性。反過來說，若資金仍集中於少數權值，指數雖有支撐，多數電子次族群未必同步受益。利率、美元與能源成本仍是評價的外部限制，任何一端重新轉緊，都可能讓遠期獲利比重較高的電子族群先承受折現壓力。

目前價格已開始反映隔夜科技與半導體走強，尚待重新定價的是這份強勢能否由量能、類股廣度與企業展望確認。若半導體轉弱、波動率回升，或台積電 ADR 的相對強勢消失，偏正面的盤前判讀應下修；若成交持續擴散且外部成本壓力未惡化，海外風險偏好才有機會轉為較廣泛的台股支撐。盤前訊號用來界定起點，不能取代開盤後的確認。"""


def rows(cursor, sql, params=()):
    cursor.execute(sql, params)
    return [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and "pre_tw_open" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    assert not rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,))
    events = rows(cursor, "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)", tuple(FACTS))
    assert {event["id"] for event in events} == set(FACTS)
    for event in events:
        token, stamp = FACTS[event["id"]]
        assert token in event["summary"] and event["published_at"] == stamp

    structured = {
        "schema_version": "codex-market-analysis-v1",
        "confidence": "medium",
        "thesis": "科技風險偏好改善，但台股電子須等待成交廣度與展望確認。",
        "evidence_event_ids": list(FACTS),
        "tw_sector_transmission": ["半導體與先進封裝", "伺服器與電子權值", "電子次族群的成交擴散"],
        "invalidation": ["半導體轉弱或波動率回升", "台積電 ADR 強勢消失", "外部成本壓力重新轉緊"],
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
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=DAY, analysis_slot="pre_tw_open", scheduled_time_local="07:30",
        model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0,
        push_enabled=True, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False),
        structured_json=json.dumps(structured, ensure_ascii=False),
    ))
    row = rows(cursor, "SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s", (row_id,))[0]
    signals = rows(cursor, "SELECT COUNT(*) AS n FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["n"]
    stored_raw = json.loads(row["raw_json"])
    assert row["summary_text"] == SUMMARY and stored_raw == raw and json.loads(row["structured_json"]) == structured
    assert row["push_enabled"] == 1 and not row["pushed"] and signals == 0 and "stock_watch" not in row["structured_json"]
    print(json.dumps({
        "analysis_id": row_id, "claim_verifier_ok": stored_raw["claim_verifier"]["ok"],
        "claim_support_rate": stored_raw["claim_verifier"]["support_rate"], "trust_gate": stored_raw["trust_gate"],
        "push_enabled": bool(row["push_enabled"]), "pushed": bool(row["pushed"]),
        "structured_json_present": bool(json.loads(row["structured_json"])),
        "garbled_text": style_check(row["summary_text"])["garbled_text"],
        "style_checks": style_check(row["summary_text"]),
        "external_provider_api_called": stored_raw["external_provider_api_called"], "trade_signal_count": signals,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
