from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-08-26"
SLOT = "pre_tw_open"
AUTOMATION_ID = "market-analysis-codex-guard-pre-open"
EVENT_IDS = [763002, 763296, 764608, 764609, 764629]

SUMMARY = """市場現在交易的不是單純的科技股反彈，而是半導體動能能否抵銷高利率、貿易摩擦與終端需求轉弱。台股盤前基調偏向大型電子權值提供支撐，但不宜把這種支撐解讀成所有出口族群都能同步擴張評價；最大的未知數，是北美關稅升級會不會進一步改變訂單、庫存與毛利。

## 科技動能遇上高資金成本

那斯達克一百指數上漲約百分之零點六，費城半導體指數漲幅約百分之一點四，半導體明顯強於大型科技指數。這使台灣的晶圓代工、先進封裝、伺服器與散熱供應鏈在開盤前仍有正向傳導，尤其大型權值可望穩住指數；不過美國十年期公債殖利率仍在百分之四點六四附近，高評價題材仍需靠訂單與獲利兌現，不能只靠風險偏好延伸。

另一條線索來自實體需求與成本。加拿大宣布對美國商品採取等額報復性關稅，部分措施涵蓋鋼鐵與家具等品項；同一時段，美國運動用品零售商也警告服飾與鞋類需求轉弱。兩者放在一起看，市場尚未充分定價的不是關稅新聞本身，而是品牌商能否轉嫁成本，以及供應商是否會被要求讓利。台灣金屬、機械與北美零組件可能出現轉單機會，紡織、製鞋及消費電子則更需要留意需求與毛利同時受壓，產業內部分化會比指數方向更重要。

目前價格已部分反映半導體相對強勢，仍可能重新定價的是長債殖利率、關稅範圍與企業財測。如果科技與半導體後續無法延續強勢，或長債殖利率再度上行並伴隨企業下修毛利，偏多但分化的基調就應降級；反過來，若關稅沒有擴大、零售需求警訊未擴散，而且企業訂單與財測維持韌性，台股風險偏好才有機會從權值支撐擴散到更廣的電子與景氣循環族群。"""


def json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def main() -> None:
    now_local = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now_local)
    if now_local.date().isoformat() != ANALYSIS_DATE or SLOT not in allowed_analysis_slots(calendar):
        raise RuntimeError(f"calendar does not allow {ANALYSIS_DATE} {SLOT}")
    store = MySqlEventStore(load_settings(".env"))
    store.initialize()
    cursor = store._cursor()
    try:
        placeholders = ",".join(["%s"] * len(EVENT_IDS))
        cursor.execute(
            f"SELECT id,event_id,source,title,summary,published_at,created_at,raw_json FROM t_relay_events WHERE id IN ({placeholders}) ORDER BY id",
            tuple(EVENT_IDS),
        )
        columns = ["id", "event_id", "source", "title", "summary", "published_at", "created_at", "raw_json"]
        events = json_safe([dict(zip(columns, row)) for row in cursor.fetchall()])
    finally:
        cursor.close()
    if len(events) != len(EVENT_IDS):
        raise RuntimeError("required local evidence rows are missing")

    structured = {
        "schema_version": "codex-market-analysis-v1",
        "headline": "半導體偏強，但高利率與關稅放大產業分化",
        "thesis": "台股偏向大型電子權值支撐，廣度能否擴散取決於利率、關稅與終端需求。",
        "sentiment": "cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "technology_and_semiconductor_momentum", "event_ids": [764608, 764609]},
            {"role": "long_rate_constraint", "event_id": 764629},
            {"role": "north_america_tariff_escalation", "event_id": 763002},
            {"role": "consumer_demand_warning", "event_id": 763296},
        ],
        "tw_sector_transmission": [
            {"sector": "晶圓代工、先進封裝、伺服器與散熱", "mechanism": "半導體相對強勢支撐大型電子權值"},
            {"sector": "金屬、機械與北美零組件", "mechanism": "關稅可能同時帶來轉單與成本壓力"},
            {"sector": "紡織、製鞋與消費電子", "mechanism": "終端需求轉弱提高讓利與毛利壓力"},
        ],
        "invalidation": [
            "科技與半導體無法延續強勢",
            "長債殖利率再度上行且企業下修毛利",
            "關稅範圍擴大或零售需求警訊擴散",
        ],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY,
        structured_payload=structured,
        events_payload=events,
        market_payload=[],
    )
    forbidden = [
        "今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導",
        "先看區間邊界", "現在只看", "今日主命題", "三個證據", "市場正在定價什麼",
        "台股配置", "今日個股觀察", "stock_watch", "入場", "停損", "止損", "目標價",
        "t_relay_events", "t_market_analyses", "claim_verifier", "market_context", "raw_json",
    ]
    found_forbidden = [term for term in forbidden if term in SUMMARY]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", SUMMARY))
    style_checks = {
        "ok": not found_forbidden and not garbled,
        "template": "flexible-briefing-memo-v1",
        "garbled_text": garbled,
        "forbidden_terms": found_forbidden,
        "fixed_section_template": False,
    }
    if not verifier["ok"] or not style_checks["ok"]:
        raise RuntimeError(json.dumps({"claim_verifier": verifier, "style_checks": style_checks}, ensure_ascii=False))

    raw = {
        "automation_id": AUTOMATION_ID,
        "generator": "codex_automation",
        "display_title": ANALYSIS_DATE,
        "calendar": calendar.to_dict(),
        "evidence_event_ids": EVENT_IDS,
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style_checks,
        "external_provider_api_called": False,
    }
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=ANALYSIS_DATE,
        analysis_slot=SLOT,
        scheduled_time_local="07:30",
        model="codex-local-judgment",
        prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY,
        events_used=len(events),
        market_rows_used=3,
        push_enabled=True,
        pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False),
        structured_json=json.dumps(structured, ensure_ascii=False),
    ))
    verify_cursor = store._cursor()
    try:
        verify_cursor.execute(
            "SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s",
            (ANALYSIS_DATE, SLOT),
        )
        stored = verify_cursor.fetchone()
        verify_cursor.execute("SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s", (row_id,))
        signal_count = int(verify_cursor.fetchone()[0])
    finally:
        verify_cursor.close()
    if not stored:
        raise RuntimeError("analysis row missing after upsert")
    stored_raw = json.loads(stored[4])
    stored_structured = json.loads(stored[5])
    stored_summary = str(stored[3])
    checks = {
        "analysis_id": int(stored[0]),
        "claim_verifier_ok": stored_raw.get("claim_verifier", {}).get("ok") is True,
        "claim_support_rate": stored_raw.get("claim_verifier", {}).get("support_rate"),
        "trust_gate_ok": stored_raw.get("trust_gate", {}).get("ok") is True,
        "trust_gate_reason": stored_raw.get("trust_gate", {}).get("reason"),
        "push_enabled": bool(stored[1]),
        "pushed": bool(stored[2]),
        "structured_json_present": bool(stored_structured),
        "stock_watch_present": "stock_watch" in stored_structured,
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", stored_summary)),
        "style_ok": stored_raw.get("style_checks", {}).get("ok") is True,
        "fixed_section_template": stored_raw.get("style_checks", {}).get("fixed_section_template"),
        "external_provider_api_called": stored_raw.get("external_provider_api_called"),
        "trade_signal_count": signal_count,
    }
    if not all([
        checks["claim_verifier_ok"], checks["trust_gate_ok"], checks["push_enabled"],
        not checks["pushed"], checks["structured_json_present"], not checks["stock_watch_present"],
        not checks["garbled_text"], checks["style_ok"], checks["fixed_section_template"] is False,
        checks["external_provider_api_called"] is False, checks["trade_signal_count"] == 0,
    ]):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
