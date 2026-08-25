from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-08-26"
SLOT = "us_close"
AUTOMATION_ID = "market-analysis-codex-guard-us-close"
EVENT_IDS = [763002, 763296]
MARKET_IDS = [343, 344]

SUMMARY = """美股收盤沒有把風險偏好推向明確方向，對台灣投資人真正改變的是：指數仍有支撐，但貿易成本與終端需求正把產業差異拉大。台股今天較可能由大型權值與實際獲利能力穩住盤面，出口成本敏感或消費循環較弱的族群，則更容易面對評價壓力；目前最大的未知數，是關稅升級會不會從政治訊號變成企業訂單與毛利的實際變化。

## 平靜指數下的成本壓力

道瓊收在約五萬三千五百七十七點，與開盤幾乎相同；標普五百收在約七千六百七十七點，也只有極小變動。這代表市場沒有出現全面撤出風險資產的跡象，但也缺少足以讓高評價成長題材同步擴張的動能。對台股而言，半導體、伺服器與大型電子權值仍可扮演穩定器，後續表現卻更需要訂單、資本支出與獲利兌現，而不是只靠美股指數上漲帶動。

加拿大宣布對美國商品採取等額報復性關稅，部分稅率最高可達五成，涵蓋鋼鐵、家具等品項。這項訊號的重要性不只在雙邊貿易量，而在企業必須重新評估採購地點、庫存與成本轉嫁。台灣的金屬、機械、零組件與北美供應鏈，可能同時遇到轉單機會與輸入成本上升，真正的方向要看客戶是否調整訂單，而不能把關稅升級直接等同於受惠。

同一個交易時段，美國運動用品零售商警告運動服飾與鞋類需求轉弱。單一企業訊號不能代表整體消費，但它與關稅成本放在一起看，顯示品牌與通路的售價承受力值得留意。這會傳到台灣的紡織、製鞋與消費電子供應鏈：若終端需求偏弱，品牌商更可能要求供應商分攤成本，接單增加未必能同步改善毛利。

市場目前已反映大型指數仍有承接，尚未充分定價的，是報復性關稅擴大後的訂單重排，以及需求放緩與成本上升同時發生。若後續美股成長股重新帶量上行、企業財測未見毛利壓力，而且關稅沒有擴大到更多品項，本次「盤面穩定但產業分化加深」的判斷就應降級；反之，若零售需求警訊擴散、企業開始下修財測，台股出口與消費供應鏈的評價會先接受檢驗。"""


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
        cursor.execute(
            "SELECT id,event_id,source,title,summary,published_at,created_at,raw_json "
            "FROM t_relay_events WHERE id IN (%s,%s) ORDER BY id",
            tuple(EVENT_IDS),
        )
        event_columns = ["id", "event_id", "source", "title", "summary", "published_at", "created_at", "raw_json"]
        events = json_safe([dict(zip(event_columns, row)) for row in cursor.fetchall()])
        cursor.execute(
            "SELECT id,event_id,source,trade_date,market_session,symbol,label,open_price,last_price,recorded_price,created_at "
            "FROM t_market_index_snapshots WHERE id IN (%s,%s) ORDER BY id",
            tuple(MARKET_IDS),
        )
        market_columns = ["id", "event_id", "source", "trade_date", "market_session", "symbol", "label", "open_price", "last_price", "recorded_price", "created_at"]
        market = json_safe([dict(zip(market_columns, row)) for row in cursor.fetchall()])
    finally:
        cursor.close()
    if len(events) != len(EVENT_IDS) or len(market) != len(MARKET_IDS):
        raise RuntimeError("required local evidence rows are missing")

    structured = {
        "schema_version": "codex-market-analysis-v1",
        "headline": "指數近乎收平，關稅與需求拉大產業差異",
        "thesis": "美股風險偏好未明顯轉弱，但貿易成本與消費需求使台股產業分化加深。",
        "sentiment": "cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close_flat", "market_snapshot_ids": MARKET_IDS},
            {"role": "canada_retaliatory_tariffs", "event_id": 763002},
            {"role": "us_consumer_demand_warning", "event_id": 763296},
        ],
        "tw_sector_transmission": [
            {"sector": "半導體、伺服器與大型電子權值", "mechanism": "指數穩定提供支撐，但評價需要訂單與獲利兌現"},
            {"sector": "金屬、機械與零組件", "mechanism": "北美關稅可能同時帶來轉單與輸入成本壓力"},
            {"sector": "紡織、製鞋與消費電子", "mechanism": "終端需求轉弱會提高品牌商的成本分攤要求"},
        ],
        "invalidation": [
            "美股成長股重新帶量上行",
            "企業財測未出現毛利壓力",
            "關稅措施沒有擴大到更多品項",
        ],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY,
        structured_payload=structured,
        events_payload=events,
        market_payload=market,
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
        "market_snapshot_rows": len(market),
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style_checks,
        "external_provider_api_called": False,
    }
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=ANALYSIS_DATE,
        analysis_slot=SLOT,
        scheduled_time_local="05:00",
        model="codex-local-judgment",
        prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY,
        events_used=len(events),
        market_rows_used=len(market),
        push_enabled=False,
        pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False),
        structured_json=json.dumps(structured, ensure_ascii=False),
    ))
    verify_cursor = store._cursor()
    try:
        verify_cursor.execute(
            "SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json FROM t_market_analyses "
            "WHERE analysis_date=%s AND analysis_slot=%s",
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
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", stored_summary)),
        "style_ok": stored_raw.get("style_checks", {}).get("ok") is True,
        "fixed_section_template": stored_raw.get("style_checks", {}).get("fixed_section_template"),
        "external_provider_api_called": stored_raw.get("external_provider_api_called"),
        "trade_signal_count": signal_count,
    }
    if not all([
        checks["claim_verifier_ok"], checks["trust_gate_ok"], not checks["push_enabled"],
        not checks["pushed"], checks["structured_json_present"], not checks["garbled_text"],
        checks["style_ok"], checks["fixed_section_template"] is False,
        checks["external_provider_api_called"] is False, checks["trade_signal_count"] == 0,
    ]):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
