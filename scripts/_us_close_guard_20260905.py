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

ANALYSIS_DATE = "2026-09-05"
SLOT = "us_close"
EVENT_IDS = [845891, 848358, 848360, 845541]
MARKET_IDS = [373, 374, 375, 376]

SUMMARY = """這次美股收盤替台灣投資人改變的，不是企業獲利敘事，而是利率路徑重新變得更鷹。美國 8 月非農就業新增 16.2 萬人，明顯高於市場預期的 5.3 萬人；標普 500 與道瓊最後都收在開盤之下，顯示股市對「經濟強、資金成本也可能更久偏高」的組合先採取降風險反應。對台股而言，AI 與半導體需求主線沒有被這一晚直接推翻，但高估值電子的折現率壓力重新升高，短線更需要基本面兌現，而不是只靠流動性擴張。

就業報告的細節讓這個判斷更完整。失業率維持 4.1%，私人部門平均時薪年增 3.09%，代表勞動市場並未明顯失速，工資也還不足以讓通膨疑慮完全退場。市場因此有理由把近期寬鬆預期往後挪，長天期殖利率若跟著上行，最先受影響的通常是本益比較高、現金流集中在較遠未來的成長資產。盤面反應與此一致：標普 500 從 7,750.19 點開盤回落至 7,718.36 點，道瓊則由 53,584.89 點降至 53,398.92 點。跌幅不算失序，但「強數據就是利多」的直線敘事已被利率成本打斷。

傳到台灣，先進製程、AI 伺服器、網通、電源與散熱鏈仍有需求支撐，卻可能面臨估值先壓縮、訂單再驗證的節奏；金融股則可能受惠於利差想像，但若殖利率快速上升並壓低風險偏好，正面效果也會被抵銷。8 月外資淨匯入 166.65 億美元，說明台灣市場並非缺乏資金承接，不過這是月度資金背景，不能直接等同下一個交易日必然流入。新台幣走勢、外資現貨與期貨是否同步，會比單一匯入數字更能判斷資金是否真正回到大型權值電子。

目前價格開始反映聯準會更難快速轉鬆，尚未充分定價的是強勁就業能否延續、以及下一批通膨數據是否確認工資壓力仍在。若後續殖利率回落、通膨降溫，而且半導體類股重新擴大參與面，這次偏保守判斷就應降級；反過來，若殖利率續升、美元轉強，並伴隨台股外資現貨與期貨同步轉弱，利率再定價對權值電子的壓力就會加深。週末期間還有政策與地緣消息的空窗，下一個台股交易日應以利率、匯率和市場廣度是否同向確認，而不是把單晚收跌延伸成趨勢結論。"""


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
        "headline": "強勁就業重啟利率再定價，台灣電子回到基本面驗證",
        "thesis": "就業與工資韌性降低快速寬鬆空間，美股盤中回落使台灣高估值電子面臨折現率壓力，但外資匯入背景仍提供承接條件。",
        "sentiment": "cautious_selective",
        "confidence": "medium",
        "evidence": [
            {"role": "labor_repricing", "event_ids": [845891, 848358, 848360]},
            {"role": "us_close_reaction", "market_snapshot_ids": MARKET_IDS},
            {"role": "taiwan_capital_buffer", "event_id": 845541},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、AI 伺服器、網通、電源與散熱", "mechanism": "利率上行先壓縮估值，再由訂單與獲利驗證需求韌性"},
            {"sector": "金融", "mechanism": "利差想像偏正面，但風險偏好轉弱可能抵銷效果"},
        ],
        "invalidation": ["殖利率回落且通膨降溫", "半導體參與面重新擴大", "台股外資現貨與期貨同步轉強"],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY,
        structured_payload=structured,
        events_payload=events,
        market_payload=market,
    )
    forbidden = [
        "今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導", "先看區間邊界", "現在只看",
        "今日主命題", "三個證據", "市場正在定價什麼", "台股配置", "今日個股觀察", "stock_watch", "買進", "推薦",
        "候選", "入場", "停損", "止損", "目標價", "t_relay_events", "t_market_analyses", "claim_verifier", "market_context", "raw_json",
    ]
    found = [term for term in forbidden if term in SUMMARY]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", SUMMARY))
    english_heading = bool(re.search(r"(?m)^#{1,6}\s+[A-Za-z]", SUMMARY))
    style = {
        "ok": not found and not garbled and not english_heading,
        "template": "flexible-briefing-memo-v1",
        "garbled_text": garbled,
        "forbidden_terms": found,
        "fixed_section_template": False,
        "english_section_headings": english_heading,
    }
    if not verifier["ok"] or not style["ok"]:
        raise RuntimeError(json.dumps({"claim_verifier": verifier, "style_checks": style}, ensure_ascii=False))

    raw = {
        "automation_id": "market-analysis-codex-guard-us-close",
        "generator": "codex_automation",
        "display_title": ANALYSIS_DATE,
        "calendar": calendar.to_dict(),
        "evidence_event_ids": EVENT_IDS,
        "market_snapshot_ids": MARKET_IDS,
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style,
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
        push_enabled=True,
        pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False),
        structured_json=json.dumps(structured, ensure_ascii=False),
    ))

    cursor = store._cursor()
    try:
        cursor.execute(
            "SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s",
            (ANALYSIS_DATE, SLOT),
        )
        stored = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s", (row_id,))
        signals = int(cursor.fetchone()[0])
    finally:
        cursor.close()
    stored_raw = json.loads(stored[4])
    stored_structured = json.loads(stored[5])
    checks = {
        "analysis_id": int(stored[0]),
        "claim_verifier_ok": stored_raw["claim_verifier"]["ok"] is True,
        "claim_support_rate": stored_raw["claim_verifier"].get("support_rate"),
        "trust_gate_ok": stored_raw["trust_gate"]["ok"] is True,
        "trust_gate_reason": stored_raw["trust_gate"].get("reason"),
        "push_enabled": bool(stored[1]),
        "pushed": bool(stored[2]),
        "structured_json_present": bool(stored_structured),
        "stock_watch_present": "stock_watch" in stored_structured,
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", stored[3])),
        "style_ok": stored_raw["style_checks"]["ok"] is True,
        "fixed_section_template": stored_raw["style_checks"].get("fixed_section_template"),
        "external_provider_api_called": stored_raw.get("external_provider_api_called"),
        "trade_signal_count": signals,
    }
    required = [
        checks["claim_verifier_ok"], checks["trust_gate_ok"], checks["push_enabled"], not checks["pushed"],
        checks["structured_json_present"], not checks["stock_watch_present"], not checks["garbled_text"], checks["style_ok"],
        checks["fixed_section_template"] is False, checks["external_provider_api_called"] is False, signals == 0,
    ]
    if not all(required):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
