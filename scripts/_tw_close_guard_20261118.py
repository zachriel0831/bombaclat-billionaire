"""Store the 2026-11-18 Taiwan-close memo from local evidence only."""
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


DAY = "2026-11-18"
EVENT_IDS = [1038262, 1038254, 1038253, 1038252, 1038250]
SUMMARY = """今天收盤能確認的是，盤後資料不足以支持「台股已全面轉強或轉弱」的結論。收盤相關資料已彙整 15 筆事件，涵蓋借券、外資持股、產業別持股、融資與三大法人交易；但加權指數、成交廣度與法人合計淨額仍沒有可用結果。這否定了用單一盤後資料替整體市場定方向的做法，今天較合理的判讀是先保留盤勢的廣度與資金流向是否同步的問題。

資料的訊號主要在結構而非方向。借券可用量的收盤資料涵蓋上市與櫃買市場，外資持股資料同時提供前二十大與產業別切面，顯示盤後追蹤的範圍完整；然而三大法人交易只有資料列存在，未附可供判讀的合計買賣超。融資資料的欄位文字亦不適合作為可讀結論。換言之，目前能看見資金與持股的觀察面向，卻不能把它們轉化為大盤需求已改善或惡化的證據。

這種不確定性對台股的傳導是，電子權值、先進製程、伺服器與半導體設備仍會受到海外科技風險偏好、匯率與利率的影響，但今日收盤資料無法確認壓力是否已擴散到非電子類股，或是否已有廣泛承接。市場已知的是盤後資料已到位；仍待重新定價的是成交參與和法人合計流向是否支持新的趨勢。若後續加權指數、廣度與法人合計同向改善，才有理由提高對盤勢擴散的信心；若三者背離，今天保留方向判斷的結論就不應被推翻。"""


def style_check(text: str) -> dict:
    forbidden = [
        "今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導",
        "先看區間邊界", "現在只看", "今日主命題", "三個證據", "市場正在定價什麼",
        "台股配置", "今日個股觀察", "stock_watch", "推薦", "候選", "入場", "停損",
        "止損", "目標價", "t_relay_events", "t_market_analyses", "market_context",
        "raw_json", "structured_json", "claim_verifier", "Codex guard", "LLM API",
    ]
    forbidden_terms = [term for term in forbidden if term in text]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢\ue397\uef94]", text))
    english_heading = bool(re.search(r"(?m)^#{1,6}\s+[A-Za-z]", text))
    return {
        "ok": not forbidden_terms and not garbled and not english_heading,
        "template": "flexible-briefing-memo-v1",
        "forbidden_terms": forbidden_terms,
        "garbled_text": garbled,
        "english_section_headings": english_heading,
        "fixed_section_template": False,
    }


def rows(cursor, sql: str, params: tuple) -> list[dict]:
    cursor.execute(sql, params)
    return [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]


def main() -> None:
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and "tw_close" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    try:
        existing = rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (DAY, "tw_close"))
        assert not existing, "target row already exists; inspect before replacing it"
        events = rows(cursor, "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s,%s)", tuple(EVENT_IDS))
        assert {event["id"] for event in events} == set(EVENT_IDS)
        structured = {
            "schema_version": "codex-market-analysis-v1",
            "confidence": "limited",
            "thesis": "收盤資料覆蓋完整但缺乏可用大盤與法人合計數據，不能確認台股整體方向。",
            "evidence_event_ids": EVENT_IDS,
            "tw_sector_transmission": ["電子權值與先進製程", "伺服器與半導體設備", "非電子類股的成交參與"],
            "invalidation": ["加權指數、成交廣度與法人合計流向同向改善", "三項指標背離"],
            "data_gaps": ["final_taiwan_index", "closing_breadth", "institutional_net_flow_aggregate"],
        }
        verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
        style = style_check(SUMMARY)
        assert verifier["ok"] and style["ok"], json.dumps({"verifier": verifier, "style": style}, ensure_ascii=False)
        raw = {
            "automation_id": "market-analysis-codex-guard-tw-close", "generator": "codex_automation",
            "display_title": DAY, "calendar": calendar.to_dict(), "dimension": "daily_tw_close",
            "evidence_event_ids": EVENT_IDS, "claim_verifier": verifier,
            "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
            "style_checks": style, "external_provider_api_called": False, "generated_at": now.isoformat(),
            "evidence_quality": "limited_local_close_confirmation",
        }
        if "--write" not in sys.argv:
            print(json.dumps({"dry_run": True, "claim_verifier": verifier, "style_checks": style, "push_enabled": False}, ensure_ascii=False))
            return
        row_id = store.upsert_market_analysis(MarketAnalysisRecord(
            analysis_date=DAY, analysis_slot="tw_close", scheduled_time_local="15:30", model="codex-local-judgment",
            prompt_version="codex-flexible-briefing-memo-v1", summary_text=SUMMARY, events_used=len(events),
            market_rows_used=0, push_enabled=False, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False),
            structured_json=json.dumps(structured, ensure_ascii=False),
        ))
        row = rows(cursor, "SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s", (row_id,))[0]
        signals = rows(cursor, "SELECT COUNT(*) AS count FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["count"]
        stored_raw, stored_structured = json.loads(row["raw_json"]), json.loads(row["structured_json"])
        final_style = style_check(row["summary_text"])
        verified = verify_claim_coverage(summary_text=row["summary_text"], structured_payload=stored_structured, events_payload=events, market_payload=[])
        checks = {
            "analysis_id": row_id, "claim_verifier_ok": verified["ok"], "claim_support_rate": verified["support_rate"],
            "trust_gate": stored_raw["trust_gate"], "push_enabled": bool(row["push_enabled"]), "pushed": bool(row["pushed"]),
            "structured_json_present": bool(row["structured_json"]), "garbled_text": final_style["garbled_text"],
            "style_checks": final_style, "external_provider_api_called": stored_raw["external_provider_api_called"],
            "stock_watch_present": "stock_watch" in stored_structured, "trade_signal_count": signals,
        }
        assert row["summary_text"] == SUMMARY and verified["ok"] and final_style["ok"]
        assert stored_raw["trust_gate"]["ok"] and not row["push_enabled"] and not row["pushed"]
        assert stored_raw["external_provider_api_called"] is False and not checks["stock_watch_present"] and signals == 0
        print(json.dumps(checks, ensure_ascii=False))
    finally:
        cursor.close()


if __name__ == "__main__":
    main()
