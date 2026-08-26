from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-08-26"
SLOT = "tw_close"
AUTOMATION_ID = "market-analysis-codex-guard-tw-close"
EVENT_IDS = [764609, 764629, 767420, 767423]

SUMMARY = """今天的台股收盤確認了權值支撐已經擴大成現貨資金回流，也否定了早盤弱勢會直接演變成風險撤退。加權指數開低後翻紅，終場上漲663.16點、收在45,832.62點，成交值約8,042.49億元；三大法人同步買超593.87億元。價格、量能與法人方向同時改善，使這次上漲比單純拉抬權值更有廣度，但美國長債殖利率仍在4.64%附近，表示評價擴張尚未脫離高資金成本約束。

## 從翻紅到資金確認

盤中由44,925.84點低位回升，收盤靠近45,878.39點的日內高位，顯示買盤不是只守住平盤，而是願意在尾盤維持風險部位。成交值升至約8,042.5億元，並有法人買超配合，市場今天確認的是承接強度與資金方向，而不只是指數跌深反彈。這也讓前一晚費城半導體指數上漲1.44%的外部動能，實際傳到台灣大型電子與高價權值。

機制上，半導體與AI供應鏈仍是指數最直接的推力：台積電等大型權值走強，可同時改善大盤、電子族群與供應鏈風險偏好；成交與法人資金放大，則提高晶圓代工、先進封裝、伺服器、散熱及零組件之間擴散的可能。非電子族群能否跟進仍重要，因為金融、原物料與運輸對利率、美元和能源成本的敏感度不同，若上漲只停留在少數大型科技權值，指數強勢仍可能掩蓋產業分化。

目前價格已開始反映半導體相對強勢與法人回補，還沒有充分解決的是高長債殖利率對估值的壓力，以及企業訂單能否把題材轉成獲利。若後續成交與法人買盤延續、電子以外族群也同步轉強，而且長債殖利率沒有再上行，今天的收盤可視為風險偏好由權值支撐向市場廣度擴散；反之，若量能快速退回、法人重新轉賣，或利率上行使高評價科技先失去動能，這次確認就應降級為事件驅動的短期回補。"""


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
        "headline": "資金與權值同步回流，廣度開始改善",
        "thesis": "台股收盤確認法人與量能支持風險偏好回升，但高長債殖利率仍限制評價擴張。",
        "sentiment": "cautious_positive",
        "confidence": "medium_high",
        "evidence": [
            {"role": "taiwan_close_price_volume", "event_id": 767420},
            {"role": "taiwan_institutional_flow", "event_id": 767423},
            {"role": "semiconductor_momentum", "event_id": 764609},
            {"role": "long_rate_constraint", "event_id": 764629},
        ],
        "tw_sector_transmission": [
            {"sector": "晶圓代工、先進封裝、伺服器與零組件", "mechanism": "半導體動能、法人回流與量能放大提高風險偏好擴散機會"},
            {"sector": "金融、原物料與運輸", "mechanism": "利率、美元與能源成本決定非電子族群能否跟上"},
        ],
        "invalidation": [
            "成交與法人買盤無法延續",
            "電子以外族群未能同步轉強",
            "長債殖利率再度上行並壓抑高評價科技",
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
        "dimension": "daily_tw_close",
        "evidence_event_ids": EVENT_IDS,
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style_checks,
        "external_provider_api_called": False,
    }
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=ANALYSIS_DATE,
        analysis_slot=SLOT,
        scheduled_time_local="15:30",
        model="codex-local-judgment",
        prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY,
        events_used=len(events),
        market_rows_used=0,
        push_enabled=False,
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
        checks["claim_verifier_ok"], checks["trust_gate_ok"], not checks["push_enabled"],
        not checks["pushed"], checks["structured_json_present"], not checks["stock_watch_present"],
        not checks["garbled_text"], checks["style_ok"], checks["fixed_section_template"] is False,
        checks["external_provider_api_called"] is False, checks["trade_signal_count"] == 0,
    ]):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
