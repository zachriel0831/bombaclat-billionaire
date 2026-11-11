"""Store the 2026-11-11 Taiwan-close memo from local evidence only."""
import json
import re
from datetime import datetime, timedelta, timezone

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


DAY = "2026-11-11"
EVENT_IDS = [1037563, 1037475, 1037476, 1037481]
SUMMARY = """今天收盤確認的不是台股全面走向，而是海外科技壓力已傳進估值：那斯達克 100 下跌 0.60%、費城半導體指數下跌 0.35%，使電子權值的風險偏好維持偏謹慎；但 TSM ADR 仍上漲 2.02%，顯示先進製程與 AI 供應鏈的基本面敘事尚未被一併否定。

這組分歧的意義在於，市場正在把「整體科技去風險」與「核心製造能力仍具韌性」分開定價。海外大盤與半導體指數走弱，會先壓抑台灣電子權值、伺服器、封裝與高評價零組件的本益比；TSM ADR 的相對強勢則讓賣壓不必然擴大成對整條供應鏈需求的重估。今天可讀的本地收盤資料已完成借券、外資持股、融資與法人交易資料的彙整，但沒有足以確認指數、廣度或法人合計方向的可用數字，因此不能把海外訊號直接等同於台股收盤結論。

目前已被反映的是科技類資產對風險折價的敏感度；還可能重估的，是海外指數續弱時台灣電子內部能否維持相對抗跌，以及資金是否擴散至非電子族群。若費城半導體指數與 TSM ADR 同步轉弱，這個「核心韌性」判斷就要降級；反之，若後續本地廣度與法人合計流向改善，市場才有理由從防守式分歧轉向更廣泛的風險承擔。"""


def check_text(text: str) -> dict:
    forbidden = [
        "今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導",
        "先看區間邊界", "現在只看", "今日主命題", "三個證據", "市場正在定價什麼",
        "台股配置", "今日個股觀察", "stock_watch", "推薦", "候選", "入場", "停損",
        "止損", "目標價", "t_relay_events", "raw_json", "structured_json", "Codex guard", "LLM API",
    ]
    bad = [term for term in forbidden if term in text]
    return {
        "ok": not bad and not re.search(r"\?{3,}|\ufffd|[銝脣蝢\ue397\uef94]", text) and not re.search(r"(?m)^#{1,6}\s+[A-Za-z]", text),
        "template": "flexible-briefing-memo-v1", "forbidden_terms": bad,
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢\ue397\uef94]", text)),
        "english_section_headings": bool(re.search(r"(?m)^#{1,6}\s+[A-Za-z]", text)), "fixed_section_template": False,
    }


def rows(cursor, sql: str, params: tuple) -> list[dict]:
    cursor.execute(sql, params)
    return [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]


def main() -> None:
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DAY and "tw_close" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env")); cursor = store._cursor()
    assert not rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (DAY, "tw_close"))
    events = rows(cursor, "SELECT id, source, title, summary, published_at, raw_json AS raw FROM t_relay_events WHERE id IN (%s,%s,%s,%s)", tuple(EVENT_IDS))
    assert {event["id"] for event in events} == set(EVENT_IDS)
    structured = {
        "schema_version": "codex-market-analysis-v1", "confidence": "limited",
        "thesis": "海外科技壓力存在，但先進製程與 AI 供應鏈韌性未被一併否定。",
        "evidence_event_ids": EVENT_IDS,
        "tw_sector_transmission": ["電子權值、伺服器、封裝與高評價零組件的估值壓力", "先進製程與 AI 供應鏈的相對韌性"],
        "invalidation": ["費城半導體指數與 TSM ADR 同步轉弱", "本地廣度與法人合計流向改善"],
        "data_gaps": ["final_taiwan_index", "closing_breadth", "institutional_net_flow_aggregate"],
    }
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = check_text(SUMMARY)
    assert verifier["ok"] and style["ok"], (verifier, style)
    raw = {"automation_id": "market-analysis-codex-guard-tw-close", "generator": "codex_automation", "display_title": DAY,
           "calendar": calendar.to_dict(), "dimension": "daily_tw_close", "evidence_event_ids": EVENT_IDS,
           "claim_verifier": verifier, "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
           "style_checks": style, "external_provider_api_called": False, "generated_at": now.isoformat(), "evidence_quality": "limited_local_close_confirmation"}
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=DAY, analysis_slot="tw_close", scheduled_time_local="15:30", model="codex-local-judgment",
        prompt_version="codex-flexible-briefing-memo-v1", summary_text=SUMMARY, events_used=len(events), market_rows_used=0,
        push_enabled=False, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    row = rows(cursor, "SELECT summary_text, raw_json, structured_json, push_enabled, pushed FROM t_market_analyses WHERE id=%s", (row_id,))[0]
    stored_raw, stored_structured = json.loads(row["raw_json"]), json.loads(row["structured_json"])
    verified = verify_claim_coverage(summary_text=row["summary_text"], structured_payload=stored_structured, events_payload=events, market_payload=[])
    signals = rows(cursor, "SELECT COUNT(*) AS count FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["count"]
    checks = {"analysis_id": row_id, "claim_verifier": verified, "trust_gate": stored_raw["trust_gate"], "push_enabled": bool(row["push_enabled"]),
              "pushed": bool(row["pushed"]), "structured_json_present": bool(row["structured_json"]), "style_checks": check_text(row["summary_text"]),
              "external_provider_api_called": stored_raw["external_provider_api_called"], "stock_watch_present": "stock_watch" in stored_structured, "trade_signal_count": signals}
    assert row["summary_text"] == SUMMARY and verified["ok"] and checks["style_checks"]["ok"]
    assert stored_raw["trust_gate"]["ok"] and not row["push_enabled"] and not row["pushed"]
    assert stored_raw["external_provider_api_called"] is False and not checks["stock_watch_present"] and signals == 0
    cursor.close(); print(json.dumps(checks, ensure_ascii=False))


if __name__ == "__main__":
    main()
