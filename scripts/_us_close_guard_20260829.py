from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-08-29"
SLOT = "us_close"
AUTOMATION_ID = "market-analysis-codex-guard-us-close"
EVENT_IDS = [788345, 789018, 789639, 789668, 789728]
MARKET_IDS = [353, 354, 355, 356]

SUMMARY = """這次美股收盤替台灣投資人改變的，是利率風險重新壓過單一財報驚喜：AI 需求仍有支撐，但只要通膨黏性讓資金成本上修，市場就不會再用同一套估值獎勵整條科技鏈。道瓊收在約五萬三千五百五十九點，標普五百收在約七千七百十一點，兩者都低於當日開盤附近，顯示盤面沒有把前一日的科技樂觀直接延伸成全面追價。對下週台股而言，基調仍偏正面，但更像資金與獲利品質的篩選，而不是普遍性的風險偏好上升。

## 利率重新成為估值的天花板

聯準會主席華許在全球央行年會表示，夏季通膨雖優於預期，基礎趨勢卻尚未實質改善，並強調升息仍是對抗通膨的核心工具。市場因此必須重新估算「高利率維持更久、甚至仍有升息風險」的情境；這會先拉高長久期成長股的折現率，也讓 AI 類股需要用更強的營收與毛利率證明高評價合理。

科技需求本身並未熄火。邁威爾上季營收與獲利優於預期、並上調全年財測，顯示雲端業者的客製化晶片與資料中心投資仍在擴張。這對台灣的先進製程、封裝、網通、光通訊與伺服器供應鏈仍是正向傳導；但同一晚主要指數沒有續強，也說明「訂單成長」與「估值再擴張」已變成兩件事。

台股自身的資金面則提供緩衝。週五台股收在四萬六千三百三十一點附近，單週上漲逾一千一百點，外資單週買超也逾一千一百億元，而且資金不只集中 AI，金融與傳產同樣獲得青睞。這種擴散有利於降低指數完全依賴少數大型電子股的脆弱度；若新台幣升值與外資回補延續，台積電等權值股仍可支撐指數，但高估值供應鏈的表現會更取決於獲利兌現。

目前價格已相當程度反映 AI 資本支出續強，尚未充分反映的是鷹派利率訊號是否轉成實際政策與債券殖利率上行。若後續通膨持續降溫、利率預期回穩，且科技股重新擴散上漲，這個「基本面正向、估值受限」判斷就應降級；反之，若殖利率上升、主要指數跌破財報後支撐，或外資回補中斷，台股下週更可能從普漲轉為權值、金融與具訂單能見度產業之間的輪動。"""


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
        placeholders = ",".join(["%s"] * len(MARKET_IDS))
        cursor.execute(
            f"SELECT id,event_id,trade_date,market_session,symbol,label,open_price,last_price,recorded_price "
            f"FROM t_market_index_snapshots WHERE id IN ({placeholders}) ORDER BY id",
            tuple(MARKET_IDS),
        )
        market_columns = ["id", "event_id", "trade_date", "market_session", "symbol", "label", "open_price", "last_price", "recorded_price"]
        market = json_safe([dict(zip(market_columns, row)) for row in cursor.fetchall()])
    finally:
        cursor.close()
    if len(events) != len(EVENT_IDS) or len(market) != len(MARKET_IDS):
        raise RuntimeError("required local evidence rows are missing")

    structured = {
        "schema_version": "codex-market-analysis-v1",
        "headline": "AI 基本面仍強，鷹派利率訊號壓住估值",
        "thesis": "AI 與資料中心需求仍有支撐，但聯準會對通膨的鷹派訊號限制估值擴張，台股轉向資金與獲利品質分化。",
        "sentiment": "constructive_cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close", "event_id": 789668, "market_snapshot_ids": MARKET_IDS},
            {"role": "fed_inflation_risk", "event_id": 789728},
            {"role": "ai_custom_chip_demand", "event_id": 788345},
            {"role": "taiwan_flow_breadth", "event_id": 789639},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、封裝、網通、光通訊與伺服器", "mechanism": "資料中心與客製化晶片需求支撐訂單"},
            {"sector": "大型電子權值", "mechanism": "外資回補與匯率支撐指數，但利率限制估值"},
            {"sector": "金融與傳產", "mechanism": "資金擴散降低指數對少數科技權值的依賴"},
        ],
        "invalidation": [
            "通膨持續降溫且利率預期回穩",
            "科技股重新擴散上漲",
            "殖利率上行或外資回補中斷",
        ],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY,
        structured_payload=structured,
        events_payload=events,
        market_payload=market,
    )
    forbidden = [
        "今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導", "先看區間邊界",
        "現在只看", "今日主命題", "三個證據", "市場正在定價什麼", "台股配置", "今日個股觀察",
        "stock_watch", "買進", "推薦", "候選", "入場", "停損", "止損", "目標價", "t_relay_events",
        "t_market_analyses", "claim_verifier", "market_context", "raw_json",
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
        "evidence_event_ids": EVENT_IDS,
        "market_snapshot_ids": MARKET_IDS,
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style_checks,
        "external_provider_api_called": False,
    }
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=ANALYSIS_DATE, analysis_slot=SLOT, scheduled_time_local="05:00",
        model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY, events_used=len(events), market_rows_used=len(market),
        push_enabled=True, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False),
        structured_json=json.dumps(structured, ensure_ascii=False),
    ))

    cursor = store._cursor()
    try:
        cursor.execute(
            "SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s",
            (ANALYSIS_DATE, SLOT),
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
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", str(stored[3]))),
        "style_ok": stored_raw.get("style_checks", {}).get("ok") is True,
        "fixed_section_template": stored_raw.get("style_checks", {}).get("fixed_section_template"),
        "external_provider_api_called": stored_raw.get("external_provider_api_called"),
        "trade_signal_count": signal_count,
    }
    if not all([
        checks["claim_verifier_ok"], checks["trust_gate_ok"], checks["push_enabled"], not checks["pushed"],
        checks["structured_json_present"], not checks["garbled_text"], checks["style_ok"],
        checks["fixed_section_template"] is False, checks["external_provider_api_called"] is False,
        checks["trade_signal_count"] == 0,
    ]):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
