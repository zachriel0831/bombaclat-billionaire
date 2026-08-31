from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-09-01"
SLOT = "us_close"
AUTOMATION_ID = "market-analysis-codex-guard-us-close"
EVENT_IDS = [810030, 810342, 810814, 812280]
MARKET_IDS = [359, 360]

SUMMARY = """這次美股收盤帶給台灣投資人的訊號，是地緣政治與高利率重新搶回定價主導權，但 AI 供應鏈的產業合作並未停下。道瓊收在約五萬三千一百八十六點、標普五百收在約七千六百八十六點，兩者都低於當日開盤，代表市場面對油價與債券賣壓時，沒有把科技產業的利多直接轉成全面風險偏好。對今日台股而言，方向不宜只看 AI 題材強弱，更要看能源成本與殖利率是否繼續擠壓估值。

## 風險溢價回到盤面中央

本地蒐集的市場消息顯示，美國與伊朗情勢升高之際，油價走高、債券殖利率維持高檔，全球股市轉趨謹慎。這條機制對台股有兩層影響：油價上升會提高運輸、化工與製造成本；殖利率偏高則會拉高長久期成長股的折現率。兩者同時出現時，即使企業訂單沒有惡化，高本益比科技股也較難靠題材再擴張估值。

另一邊，路透相關訊息指出 NVIDIA 計畫投資聯發科並擴大合作，顯示 AI 算力需求正由單一晶片延伸至平台、客製化設計與終端整合。對台灣的傳導不只是大型權值股，也包括先進製程、封裝、IC 設計、伺服器與高速傳輸供應鏈；不過這類產業合作屬中期基本面支撐，未必足以抵銷同一天的利率與能源風險。

因此，盤面已在反映 AI 投資仍有延續性，尚未完全定價的是中東衝突是否讓油價與殖利率形成更持久的上行組合。若油價回落、債市賣壓緩和，且美股主要指數重新站回開盤區附近，這個「風險溢價壓過產業利多」的判斷就應降級；反之，若能源與利率同步走高，台股較可能呈現大型電子撐指數、傳產與高估值供應鏈分化的格局，而不是全面性追價。"""


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
        "headline": "油價與殖利率壓住風險偏好，AI 合作支撐台灣供應鏈",
        "thesis": "地緣政治、能源與利率風險壓過單日科技利多，但 AI 產業合作仍為台灣供應鏈提供中期支撐。",
        "sentiment": "cautious_selective",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close", "event_id": 812280, "market_snapshot_ids": MARKET_IDS},
            {"role": "oil_rates_risk", "event_id": 810342},
            {"role": "geopolitical_risk", "event_id": 810030},
            {"role": "ai_taiwan_partnership", "event_id": 810814},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、封裝、IC 設計、伺服器與高速傳輸", "mechanism": "AI 平台合作延伸中期需求"},
            {"sector": "運輸、化工與製造", "mechanism": "油價上升提高成本壓力"},
            {"sector": "高估值電子", "mechanism": "殖利率偏高限制估值擴張"},
        ],
        "invalidation": [
            "油價回落且債市賣壓緩和",
            "美股主要指數重新站回開盤區附近",
            "能源與殖利率持續同步上行",
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

    cursor = store._cursor()
    try:
        cursor.execute(
            "SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json FROM t_market_analyses "
            "WHERE analysis_date=%s AND analysis_slot=%s",
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
        "push_enabled": bool(stored[1]),
        "pushed": bool(stored[2]),
        "structured_json_present": bool(stored_structured),
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", str(stored[3]))),
        "style_ok": stored_raw.get("style_checks", {}).get("ok") is True,
        "fixed_section_template": stored_raw.get("style_checks", {}).get("fixed_section_template"),
        "external_provider_api_called": stored_raw.get("external_provider_api_called"),
        "trade_signal_count": signal_count,
    }
    if not all([
        checks["claim_verifier_ok"], checks["trust_gate_ok"], not checks["push_enabled"], not checks["pushed"],
        checks["structured_json_present"], not checks["garbled_text"], checks["style_ok"],
        checks["fixed_section_template"] is False, checks["external_provider_api_called"] is False,
        checks["trade_signal_count"] == 0,
    ]):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
