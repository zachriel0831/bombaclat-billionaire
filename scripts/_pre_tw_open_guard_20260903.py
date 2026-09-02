from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-09-03"
SLOT = "pre_tw_open"
AUTOMATION_ID = "market-analysis-codex-guard-pre-open"
EVENT_IDS = [826270, 829574, 829919, 830910]
MARKET_IDS = [367, 368]

SUMMARY = """盤前市場正在交易的，不是成長動能全面轉強，而是債券壓力暫歇後，資金願不願意重新承接科技與半導體。美股主要指數由開盤位置回升，盤前資料也顯示那斯達克一百指數上漲百分之零點二三、半導體指數上漲百分之零點四五；因此台股基調偏正面但仍是選擇性承接。最大不確定性仍在能源：油價維持高檔，若再度推升通膨與長端利率，電子評價修復會很快遇到上限。

## 風險胃納回來了，估值約束還沒走

標普五百收在七千六百六十六點六八，高於七千六百三十四點五八的開盤；道瓊收在五萬三千零六十一點五一，也高於五萬二千八百二十九點五八的開盤。配合波動率指數十五點二零與高收益債利差百分之二點六五，眼前比較像信用環境尚穩、股市願意承擔風險，而不是金融條件突然轉緊。這對台股大型權值電子與具實際訂單能見度的供應鏈較有利，但不足以支持所有高本益比題材同步擴張。

第二條線索是債券賣壓曾受到油價與公共債務疑慮推動，而目前西德州原油約九十一點四八美元、布蘭特原油約九十六點零二美元。能源維持高檔，會透過運輸與製造成本、通膨預期及政策利率路徑壓抑長久期資產；對台灣的傳導，一邊是高本益比電子對殖利率更敏感，另一邊是運輸、化工與耗能製造面臨成本不確定性。

成長端仍有實體支撐。資料中心擴張已把需求從晶片延伸到電力、冷卻與基礎設施，台灣較直接的受惠鏈落在先進製程、伺服器、電源、散熱與網通零組件。不過，資本支出規模大也代表市場會更嚴格檢驗訂單、毛利與投資回報；這輪修復較可能先集中在能見度較高的環節，而不是只靠遠期敘事的全面行情。

目前價格已反映美股風險偏好回穩，尚未完全反映的是高油價會停留多久。若半導體漲勢擴散、市場廣度改善，同時油價與長端殖利率回落，偏正面的盤前判斷可再上調；若油價與信用利差同步走高，或資料中心投資開始延後，這個判斷就應降級。今天較有辨識力的訊號，是權值電子能否帶動成交與類股廣度一起改善。"""


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
        "headline": "美股風險偏好回穩，能源與利率仍限制台股評價",
        "thesis": "台股盤前偏正面但以選擇性承接為主；科技需求仍在，能源與長端利率是最大估值約束。",
        "sentiment": "constructive_selective",
        "confidence": "medium",
        "evidence": [
            {"role": "bond_oil_fiscal_pressure", "event_id": 826270},
            {"role": "us_close_recovery", "event_id": 829574, "market_snapshot_ids": MARKET_IDS},
            {"role": "data_center_power_cooling_demand", "event_id": 829919},
            {"role": "pre_open_cross_asset_context", "event_id": 830910},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、伺服器、電源、散熱與網通", "mechanism": "資料中心擴張延伸晶片與基礎設施需求"},
            {"sector": "高本益比電子", "mechanism": "高油價與長端利率限制估值修復"},
            {"sector": "運輸、化工與耗能製造", "mechanism": "能源成本增加營運與通膨不確定性"},
        ],
        "invalidation": [
            "半導體漲勢擴散且市場廣度改善，同時油價與長端殖利率回落",
            "油價與信用利差同步走高",
            "資料中心投資延後或投資回報轉弱",
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
    english_heading = bool(re.search(r"(?m)^#{1,6}\s+[A-Za-z]", SUMMARY))
    style_checks = {
        "ok": not found_forbidden and not garbled and not english_heading,
        "template": "flexible-briefing-memo-v1",
        "garbled_text": garbled,
        "forbidden_terms": found_forbidden,
        "fixed_section_template": False,
        "english_section_headings": english_heading,
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
        scheduled_time_local="07:30",
        model="codex-local-judgment",
        prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY,
        events_used=len(events),
        market_rows_used=len(market),
        push_enabled=True,
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
        "stock_watch_present": "stock_watch" in stored_structured,
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", str(stored[3]))),
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
