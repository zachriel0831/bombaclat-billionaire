"""Persist the 2026-10-28 Codex pre-open memo from readable local facts."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _us_close_guard_20260917 import (
    MarketAnalysisRecord, MySqlEventStore, allowed_analysis_slots, load_settings,
    resolve_market_calendar_state, style_check, verify_claim_coverage,
)


DAY = "2026-10-28"
FACTS = {
    1036081: ("change_percent=+1.29%", "2026-10-27T21:15:59+00:00"),
    1036082: ("change_percent=+3.60%", "2026-10-27T21:15:59+00:00"),
    1036083: ("change_percent=-4.73%", "2026-10-27T20:15:01+00:00"),
    1036087: ("change_percent=+2.95%", "2026-10-27T20:00:02+00:00"),
}
SUMMARY = """隔夜市場交易的是晶片風險偏好快速回溫能否轉成台股開盤的廣泛買盤。台股電子權值的起點偏正面，最大不確定性是資金會否由少數大型半導體股擴散到供應鏈；若廣度沒有跟上，指數走強與多數族群的表現仍可能分化。

那斯達克百大上漲 1.29%，費城半導體指數上漲 3.60%，資金明顯回到成長與晶片題材。VIX 下跌 4.73%，代表避險需求同步降溫，這波上漲不只是高波動下的短線回補。台積電 ADR 上漲 2.95%，為台灣半導體權值提供較直接的海外情緒參考。這些訊號支持風險偏好改善，但只能說明估值壓力暫時緩解，尚不足以證明終端需求或企業獲利已全面上修。

傳導到台股時，半導體、先進封裝、伺服器與電子權值會先反應海外晶片股走強；若大型電子帶動成交擴散，供應鏈相對表現才較可能延續。若買盤仍集中在少數權值，指數雖有支撐，電子次族群未必同步受惠。利率、美元與能源成本仍會影響遠期獲利比重較高族群的評價，因此海外科技走強不等於所有成長題材都會同幅重估。

價格已開始反映隔夜科技與半導體上漲，下一步要看開盤後的量能與類股廣度。若半導體轉弱、波動率回升，或台積電 ADR 的相對強勢消失，偏正面的盤前判讀應下修；若成交持續擴散且外部成本壓力沒有惡化，海外風險偏好才可能轉成較廣泛的台股支撐。盤前訊號只界定起點，不能取代開盤後確認。"""


def rows(cursor, sql, params=()):
    cursor.execute(sql, params)
    return [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and "pre_tw_open" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    try:
        assert not rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,))
        events = rows(cursor, "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)", tuple(FACTS))
        assert {event["id"] for event in events} == set(FACTS)
        for event in events:
            token, stamp = FACTS[event["id"]]
            assert token in event["summary"] and event["published_at"] == stamp

        structured = {
            "schema_version": "codex-market-analysis-v1",
            "confidence": "medium",
            "thesis": "晶片風險偏好回溫，但台股電子仍須等待成交廣度確認。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["半導體與先進封裝", "伺服器與電子權值", "電子次族群的成交擴散"],
            "invalidation": ["半導體轉弱或波動率回升", "台積電 ADR 強勢消失", "外部成本壓力重新轉緊"],
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
        stored_raw = json.loads(row["raw_json"])
        assert row["summary_text"] == SUMMARY and stored_raw == raw and json.loads(row["structured_json"]) == structured
        assert row["push_enabled"] == 1 and not row["pushed"] and signals == 0 and "stock_watch" not in row["structured_json"]
        print(json.dumps({
            "analysis_id": row_id, "claim_verifier_ok": stored_raw["claim_verifier"]["ok"],
            "claim_support_rate": stored_raw["claim_verifier"]["support_rate"], "trust_gate": stored_raw["trust_gate"],
            "push_enabled": bool(row["push_enabled"]), "pushed": bool(row["pushed"]),
            "structured_json_present": bool(json.loads(row["structured_json"])),
            "garbled_text": style_check(row["summary_text"])["garbled_text"], "style_checks": style_check(row["summary_text"]),
            "external_provider_api_called": stored_raw["external_provider_api_called"], "trade_signal_count": signals,
        }, ensure_ascii=False))
    finally:
        cursor.close()


if __name__ == "__main__":
    main()
