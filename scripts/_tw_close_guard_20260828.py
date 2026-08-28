from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-08-28"
SLOT = "tw_close"
AUTOMATION_ID = "market-analysis-codex-guard-tw-close"
EVENT_IDS = [784233, 784513, 784790]

SUMMARY = """今天的台股收盤確認了美股科技財報帶來的 AI 風險偏好確實傳進台灣市場，也否定了早盤衝高只是短暫情緒的保守版本。加權指數終場上漲356.23點、收46,331.45點，成交金額約1.02兆元，三大法人買超468.17億元；價格、量能與法人方向一致，讓這次上漲比單靠權值股拉抬更有支撐。不過，指數未守住盤中46,574.52點，仍顯示高檔有人獲利了結，合理判斷是偏多承接獲得確認，而非風險已完全消失。

## 利多有落地，下一步看擴散

盤面主軸仍由大型電子帶動，台積電收漲10元，聯電等電子權值同步提供支撐。這說明市場願意把 AI 需求與財報能見度轉成台灣半導體評價，但接下來的關鍵已從「龍頭財報是否失速」轉向先進製程、封裝、伺服器、散熱與高速傳輸能否出現更廣泛的訂單與獲利改善。若只有少數權值維持強勢，指數仍可能上漲，產業內部卻會快速分化；若中游零組件與櫃買電子也延續量價，這波行情才更接近基本面擴散。

法人買盤與破兆成交是今天最有市場意義的第二條證據。它代表外部利多不是只停留在開盤定價，而是盤中仍有資金承接；同時，盤中高點未能守住，也提醒市場對高評價仍有價格敏感度。金融與內需族群因此較可能扮演穩定盤面的角色，真正決定指數彈性的仍是半導體權值與 AI 供應鏈的獲利兌現。

外部風險目前沒有消失。國際油價本週仍可能走低，但美伊緊張情勢持續，意味能源價格與通膨預期仍可能反覆；若油價重新上行並推升長端利率，高評價科技的折現壓力會再度升高，航運、塑化與用能產業也會出現不同方向的成本與報價影響。

目前價格已反映 AI 財報利多與法人回補，尚未完全反映的是獲利能否由權值股向供應鏈擴散。若後續成交維持、法人買盤延續，且指數能縮小盤中高點與收盤的落差，今天可視為新一輪風險偏好的有效確認；反之，若量能放大卻無法再創收盤高點、電子廣度轉弱，或油價與長端利率同步上升，這個偏多判斷就應降級為財報事件後的短期重估。"""


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
            f"SELECT id,event_id,source,title,summary,published_at,created_at,raw_json "
            f"FROM t_relay_events WHERE id IN ({placeholders}) ORDER BY id",
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
        "headline": "AI 利多獲收盤確認，高檔承接仍待擴散",
        "thesis": "台股以價量與法人買盤確認 AI 風險偏好，但盤中高點未守住，後續取決於獲利是否由權值向供應鏈擴散。",
        "sentiment": "constructive_cautious",
        "confidence": "medium_high",
        "evidence": [
            {"role": "taiwan_close_price_volume_flow", "event_id": 784790},
            {"role": "taiwan_close_electronics_leadership", "event_id": 784513},
            {"role": "oil_geopolitical_risk", "event_id": 784233},
        ],
        "tw_sector_transmission": [
            {"sector": "大型電子、半導體與 AI 供應鏈", "mechanism": "財報需求能見度先支撐權值，再由訂單與獲利廣度決定擴散"},
            {"sector": "金融與內需", "mechanism": "權值高檔換手時提供盤面穩定度"},
            {"sector": "航運、塑化與用能產業", "mechanism": "油價透過成本、報價與通膨利率預期形成分化"},
        ],
        "invalidation": [
            "量能放大但指數無法再創收盤高點",
            "電子族群廣度轉弱且法人買盤中斷",
            "油價與長端利率同步上升並壓抑科技評價",
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
        "台股配置", "今日個股觀察", "stock_watch", "買進", "推薦", "候選", "入場",
        "停損", "止損", "目標價", "t_relay_events", "t_market_analyses", "claim_verifier",
        "market_context", "raw_json",
    ]
    found_forbidden = [term for term in forbidden if term in SUMMARY]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", SUMMARY))
    style_checks = {
        "ok": not found_forbidden and not garbled,
        "template": "flexible-briefing-memo-v1",
        "garbled_text": garbled,
        "forbidden_terms": found_forbidden,
        "fixed_section_template": False,
        "english_section_headings": False,
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

    cursor = store._cursor()
    try:
        cursor.execute(
            "SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json FROM t_market_analyses "
            "WHERE analysis_date=%s AND analysis_slot=%s", (ANALYSIS_DATE, SLOT),
        )
        stored = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s", (row_id,))
        signal_count = int(cursor.fetchone()[0])
    finally:
        cursor.close()
    if not stored:
        raise RuntimeError("analysis row missing after upsert")
    stored_raw = json.loads(stored[4])
    stored_structured = json.loads(stored[5])
    checks = {
        "analysis_id": int(stored[0]),
        "claim_verifier_ok": stored_raw.get("claim_verifier", {}).get("ok") is True,
        "claim_support_rate": stored_raw.get("claim_verifier", {}).get("support_rate"),
        "trust_gate_ok": stored_raw.get("trust_gate", {}).get("ok") is True,
        "trust_gate_reason": stored_raw.get("trust_gate", {}).get("reason"),
        "push_enabled": bool(stored[1]), "pushed": bool(stored[2]),
        "structured_json_present": bool(stored_structured),
        "stock_watch_present": "stock_watch" in stored_structured,
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", str(stored[3]))),
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
