"""Store the 2026-11-03 Taiwan-close memo from local evidence only."""
import json
import re
from datetime import datetime, timedelta, timezone

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


DAY = "2026-11-03"
EVENT_IDS = [1036765, 1036678, 1036683, 1036679]
SUMMARY = """今天台股收盤確認的不是一個明確方向，而是外部風險傳導比本地收盤訊號更完整。美國半導體指數與 TSM ADR 走弱、波動率上升，讓台灣電子權值與供應鏈的評價壓力仍在；但本地終盤指數、成交廣度與可用的法人買賣超明細沒有形成完整交叉驗證，因此不能把海外回檔直接翻成今天台股全面轉弱。

海外晶片鏈的疲弱意味著市場正在重新檢查高估值科技股能否持續承接需求與獲利預期。這會先傳到大型電子權值、先進製程、封裝及伺服器供應鏈；若下游接單與終端需求沒有同步轉弱，價格壓力未必會立刻變成獲利壓力。波動率走高則提高短線風險溢酬，資金較可能先要求更清楚的基本面證據，再擴大對景氣循環族群的定價。

本地收盤資料已涵蓋融資與外資持股結構等項目，但現有材料不足以判定資金是否在今日收盤明確撤出或承接。這項限制不是把空白資料當成中性，而是避免讓盤前的海外價格取代台灣收盤本身。金融與高股息類股也不能只因科技承壓就被視為必然受惠，仍要分開看利率、債券評價與實際資金流。

目前較合理的重估是：電子風險溢酬上升已開始影響台股的評價討論，但尚未被本地完整收盤證據確認。若後續顯示電子廣度改善、法人方向轉為支持，且海外半導體跌勢收斂，偏保守的判斷就應撤回；反之，若晶片鏈續弱並伴隨本地成交收縮或企業展望下修，壓力才可能由評價延伸到獲利。"""


def check_text(text: str) -> dict:
    forbidden = ["今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導", "先看區間邊界", "現在只看", "今日主命題", "三個證據", "市場正在定價什麼", "台股配置", "今日個股觀察", "stock_watch", "推薦", "候選", "入場", "停損", "止損", "目標價", "t_relay_events", "raw_json"]
    bad = [term for term in forbidden if term in text]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢\ue397\uef94]", text))
    english_heading = bool(re.search(r"(?m)^#{1,6}\s+[A-Za-z]", text))
    return {"ok": not bad and not garbled and not english_heading, "template": "flexible-briefing-memo-v1", "forbidden_terms": bad, "garbled_text": garbled, "english_section_headings": english_heading, "fixed_section_template": False}


def fetch_rows(cursor, sql: str, params: tuple) -> list[dict]:
    cursor.execute(sql, params)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def main() -> None:
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DAY and "tw_close" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    assert not fetch_rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (DAY, "tw_close"))
    events = fetch_rows(cursor, "SELECT id, source, title, summary, published_at, raw_json AS raw FROM t_relay_events WHERE id IN (%s,%s,%s,%s)", tuple(EVENT_IDS))
    assert {event["id"] for event in events} == set(EVENT_IDS)
    structured = {"schema_version": "codex-market-analysis-v1", "confidence": "low", "thesis": "海外半導體風險升高，但本地收盤資料不足以確認台股方向。", "evidence_event_ids": EVENT_IDS, "tw_sector_transmission": ["海外晶片風險先傳到電子權值、先進製程、封裝與伺服器供應鏈評價", "波動率上升提高風險溢酬，金融與高股息仍須分開看利率與資金流"], "invalidation": ["電子廣度改善、法人方向支持且海外半導體跌勢收斂", "晶片鏈續弱且本地成交收縮或企業展望下修"], "data_gaps": ["final_taiwan_index", "closing_breadth", "institutional_net_flow_detail"]}
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = check_text(SUMMARY)
    assert verifier["ok"] and style["ok"], (verifier, style)
    raw = {"automation_id": "market-analysis-codex-guard-tw-close", "generator": "codex_automation", "display_title": DAY, "calendar": calendar.to_dict(), "dimension": "daily_tw_close", "evidence_event_ids": EVENT_IDS, "claim_verifier": verifier, "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"}, "style_checks": style, "external_provider_api_called": False, "generated_at": now.isoformat(), "close_confirmation": "unconfirmed_missing_complete_taiwan_close_data", "evidence_quality": "limited_evidence"}
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot="tw_close", scheduled_time_local="15:30", model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1", summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=False, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
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
