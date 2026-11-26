"""Store the 2026-11-26 Taiwan-close memo from local evidence only."""
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


DAY = "2026-11-26"
EVENT_IDS = [1039048, 1039039, 1039038, 1039037, 1039035]
SUMMARY = """今天收盤確認的是，盤後資料雖已補齊多個資金與持股切面，仍不足以證實台股資金已經沿產業或法人面向轉為一致方向。收盤資料彙整 15 筆事件，借券、外資持股與產業別持股均已到位；但加權指數、成交廣度與法人合計買賣超沒有可用的收盤結論，因此不宜把單一結構資料放大成大盤轉強或轉弱的判斷。

可讀證據顯示，借券可用量涵蓋上市與櫃買共 1,255 筆，外資前二十大持股與 36 個產業別持股也同步更新，代表盤後追蹤的範圍並不狹窄。相對地，三大法人交易只有一筆資料列，未提供可供比較的合計淨額。這使得市場能觀察籌碼與持股分布，卻無法確認今天的交易是否已形成廣泛承接或賣壓；缺少成交廣度時，任何單一族群的變化都還不足以代表整體盤勢。

對台股而言，海外科技情緒、匯率與利率仍會先透過電子權值、先進製程、伺服器與半導體設備傳導；若後續法人流向與成交參與同步改善，這些高權重類股較可能放大正向擴散。反之，若資金只停留在少數族群、且法人合計流向未跟上，盤面仍可能維持輪動而非趨勢。市場已經知道資料覆蓋增加，尚未完全定價的是資金是否真的擴散到更廣的類股。

接下來若加權指數、成交廣度與法人合計流向出現同向改善，今天保留方向的判讀就應提高信心；若三者持續背離，則不應把持股或借券的單一變化解讀為新趨勢。收盤資料的價值在於界定應追蹤的結構，而不是替尚未確認的方向下結論。"""


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
        placeholders = ",".join(["%s"] * len(EVENT_IDS))
        events = rows(cursor, f"SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN ({placeholders})", tuple(EVENT_IDS))
        assert {event["id"] for event in events} == set(EVENT_IDS)
        structured = {
            "schema_version": "codex-market-analysis-v1",
            "confidence": "limited",
            "thesis": "收盤資料覆蓋擴大但缺乏可用大盤、廣度與法人合計數據，不能確認台股整體方向。",
            "evidence_event_ids": EVENT_IDS,
            "tw_sector_transmission": ["電子權值與先進製程", "伺服器與半導體設備", "輪動中的非電子類股"],
            "invalidation": ["加權指數、成交廣度與法人合計流向同向改善", "三項指標持續背離"],
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
