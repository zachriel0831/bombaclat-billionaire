from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-09-02"
SLOT = "pre_tw_open"
AUTOMATION_ID = "market-analysis-codex-guard-pre-open"
EVENT_IDS = [820141, 820219, 820549, 822157]
MARKET_IDS = [363, 364]

SUMMARY = """盤前市場正在交易的是能源衝擊可能延長高利率，而不是 AI 需求已經反轉。台股基調偏中性、略帶防守：半導體的中期需求仍有支撐，但美國科技股與半導體指數轉弱，會讓今天的電子盤面更重視獲利能見度與估值。最大不確定性，是中東風險會停留在短期風險溢價，還是透過油價與通膨改變央行政策預期。

## 成長主線還在，價格先接受利率檢驗

盤前跨資產資料顯示，那斯達克一百指數下跌百分之一點二九，半導體指數下跌百分之二點一四，市場廣度也偏弱；這表示壓力不只集中在少數大型股，資金正在降低長久期成長資產的風險承受度。美國十年期公債殖利率約百分之四點七九，折現率仍高，AI 題材若要重新擴張評價，需要更明確的獲利兌現或利率回落配合。

能源與通膨是這輪重估的傳導核心。中東衝突升級提高供應風險，西德州原油約八十三點九美元、布蘭特原油約八十八點二四美元；歐元區通膨升至百分之三點三並帶動升息預期，也提醒市場，能源價格若維持高檔，主要央行轉向寬鬆的時間可能後移。對台股而言，這會同時壓抑高本益比電子的評價，並增加運輸、化工與耗能製造的成本不確定性。

不過，產業需求並未與股價同步轉弱。台灣供應鏈資料指出，AI 正提高晶片種類、數量與材料規格，矽晶圓需求仍被視為結構性成長。這讓先進製程、矽晶圓、封裝、伺服器與散熱仍有基本面支撐；只是今天更可能呈現大型權值與訂單能見度較高的供應鏈相對抗震，而非電子族群全面抬升。

信用市場目前仍提供緩衝，高收益債利差約百分之二點六三，金融壓力指標也未顯示全面緊縮。市場已部分反映 AI 成長與高利率並存，還沒充分定價的是能源衝擊會持續多久。若油價與十年期殖利率回落、半導體指數止跌且市場廣度改善，防守判斷可上調；反之，若油價、殖利率與信用利差同步走高，即使 AI 訂單沒有立即惡化，台股仍可能轉成權值撐盤、族群分化加劇。"""


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
        "headline": "能源與利率壓抑評價，AI 基本面仍提供台股支撐",
        "thesis": "台股盤前偏中性略防守；能源與高殖利率提高風險溢價，但 AI 結構性需求尚未反轉。",
        "sentiment": "neutral_cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "europe_inflation_rates", "event_id": 820141},
            {"role": "geopolitical_energy_risk", "event_id": 820219},
            {"role": "taiwan_ai_wafer_demand", "event_id": 820549},
            {"role": "pre_open_cross_asset_context", "event_id": 822157, "market_snapshot_ids": MARKET_IDS},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、矽晶圓、封裝、伺服器與散熱", "mechanism": "AI 結構性需求提供基本面支撐，但高殖利率限制評價"},
            {"sector": "高本益比電子", "mechanism": "美國科技與半導體轉弱使市場提高獲利兌現要求"},
            {"sector": "運輸、化工與耗能製造", "mechanism": "高油價增加成本與通膨不確定性"},
        ],
        "invalidation": [
            "油價與十年期殖利率回落，半導體指數止跌且市場廣度改善",
            "油價、殖利率與信用利差同步走高",
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
