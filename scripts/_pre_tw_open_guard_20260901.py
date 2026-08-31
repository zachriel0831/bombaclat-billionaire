from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-09-01"
SLOT = "pre_tw_open"
AUTOMATION_ID = "market-analysis-codex-guard-pre-open"
EVENT_IDS = [810342, 810814, 812280, 813528]
MARKET_IDS = [359, 360]

SUMMARY = """盤前市場正在交易的不是 AI 需求消失，而是油價與長債殖利率把風險溢價重新抬高。台股基調偏中性、略帶防守：半導體產業訊號仍有支撐，但估值擴張需要更低的利率壓力配合。最大不確定性，是中東風險帶動的能源價格會快速降溫，還是進一步固化通膨與高利率預期。

## 基本面有支撐，資金面先踩煞車

美股上一交易日的道瓊與標普五百都收在開盤價之下，反映油價走高與債券賣壓已壓過部分科技利多。盤前資料又顯示，美國十年期公債殖利率約百分之四點七五；這會提高長久期成長股的折現率，使市場更要求 AI 投資能轉成獲利，而不是只靠題材推升評價。

風險尚未演變成全面緊縮。高收益債利差約百分之二點六，金融壓力指標仍偏寬鬆，表示目前更像估值與風險偏好的調整，而非企業信用危機。這個差異很重要：只要信用市場穩定，電子權值與具訂單能見度的供應鏈仍有承接基礎；若信用利差開始快速擴大，壓力才可能從評價面傳到企業融資與實體需求。

產業端也沒有同步轉弱。半導體指數小幅上漲，NVIDIA 與聯發科擴大合作的消息，顯示 AI 算力需求仍在向平台、IC 設計與終端整合延伸。對台灣的傳導可落在先進製程、封裝、IC 設計、伺服器與高速傳輸，但市場廣度偏弱，較可能呈現大型權值與有實質訂單者相對抗震，而不是電子族群全面上漲。

能源則是台股非電子族群的另一條分化線。西德州原油約八十三點九美元、布蘭特原油約八十八點二四美元；若高檔延續，運輸、化工與耗能製造會先面對成本壓力，也可能延後市場對利率降溫的期待。

目前價格已部分反映 AI 需求延續與利率偏高，尚未充分定價的是能源衝擊的持續時間。若油價回落、十年期殖利率轉低，且市場廣度改善，盤前的防守判斷可上調；反之，若油價與殖利率同步走高，信用利差也開始擴大，即使半導體訂單未立即惡化，台股也更可能進入權值撐盤、族群輪動加快的格局。"""


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
        "headline": "AI 基本面仍有支撐，能源與利率抬高風險溢價",
        "thesis": "台股盤前偏中性略防守；半導體需求訊號仍在，但油價與高殖利率限制估值。",
        "sentiment": "neutral_cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "oil_rates_risk", "event_id": 810342},
            {"role": "ai_taiwan_partnership", "event_id": 810814},
            {"role": "us_close", "event_id": 812280, "market_snapshot_ids": MARKET_IDS},
            {"role": "pre_open_cross_asset_context", "event_id": 813528},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、封裝、IC 設計、伺服器與高速傳輸", "mechanism": "AI 合作延伸需求，但高殖利率限制評價"},
            {"sector": "運輸、化工與耗能製造", "mechanism": "高油價提高成本並延後利率降溫預期"},
            {"sector": "大型電子權值", "mechanism": "信用穩定提供承接，但市場廣度偏弱使走勢分化"},
        ],
        "invalidation": [
            "油價回落、十年期殖利率轉低且市場廣度改善",
            "油價與殖利率同步走高且信用利差擴大",
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
