"""Store the 2026-10-21 Codex pre-open memo from readable local facts."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _us_close_guard_20260917 import (
    MySqlEventStore,
    MarketAnalysisRecord,
    allowed_analysis_slots,
    load_settings,
    resolve_market_calendar_state,
    style_check,
    verify_claim_coverage,
)


DAY = "2026-10-21"
FACTS = {
    1035411: ("change_percent=-0.13%", "2026-10-20T21:15:59+00:00"),
    1035412: ("change_percent=-0.29%", "2026-10-20T21:15:59+00:00"),
    1035413: ("change_percent=-6.13%", "2026-10-20T20:15:01+00:00"),
    1035417: ("change_percent=+1.16%", "2026-10-20T20:00:03+00:00"),
}
SUMMARY = """開盤前，市場交易的是科技權值能否在利率與能源成本仍有壓力時維持相對韌性，而不是單一指數的漲跌。台股基調先採中性偏審慎：海外科技指數略回落，但恐慌指標同步下降，較像高檔整理而非全面撤出風險資產。最大不確定性是這種分歧能否在台灣開盤後擴散成電子族群的實際承接，或仍只停留在少數大型權值股。

昨晚那斯達克百大下跌 0.13%，費城半導體指數下跌 0.29%，兩者都沒有提供電子族群立即擴張的價格訊號；不過波動率指數下降 6.13%，顯示市場對短線風險的要求沒有同步升高。台積電 ADR 上漲 1.16%，也讓半導體供應鏈的開盤情緒不必直接等同於海外指數的小幅回落。這四項事實合在一起，較合理的解讀是市場正在重新排序權值、獲利能見度與估值，而非已經形成單一路徑的風險趨避。

對台股而言，傳導會先集中在半導體、伺服器與電子權值。若海外大型科技的相對強勢由訂單、資本支出與毛利率承接，台灣的先進製程、封裝、零組件與設備需求可維持韌性；但若資金只停留在少數龍頭，指數表現可能與多數電子次族群脫鉤。能源與利率仍是另一端的限制：兩者若續升，遠期獲利占比較高的電子產業會先面對評價折現壓力，運輸及耗能製造也會承受成本疑慮。

目前價格已反映部分科技高檔整理，尚未完全反映的是台灣開盤後的成交擴散與海外資金是否願意承接非權值電子。若半導體跌勢擴大、波動率重新上行，且台積電 ADR 的相對強勢消失，中性判斷應轉弱；若電子成交範圍擴大，同時利率與能源壓力沒有惡化，海外權值韌性才有機會轉成較廣泛的台股支撐。盤前訊號只能界定起點，不能取代開盤後的量能與類股確認。"""


def rows(cursor, sql, params=()):
    cursor.execute(sql, params)
    return [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and "pre_tw_open" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    assert not rows(
        cursor,
        "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'",
        (DAY,),
    ), "Existing row requires separate review"
    events = rows(
        cursor,
        "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)",
        tuple(FACTS),
    )
    assert {event["id"] for event in events} == set(FACTS)
    for event in events:
        token, stamp = FACTS[event["id"]]
        assert token in event["summary"] and event["published_at"] == stamp

    structured = {
        "schema_version": "codex-market-analysis-v1",
        "confidence": "medium",
        "thesis": "科技權值相對韌性仍在，但台股電子須等待開盤後的成交擴散確認。",
        "evidence_event_ids": list(FACTS),
        "tw_sector_transmission": ["半導體與伺服器供應鏈", "電子權值與非權值擴散", "運輸及耗能製造成本"],
        "invalidation": ["半導體跌勢擴大、波動率重新上行", "電子成交擴散且利率與能源壓力未惡化"],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY,
        structured_payload=structured,
        events_payload=events,
        market_payload=[],
    )
    style = style_check(SUMMARY)
    assert verifier["ok"] and style["ok"], (verifier, style)
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
        "evidence_limits": ["Garbled aggregate context excluded", "Taiwan opening flows unconfirmed"],
    }
    print(json.dumps({"dry_run": "--apply" not in sys.argv, "characters": len(SUMMARY), "verifier": verifier, "style": style}, ensure_ascii=False))
    if "--apply" not in sys.argv:
        return

    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=DAY,
        analysis_slot="pre_tw_open",
        scheduled_time_local="07:30",
        model="codex-local-judgment",
        prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY,
        events_used=len(events),
        market_rows_used=0,
        push_enabled=True,
        pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False),
        structured_json=json.dumps(structured, ensure_ascii=False),
    ))
    row = rows(cursor, "SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s", (row_id,))[0]
    signals = rows(cursor, "SELECT COUNT(*) AS n FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["n"]
    assert row["summary_text"] == SUMMARY and json.loads(row["raw_json"]) == raw
    assert json.loads(row["structured_json"]) == structured and row["push_enabled"] == 1 and not row["pushed"]
    assert signals == 0 and "stock_watch" not in row["structured_json"]
    print(json.dumps({"analysis_id": row_id, "claim_verifier_ok": verifier["ok"], "trust_gate": raw["trust_gate"], "push_enabled": True, "pushed": False, "structured_json_present": True, "style_checks": style_check(row["summary_text"]), "external_provider_api_called": False, "trade_signal_count": signals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
