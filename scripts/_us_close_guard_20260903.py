import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-09-03"
SLOT = "us_close"
AUTOMATION_ID = "market-analysis-codex-guard-us-close"
EVENT_IDS = [829574, 826270, 829919, 829891, 829892]
MARKET_IDS = [363, 364, 367, 368]

SUMMARY = """美股收盤帶給台灣投資人的新訊號，是風險偏好已從前一日壓力中回穩，但利率與能源成本還沒有退場。標普 500 收在 7,666.68 點，高於 7,634.58 點的開盤；道瓊收在 53,061.51 點，也高於 52,829.58 點的開盤。這種走勢有利台股權值電子穩住情緒，但更像選擇性承接，而不是估值全面重新擴張。

支撐這個判斷的關鍵，在於股價修復與債券壓力同時存在。市場消息顯示，油價與公共債務疑慮加深債券賣壓；另一方面，美國 7 月整體消費者物價年增 3.30%，核心物價年增 2.47%。因此，股指收高反映資金仍願意承擔風險，卻不能直接推論通膨或折現率壓力已解除。只要長端利率仍受能源與財政供給牽動，高本益比成長股的上行空間就會更依賴獲利兌現，而不是單靠市場情緒。

科技需求的支撐仍有實體投資線索。資料中心擴張不只推升晶片需求，也把電力、冷卻與基礎設施供應商帶進成長鏈。對台灣而言，傳導較直接的是先進製程、伺服器、電源、散熱與網通零組件；但同一套機制也意味著用電、建置成本與資本支出效率會成為市場篩選條件。大型權值與具訂單能見度的供應鏈較可能承接美股回穩，純靠遠期想像支撐的高估值題材則仍容易受殖利率波動影響。

市場目前正在重新定價的是「成長需求尚在，但資金成本不會快速下降」。若後續油價與長債殖利率回落、物價趨勢續降，同時美股漲勢擴散至更多類股，估值壓力才算真正減輕；若債券賣壓延續，或資料中心投資開始出現延後與回報不及預期，今日偏正面的收盤訊號就應降級。對台灣盤面而言，最有辨識力的不是指數單日紅黑，而是權值電子能否帶動成交與類股廣度同步改善。"""


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
        "headline": "美股風險偏好回穩，利率與能源仍限制台股估值擴張",
        "thesis": "美股指數由開盤回升，支持台灣權值電子情緒，但債券、能源與通膨壓力仍使行情偏向選擇性承接。",
        "sentiment": "constructive_selective",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close_recovery", "event_id": 829574, "market_snapshot_ids": MARKET_IDS},
            {"role": "bond_oil_fiscal_pressure", "event_id": 826270},
            {"role": "us_inflation", "event_ids": [829891, 829892]},
            {"role": "data_center_power_cooling_demand", "event_id": 829919},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、伺服器、電源、散熱與網通", "mechanism": "資料中心擴張延伸晶片與基礎設施需求"},
            {"sector": "高本益比成長題材", "mechanism": "長端利率偏高限制估值擴張"},
            {"sector": "高耗能製造", "mechanism": "能源與用電成本增加營運壓力"},
        ],
        "invalidation": [
            "油價與長債殖利率回落且物價趨勢續降",
            "美股漲勢擴散至更多類股",
            "債券賣壓延續或資料中心投資回報轉弱",
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
        "stock_watch_present": "stock_watch" in stored_structured,
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", str(stored[3]))),
        "style_ok": stored_raw.get("style_checks", {}).get("ok") is True,
        "fixed_section_template": stored_raw.get("style_checks", {}).get("fixed_section_template"),
        "external_provider_api_called": stored_raw.get("external_provider_api_called"),
        "trade_signal_count": signal_count,
    }
    if not all([
        checks["claim_verifier_ok"], checks["trust_gate_ok"], not checks["push_enabled"], not checks["pushed"],
        checks["structured_json_present"], not checks["stock_watch_present"], not checks["garbled_text"], checks["style_ok"],
        checks["fixed_section_template"] is False, checks["external_provider_api_called"] is False,
        checks["trade_signal_count"] == 0,
    ]):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
