from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-09-02"
SLOT = "us_close"
AUTOMATION_ID = "market-analysis-codex-guard-us-close"
EVENT_IDS = [820141, 820219, 820549, 820822]
MARKET_IDS = [363, 364]

SUMMARY = """這次美股收盤帶給台灣投資人的變化，是風險焦點正從單純的 AI 成長敘事，轉向「能源衝擊會不會把通膨與利率壓力拉長」。道瓊收在約五萬二千七百六十八點，低於當日開盤；標普五百收在約七千六百三十二點，也略低於開盤。兩個指數並未出現同樣幅度的下跌，顯示壓力目前更像風險溢價與產業輪動，而不是科技需求已被全面否定。

## 油價、通膨與折現率重新連成一條線

本地蒐集的消息顯示，美國對伊朗發動新一輪打擊，中東升級同時推高市場對能源供應的警戒。另一項歐洲資料顯示，能源價格上漲伴隨歐元區通膨升至百分之三點三，市場也提高對歐洲央行升息的預期。這兩項訊息的共同機制，是油價不只影響運輸與製造成本，也可能延後主要央行轉向寬鬆的時間；對估值較高的科技股而言，需求仍強並不等於折現率壓力已經消失。

台灣端同時出現不同方向的基本面訊號。產業消息認為 AI 帶動晶片種類、數量與材料規格提升，矽晶圓需求被視為結構性成長，而不只是短期庫存循環。這讓先進製程、矽晶圓、封裝、伺服器與散熱供應鏈仍有中期支撐；但能源成本上升與利率維持高檔，會讓高耗能製造、運輸以及高本益比電子股面臨較大的評價壓力。今日台股更值得觀察的是權值電子能否穩住指數，以及能源敏感產業是否擴大分化。

目前市場已部分反映中東風險與 AI 需求並存，尚未充分定價的是油價上漲會不會持續傳入通膨與央行政策。若衝突降溫、油價回落，且債市對升息或延後降息的預期緩和，這個「能源與利率壓過成長題材」的判斷就應降級；反之，若能源價格與殖利率同步走高，即使 AI 訂單沒有轉弱，台股也更可能走向權值支撐、類股分化，而不是全面擴張估值。"""


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
        "headline": "能源衝擊重拉通膨與利率壓力，AI 需求支撐台灣供應鏈",
        "thesis": "中東與能源風險正在提高通膨和利率的不確定性，但 AI 結構性需求尚未被美股收低否定。",
        "sentiment": "cautious_selective",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close", "event_id": 820822, "market_snapshot_ids": MARKET_IDS},
            {"role": "geopolitical_energy_risk", "event_id": 820219},
            {"role": "europe_inflation_rates", "event_id": 820141},
            {"role": "taiwan_ai_wafer_demand", "event_id": 820549},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、矽晶圓、封裝、伺服器與散熱", "mechanism": "AI 結構性需求提供中期支撐"},
            {"sector": "高耗能製造與運輸", "mechanism": "能源成本上升壓縮成本空間"},
            {"sector": "高本益比電子", "mechanism": "利率維持高檔限制估值擴張"},
        ],
        "invalidation": [
            "中東衝突降溫且油價回落",
            "債市對升息或延後降息的預期緩和",
            "能源價格與殖利率持續同步走高",
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
