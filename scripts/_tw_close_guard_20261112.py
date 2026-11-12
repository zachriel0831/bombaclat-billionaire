"""Store the 2026-11-12 Taiwan-close memo from local evidence only."""
import json
import re
from datetime import datetime, timedelta, timezone

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


DAY = "2026-11-12"
EVENT_IDS = [1037663, 1037575, 1037576, 1037581, 1037577]
SUMMARY = """今天收盤可確認的是外部科技風險偏好明顯回暖，但不能因此宣告台股已全面轉強。那斯達克 100 上漲 2.28%、費城半導體指數上漲 5.66%，TSM ADR 上漲 4.25%，且 VIX 下跌 10.12%；這組合支持半導體與 AI 供應鏈的評價壓力暫時緩解，也否定了前一日那種全面去風險的延續判斷。

背後的機制是，美國科技指數、半導體指數與關鍵晶圓代工 ADR 同步走強時，市場通常先下修對成長資產的風險折價，台灣電子權值、先進製程、伺服器與封裝供應鏈因而受惠；波動率回落則降低資金避險需求，讓資金更可能回到高本益比族群。今天本地資料已完成借券、外資持股、融資與法人交易的收盤彙整，但沒有可用的加權指數、廣度或法人合計數字，因此上述只能確認估值環境改善，不能替台股整體收盤表現下定論。

市場已先反映一部分科技風險溢酬回落，接下來仍會重估這波上行能否由半導體擴散到更廣的電子供應鏈。若費城半導體指數與 TSM ADR 轉為同步走弱，或 VIX 回升，今日的風險偏好改善就應視為短暫反彈；反之，若後續本地廣度與法人合計流向也轉佳，才足以把外部訊號升格為較廣泛的台股確認。"""


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
    events = rows(cursor, "SELECT id, source, title, summary, published_at, raw_json AS raw FROM t_relay_events WHERE id IN (%s,%s,%s,%s,%s)", tuple(EVENT_IDS))
    assert {event["id"] for event in events} == set(EVENT_IDS)
    structured = {
        "schema_version": "codex-market-analysis-v1", "confidence": "limited",
        "thesis": "外部科技風險偏好回暖，支撐台灣電子估值，但尚不足以確認整體台股走勢。",
        "evidence_event_ids": EVENT_IDS,
        "tw_sector_transmission": ["電子權值、先進製程、伺服器與封裝供應鏈的風險折價暫時緩解", "高評價電子族群對波動率回落較敏感"],
        "invalidation": ["費城半導體指數與 TSM ADR 同步轉弱", "VIX 回升", "本地廣度與法人合計流向未改善"],
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
