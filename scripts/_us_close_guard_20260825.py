from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-08-25"
SLOT = "us_close"
AUTOMATION_ID = "market-analysis-codex-guard-us-close"
EVENT_IDS = [756074, 756073, 756015]
MARKET_IDS = [339, 340]

SUMMARY = """美股這次收盤帶給台灣投資人的重點，是資金並未全面轉弱，卻明顯在降低對單一成長敘事的依賴。道瓊收高、標普五百小幅收低，顯示景氣與現金流題材仍有人承接，但高評價資產缺少一起上行的確認；台股短線因此較可能呈現大型權值撐盤、產業內部分化，而不是電子族群全面擴張評價。最大不確定性來自美國對伊朗施壓是否外溢到能源、美元與通膨預期。

## 指數分歧背後的風險排序

道瓊由開盤約五萬三千二百六十二點升至五萬三千四百十七點，標普五百則由約七千六百六十三點回到七千六百五十三點。兩個大型指數方向不同，較像資金在景氣韌性與成長股評價之間重新分配，而不是市場對風險資產給出一致加碼訊號。對台股而言，這會提高選擇性：具實際訂單、獲利與現金流支撐的供應鏈較能抵抗波動，純靠遠期想像推升的題材則更容易受利率與風險溢價擠壓。

同一時間，美國宣布加強對伊朗的經濟制裁，伊朗也表達將回應。市場尚未看到供給中斷的直接證據，但制裁若擴及交易對手或美元結算，風險會先透過能源與運輸成本，再回到通膨預期及債券評價。加拿大與美國的貿易談判破裂，則提醒投資人，關稅與供應鏈摩擦並非背景雜訊；它可能改變企業投資地點、庫存安排與成本轉嫁能力。

另一項供應鏈訊號是，市場消息指 Google 計畫在二〇二七年前把 Pixel 製造移出中國，轉往越南與印度。這不等於台灣電子業整體受惠，但代表品牌廠分散產地的方向仍在延續。台灣的半導體、伺服器、零組件與製造服務，受影響的關鍵將是能否跟隨客戶跨區配置，以及新增產能能否轉成可見營收；航運、航空、塑化與耗能製造則需分別評估能源及貿易摩擦對收入與成本的不同傳導。

目前價格已部分反映美國大型股仍有承接，尚未充分定價的是伊朗制裁轉成實際能源或結算干擾，以及北美貿易摩擦進一步拉高企業成本。若後續標普五百重新與道瓊同步走強、能源風險沒有落到供給端，且供應鏈調整帶來的是訂單而非重複資本支出，本次「輪動重於全面上漲」的判斷就應降級；反之，若油價、美元與長債殖利率同步上行，台股高評價電子與成本敏感產業都會面臨更嚴格的估值檢驗。"""


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
            "FROM t_relay_events WHERE id IN (%s,%s,%s) ORDER BY id",
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
        "headline": "指數分歧，供應鏈與地緣風險提高選擇性",
        "thesis": "美股大型指數分歧，台股較可能呈現權值支撐與產業內部分化。",
        "sentiment": "cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close_divergence", "market_snapshot_ids": MARKET_IDS},
            {"role": "iran_sanctions", "event_id": 756015},
            {"role": "north_america_trade_friction", "event_id": 756073},
            {"role": "electronics_supply_chain_shift", "event_id": 756074},
        ],
        "tw_sector_transmission": [
            {"sector": "半導體、伺服器與電子零組件", "mechanism": "評價受指數分歧約束，跨區供應能力影響訂單承接"},
            {"sector": "航運、航空、塑化與耗能製造", "mechanism": "能源與貿易摩擦對收入與成本的傳導方向不同"},
        ],
        "invalidation": [
            "標普五百重新與道瓊同步走強",
            "能源風險未轉成實際供給干擾",
            "供應鏈調整帶來可見訂單而非重複資本支出",
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
