"""Persist the 2026-11-16 Codex pre-open memo from readable local facts."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _pre_tw_open_guard_20261113 import (
    MarketAnalysisRecord,
    MySqlEventStore,
    allowed_analysis_slots,
    load_settings,
    rows,
    resolve_market_calendar_state,
    style_check,
    verify_claim_coverage,
)


DAY = "2026-11-16"
FACTS = {
    1037978: ("change_percent=+0.00%", "2026-11-15T23:10:11+00:00"),
    1037979: ("change_percent=-0.29%", "2026-11-15T23:10:10+00:00"),
    1037980: ("change_percent=+0.09%", "2026-11-15T23:10:02+00:00"),
    1037999: ("value=4", "2026-11-15"),
}
SUMMARY = """今天盤前市場並沒有新的美股收盤可供消化，焦點轉為美元、能源與既有利率水位是否繼續限制風險承擔。台股的起始判讀為中性偏謹慎：電子與出口族群仍須面對匯率和資金成本的評價約束，最大不確定性則是開盤後的量能能否承接，而非單一隔夜指數的方向。

美元指數報 103.415、變動接近持平，表示匯率壓力尚未明顯鬆動；西德州原油報 88.3 美元、下跌 0.29%，短線雖略減成本焦慮，仍不足以改變能源對運輸、石化與耗能製造的影響。黃金期貨報 3889.9 美元、上升 0.09%，反映避險需求沒有完全退場；聯準會政策利率上限維持 4%，也使長天期成長題材對利率與美元的變動保持敏感。這些訊號共同描述的是盤前風險條件，而不是新的景氣結論。

傳導到台股時，先進製程、伺服器與其他電子權值的評價仍會受到美元和資金成本牽動；能源與運輸成本敏感的產業則較在意油價是否再度走高。若開盤後權值股能在正常量能下維持穩定，市場可能把週末的外部訊號視為背景約束，而非立即的賣壓來源；若量能萎縮且成本敏感族群同步轉弱，盤面的風險折價可能擴大。

目前已反映的是沒有新增美股收盤的資訊真空，仍可能重新定價的是匯率、油價與開盤後資金流向。若美元轉弱、油價回落且電子權值獲得量能支持，偏謹慎的判讀應下修；反之，若美元走強、油價回升而盤面承接不足，台股對成本與評價的敏感度可能提高。這是週末後的盤前框架，開盤表現仍是確認訊號。"""


def main() -> None:
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and "pre_tw_open" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    try:
        existing = rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (DAY, "pre_tw_open"))
        assert not existing
        events = rows(cursor, "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)", tuple(FACTS))
        assert {event["id"] for event in events} == set(FACTS)
        for event in events:
            token, published_at = FACTS[event["id"]]
            assert token in event["summary"] and event["published_at"] == published_at
        structured = {
            "schema_version": "codex-market-analysis-v1",
            "confidence": "low",
            "thesis": "缺少新增美股收盤時，台股盤前偏中性謹慎，應觀察美元、油價與開盤量能是否擴大成本及評價壓力。",
            "evidence_event_ids": list(FACTS),
            "tw_sector_transmission": ["電子權值、先進製程與伺服器的匯率及資金成本敏感度", "能源、運輸、石化與耗能製造的成本敏感度"],
            "invalidation": ["美元轉弱、油價回落且電子權值獲得量能支持", "美元走強、油價回升而盤面承接不足"],
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
            "evidence_limits": ["No new U.S. closing session was available before the Taiwan pre-open window"],
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
