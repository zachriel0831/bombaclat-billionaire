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

ANALYSIS_DATE = "2026-09-04"
SLOT = "us_close"
EVENT_IDS = [839046, 839487, 838952, 839418]
MARKET_IDS = [369, 370, 371, 372]

SUMMARY = """美股收盤替台灣投資人改變的，是風險偏好從債券壓力中重新取得支撐，但還不能把它解讀成資金成本已經全面轉鬆。標普 500 收在 7,747.60 點，高於 7,699.17 點的開盤；道瓊收在 53,685.52 點，也高於 53,394.94 點的開盤。科技股領漲與債券殖利率回落，讓台股大型電子與 AI 供應鏈的情緒偏正面，最大的變數仍是利率回落能否延續，以及能源風險會不會再度推高通膨預期。

這次反彈的證據鏈有三層。第一，兩大美股指數都由開盤走高，顯示買盤不只是隔夜跳空，而是在盤中持續承接。第二，市場消息把漲勢連到殖利率回落與大型科技股走強，代表估值壓力暫時緩和，成長股重新取得主導權。第三，美國 7 月對台貿易逆差升至 207 億美元，背後與 AI 建設帶動進口有關；這把美國科技資本支出與台灣半導體、伺服器及零組件需求的連結變得更具體。不過，中東原油供應疑慮仍為油價提供支撐，表示通膨與長端利率的尾端風險尚未消失。

傳到台灣盤面，較直接的是先進製程、AI 伺服器、網通、電源與散熱鏈的風險溢價改善；若美債殖利率續降，權值電子可望比高耗能或景氣敏感族群更容易承接資金。反過來說，油價若因地緣風險明顯上行，運輸、原物料與製造成本壓力會抵銷部分科技需求利多。這也是為什麼今日訊號比較像成長主線修復，而不是所有類股同步擴張。

市場已開始反映殖利率回落與科技需求仍強，尚未完全反映的是這兩者能否同時維持。若後續利率續降、科技股漲勢擴散，而且台股權值電子能帶動成交與類股廣度改善，偏正面的判斷才會升級；若殖利率重新上行、油價走強，或美股漲勢快速縮回少數大型科技股，這次收盤所帶來的風險偏好修復就應降級。"""


def safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    if now.date().isoformat() != ANALYSIS_DATE or SLOT not in allowed_analysis_slots(calendar):
        raise RuntimeError("calendar does not allow target slot")

    store = MySqlEventStore(load_settings(".env"))
    store.initialize()
    cursor = store._cursor()
    try:
        marks = ",".join(["%s"] * len(EVENT_IDS))
        cursor.execute(
            f"SELECT id,event_id,source,title,summary,published_at,created_at,raw_json FROM t_relay_events WHERE id IN ({marks}) ORDER BY id",
            tuple(EVENT_IDS),
        )
        cols = ["id", "event_id", "source", "title", "summary", "published_at", "created_at", "raw_json"]
        events = safe([dict(zip(cols, row)) for row in cursor.fetchall()])
        marks = ",".join(["%s"] * len(MARKET_IDS))
        cursor.execute(
            f"SELECT id,event_id,trade_date,market_session,symbol,label,open_price,last_price,recorded_price FROM t_market_index_snapshots WHERE id IN ({marks}) ORDER BY id",
            tuple(MARKET_IDS),
        )
        cols = ["id", "event_id", "trade_date", "market_session", "symbol", "label", "open_price", "last_price", "recorded_price"]
        market = safe([dict(zip(cols, row)) for row in cursor.fetchall()])
    finally:
        cursor.close()
    if len(events) != len(EVENT_IDS) or len(market) != len(MARKET_IDS):
        raise RuntimeError("required evidence missing")

    structured = {
        "schema_version": "codex-market-analysis-v1",
        "headline": "科技與利率帶動風險偏好修復，能源風險仍限制全面擴張",
        "thesis": "美股盤中承接與科技領漲支持台灣電子情緒，但油價及殖利率反彈仍可能中斷估值修復。",
        "sentiment": "constructive_selective",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close_rally", "event_ids": [839046, 839487], "market_snapshot_ids": MARKET_IDS},
            {"role": "ai_trade_taiwan_link", "event_id": 838952},
            {"role": "energy_geopolitical_risk", "event_id": 839418},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、AI 伺服器、網通、電源與散熱", "mechanism": "科技需求與殖利率回落改善成長資產風險溢價"},
            {"sector": "運輸、原物料與高耗能製造", "mechanism": "油價上行增加成本與通膨壓力"},
        ],
        "invalidation": ["殖利率重新上行", "油價因供應風險走強", "美股漲勢縮回少數大型科技股"],
    }
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    forbidden = ["今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導", "先看區間邊界", "現在只看", "今日主命題", "三個證據", "市場正在定價什麼", "台股配置", "今日個股觀察", "stock_watch", "買進", "推薦", "候選", "入場", "停損", "止損", "目標價", "t_relay_events", "t_market_analyses", "claim_verifier", "market_context", "raw_json"]
    found = [term for term in forbidden if term in SUMMARY]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", SUMMARY))
    english_heading = bool(re.search(r"(?m)^#{1,6}\s+[A-Za-z]", SUMMARY))
    style = {"ok": not found and not garbled and not english_heading, "template": "flexible-briefing-memo-v1", "garbled_text": garbled, "forbidden_terms": found, "fixed_section_template": False, "english_section_headings": english_heading}
    if not verifier["ok"] or not style["ok"]:
        raise RuntimeError(json.dumps({"claim_verifier": verifier, "style_checks": style}, ensure_ascii=False))

    raw = {"automation_id": "market-analysis-codex-guard-us-close", "generator": "codex_automation", "display_title": ANALYSIS_DATE, "calendar": calendar.to_dict(), "evidence_event_ids": EVENT_IDS, "market_snapshot_ids": MARKET_IDS, "claim_verifier": verifier, "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"}, "style_checks": style, "external_provider_api_called": False}
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=ANALYSIS_DATE, analysis_slot=SLOT, scheduled_time_local="05:00", model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1", summary_text=SUMMARY, events_used=len(events), market_rows_used=len(market), push_enabled=False, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))

    cursor = store._cursor()
    try:
        cursor.execute("SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s", (ANALYSIS_DATE, SLOT))
        stored = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s", (row_id,))
        signals = int(cursor.fetchone()[0])
    finally:
        cursor.close()
    stored_raw = json.loads(stored[4])
    stored_structured = json.loads(stored[5])
    checks = {"analysis_id": int(stored[0]), "claim_verifier_ok": stored_raw["claim_verifier"]["ok"] is True, "claim_support_rate": stored_raw["claim_verifier"].get("support_rate"), "trust_gate_ok": stored_raw["trust_gate"]["ok"] is True, "trust_gate_reason": stored_raw["trust_gate"].get("reason"), "push_enabled": bool(stored[1]), "pushed": bool(stored[2]), "structured_json_present": bool(stored_structured), "stock_watch_present": "stock_watch" in stored_structured, "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", stored[3])), "style_ok": stored_raw["style_checks"]["ok"] is True, "fixed_section_template": stored_raw["style_checks"].get("fixed_section_template"), "external_provider_api_called": stored_raw.get("external_provider_api_called"), "trade_signal_count": signals}
    if not all([checks["claim_verifier_ok"], checks["trust_gate_ok"], not checks["push_enabled"], not checks["pushed"], checks["structured_json_present"], not checks["stock_watch_present"], not checks["garbled_text"], checks["style_ok"], checks["fixed_section_template"] is False, checks["external_provider_api_called"] is False, signals == 0]):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
