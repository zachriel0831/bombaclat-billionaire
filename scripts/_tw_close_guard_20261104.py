"""Store the 2026-11-04 Taiwan-close memo from local evidence only."""
import json
import re
from datetime import datetime, timedelta, timezone

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


DAY = "2026-11-04"
EVENT_IDS = [1036863, 1036778, 1036783, 1036779]
SUMMARY = """今天台股收盤確認的，是海外半導體回穩能支撐電子評價討論，卻還不足以替本地盤勢下結論。費城半導體指數上漲 2.63%、TSM ADR 上漲 1.55%，VIX 回落 1.51%，代表全球科技風險溢酬暫時降溫；但本地收盤階段彙整的主要是融資、外資持股與借券結構，法人買賣超彙總沒有可用數值，終盤指數與市場廣度也沒有完整交叉確認。因此，不能把海外回穩直接解讀為台股收盤全面轉強。

這條傳導先落在電子權值、先進製程、封裝與伺服器供應鏈：海外晶片鏈若維持回穩，市場對需求與評價的壓力會緩和；若只是短暫反彈，資金仍會要求更多本地量價與法人動向來確認。金融及防禦型類股也不會因科技氣氛好轉就必然轉弱，利率與資金流仍各自決定其表現。

目前已反映的是海外科技風險降溫，尚未完全反映的是台股內部是否出現足夠廣度與資金支持。若海外半導體續強，且本地後續資料顯示廣度改善、法人方向轉為支持，偏保守的判斷就應降級；反之，若晶片鏈再度轉弱或波動率回升，今天的回穩訊號便不足以支撐更高評價。"""


def check_text(text: str) -> dict:
    forbidden = [
        "今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導",
        "先看區間邊界", "現在只看", "今日主命題", "三個證據", "市場正在定價什麼",
        "台股配置", "今日個股觀察", "stock_watch", "推薦", "候選", "入場", "停損",
        "止損", "目標價", "t_relay_events", "raw_json",
    ]
    bad = [term for term in forbidden if term in text]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢\ue397\uef94]", text))
    english_heading = bool(re.search(r"(?m)^#{1,6}\s+[A-Za-z]", text))
    return {"ok": not bad and not garbled and not english_heading, "template": "flexible-briefing-memo-v1", "forbidden_terms": bad, "garbled_text": garbled, "english_section_headings": english_heading, "fixed_section_template": False}


def fetch_rows(cursor, sql: str, params: tuple) -> list[dict]:
    cursor.execute(sql, params)
    return [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]


def main() -> None:
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DAY and "tw_close" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    assert not fetch_rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (DAY, "tw_close"))
    events = fetch_rows(cursor, "SELECT id, source, title, summary, published_at, raw_json AS raw FROM t_relay_events WHERE id IN (%s,%s,%s,%s)", tuple(EVENT_IDS))
    assert {event["id"] for event in events} == set(EVENT_IDS)
    structured = {
        "schema_version": "codex-market-analysis-v1", "confidence": "low",
        "thesis": "海外半導體回穩，但本地完整收盤確認不足，不能把它當作台股全面轉強。",
        "evidence_event_ids": EVENT_IDS,
        "tw_sector_transmission": ["電子權值、先進製程、封裝與伺服器供應鏈的評價壓力暫時緩和", "金融及防禦型類股仍分別受利率與資金流影響"],
        "invalidation": ["海外半導體續強且本地廣度改善、法人方向支持", "晶片鏈轉弱或波動率回升"],
        "data_gaps": ["final_taiwan_index", "closing_breadth", "institutional_net_flow_aggregate"],
    }
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = check_text(SUMMARY)
    assert verifier["ok"] and style["ok"], (verifier, style)
    raw = {
        "automation_id": "market-analysis-codex-guard-tw-close", "generator": "codex_automation", "display_title": DAY,
        "calendar": calendar.to_dict(), "dimension": "daily_tw_close", "evidence_event_ids": EVENT_IDS,
        "claim_verifier": verifier, "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style, "external_provider_api_called": False, "generated_at": now.isoformat(),
        "close_confirmation": "overseas_semiconductor_recovery_not_fully_confirmed_by_taiwan_close", "evidence_quality": "limited_evidence",
    }
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=DAY, analysis_slot="tw_close", scheduled_time_local="15:30", model="codex-local-judgment",
        prompt_version="codex-flexible-briefing-memo-v1", summary_text=SUMMARY, events_used=len(events), market_rows_used=0,
        push_enabled=False, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False),
    ))
    row = fetch_rows(cursor, "SELECT summary_text, raw_json, structured_json, push_enabled, pushed FROM t_market_analyses WHERE id=%s", (row_id,))[0]
    stored_raw, stored_structured = json.loads(row["raw_json"]), json.loads(row["structured_json"])
    verified = verify_claim_coverage(summary_text=row["summary_text"], structured_payload=stored_structured, events_payload=events, market_payload=[])
    signal_count = fetch_rows(cursor, "SELECT COUNT(*) AS count FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["count"]
    checks = {"analysis_id": row_id, "claim_verifier": verified, "trust_gate": stored_raw["trust_gate"], "push_enabled": bool(row["push_enabled"]), "pushed": bool(row["pushed"]), "structured_json_present": bool(row["structured_json"]), "style_checks": check_text(row["summary_text"]), "external_provider_api_called": stored_raw["external_provider_api_called"], "stock_watch_present": "stock_watch" in stored_structured, "trade_signal_count": signal_count}
    assert row["summary_text"] == SUMMARY and verified["ok"] and checks["style_checks"]["ok"]
    assert stored_raw["trust_gate"]["ok"] and not row["push_enabled"] and not row["pushed"]
    assert stored_raw["external_provider_api_called"] is False and not checks["stock_watch_present"] and signal_count == 0
    cursor.close()
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == "__main__":
    main()
