from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-08-31"
SLOT = "pre_tw_open"
AUTOMATION_ID = "market-analysis-codex-guard-pre-open"
EVENT_IDS = [804864, 806032, 806264, 806288]

SUMMARY = """市場目前同時交易兩股力量：AI 與先進封裝的需求能見度仍在，卻被更高的利率與中東能源風險壓住估值。台股盤前基調偏中性、略帶防守，電子權值有基本面支撐，但指數要擴大上行仍需先確認油價與長債殖利率不再升高；最大不確定性是荷莫茲海峽情勢會不會把短期油價衝擊變成新的通膨壓力。

## 需求沒有消失，折現率先收緊

盤前市場資料顯示，美國十年期公債殖利率約百分之四點七三，高收益債利差約百分之二點六三。信用市場尚未顯示全面性壓力，意味企業融資風險暫時可控；但長債殖利率處在高檔，會提高成長股折現率，讓資金更要求營收成長能夠轉成毛利與現金流，而不是只接受題材延伸。

利率壓力還可能被政策預期放大。最新財經消息指出，聯準會主席華許重申抗通膨立場，市場把九月升息機率推高到約六成。這類預期若持續，最先受影響的是高評價科技與長久期資產；對台股而言，台積電等大型權值仍可受惠 AI 訂單，但評價再擴張的門檻會提高。

能源端則出現更直接的成本訊號。荷莫茲海峽戰火再起後，布蘭特原油一度站上每桶九十美元，西德州原油逼近八十六美元。油價若只短暫跳升，影響多半停留在風險情緒；若高檔延續，運輸、塑化與耗能製造的成本壓力會增加，也可能讓市場延後對通膨與利率降溫的期待。

科技基本面仍提供下檔支撐。台灣先進封裝供應鏈傳出客製化晶片與異質整合訂單擴張，顯示 AI 資本支出仍往先進製程、封裝與伺服器鏈傳導。不過本輪較可能呈現有訂單與議價能力者領先，而不是電子族群全面同步上漲；金融與傳產則更看利率、匯率和能源成本的分化。

目前價格已部分反映 AI 需求續強，也開始反映利率偏鷹與油價風險，尚未定價清楚的是能源衝擊會維持多久。若油價回落、十年期殖利率轉低，且先進封裝訂單持續轉成獲利，盤前的防守判斷可轉為偏多；反過來，若油價與殖利率同步上行、信用利差也開始擴大，或 AI 供應鏈毛利展望下修，就代表成本與折現率正一起侵蝕獲利，台股權值支撐也應降級。"""


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
        "headline": "AI 需求仍有支撐，利率與能源壓住估值",
        "thesis": "台股盤前偏中性略防守；AI 與先進封裝需求仍在，但高利率和能源衝擊限制估值。",
        "sentiment": "neutral_cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "ai_advanced_packaging_demand", "event_id": 804864},
            {"role": "energy_geopolitical_shock", "event_id": 806032},
            {"role": "rates_credit_context", "event_id": 806264},
            {"role": "fed_repricing", "event_id": 806288},
        ],
        "tw_sector_transmission": [
            {"sector": "大型電子、先進製程與先進封裝", "mechanism": "AI 訂單支撐基本面，但高殖利率提高評價門檻"},
            {"sector": "運輸、塑化與耗能製造", "mechanism": "能源價格延續時間決定成本壓力"},
            {"sector": "金融與傳產", "mechanism": "利率、匯率與能源成本造成分化"},
        ],
        "invalidation": [
            "油價回落且十年期殖利率轉低",
            "先進封裝訂單持續轉成獲利",
            "油價、殖利率與信用利差同步上行",
            "AI 供應鏈毛利展望下修",
        ],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[]
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
        market_rows_used=0,
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
