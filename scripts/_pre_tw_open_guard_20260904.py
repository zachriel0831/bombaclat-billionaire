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

ANALYSIS_DATE = "2026-09-04"
SLOT = "pre_tw_open"
AUTOMATION_ID = "market-analysis-codex-guard-pre-open"
EVENT_IDS = [838952, 839046, 839418, 839487, 840396]
MARKET_IDS = [371, 372]

SUMMARY = """盤前市場正在交易的是美股利率壓力緩和後的科技風險偏好修復，但資金仍集中在大型成長主線，還不是全面景氣交易。標普五百收在七千七百四十七點六零，高於七千六百八十六點七一的開盤；道瓊收在五萬三千六百八十五點五二，也高於五萬三千三百零九點一七的開盤。這讓台股開盤基調偏正面，較有利於大型權值電子與具訂單能見度的 AI 供應鏈；最大不確定性是油價與利率是否再度反向上行。

## 漲勢有承接，廣度仍待確認

科技股領漲與債券殖利率回落，說明近期壓抑成長股評價的力量暫時減弱，而且兩大美股指數都由開盤位置走高，盤中承接並不弱。不過，盤前資料顯示那斯達克一百指數上漲百分之一點一六，半導體指數僅上漲百分之零點一一；等權重相對市值加權指數也偏弱。市場其實更像資金集中承接少數大型科技資產，而不是風險偏好已擴散到所有產業。

需求面仍給台灣科技鏈實體支撐。美國七月對台單月貿易逆差升至二百零七億美元，報導把增幅連結到 AI 建設帶動的進口。這表示美國科技資本支出仍可沿著先進製程、伺服器、網通、電源與散熱傳到台灣；但當漲勢集中，市場會更嚴格區分有訂單與獲利落地的環節，純題材的評價彈性反而有限。

另一端是能源約束。西德州原油約九十一點四八美元、布蘭特原油約九十六點零二美元，中東供應疑慮仍在。高油價若維持，會經由運輸與製造成本、通膨預期再傳到長端利率，對高本益比電子形成估值上限，也提高運輸、化工與耗能製造的成本不確定性。

目前價格已反映利率回落與大型科技股續強，尚未充分反映的是漲勢能否擴散、能源風險能否降溫。若半導體相對漲幅追上、等權重表現改善，同時油價與殖利率回落，偏正面的判斷可再升級；若美股漲勢繼續縮在少數權值股，或油價與信用利差同步走高，這個盤前判斷就應降級。今天最值得辨認的不是指數是否開高，而是權值電子能否帶動成交與類股廣度一起改善。"""


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
            f"SELECT id,event_id,source,title,summary,published_at,created_at,raw_json FROM t_relay_events "
            f"WHERE id IN ({placeholders}) ORDER BY id",
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
        "headline": "科技風險偏好修復，但漲勢集中與能源風險限制台股擴散",
        "thesis": "台股盤前偏正面但集中於大型權值電子與具實體需求的 AI 供應鏈，油價與利率反彈是主要風險。",
        "sentiment": "constructive_selective",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close_intraday_bid", "event_ids": [839046, 839487], "market_snapshot_ids": MARKET_IDS},
            {"role": "narrow_technology_breadth", "event_id": 840396},
            {"role": "ai_trade_taiwan_link", "event_id": 838952},
            {"role": "energy_geopolitical_risk", "event_ids": [839418, 840396]},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、AI 伺服器、網通、電源與散熱", "mechanism": "美國科技資本支出與利率回落支持具訂單能見度的成長資產"},
            {"sector": "高本益比電子", "mechanism": "油價與長端利率反彈限制估值修復"},
            {"sector": "運輸、化工與耗能製造", "mechanism": "高能源價格增加成本與通膨不確定性"},
        ],
        "invalidation": [
            "半導體相對漲幅追上且等權重表現改善",
            "美股漲勢持續縮在少數大型權值股",
            "油價與信用利差同步走高",
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
