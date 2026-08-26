from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-08-27"
SLOT = "us_close"
AUTOMATION_ID = "market-analysis-codex-guard-us-close"
EVENT_IDS = [770664, 772083, 772084, 772093]

SUMMARY = """美股收盤帶給台灣投資人的新訊號，不是風險資產已經轉空，而是通膨黏性與 AI 獲利驗證同時壓縮了市場願意追價的空間。三大指數小幅收低，顯示資金仍留在場內等待答案；台股今天較可能維持大型電子權值支撐、但族群分化加深的格局，最大的變數是 AI 龍頭財報能否抵銷利率與成本壓力。

## 等財報，也等通膨降溫

道瓊收在約五萬三千四百六十四點、下跌約百分之零點二一，標普五百收在約七千六百七十六點，市場報導並指出三大指數均小幅收低。這種幅度比較像事件前的風險收斂，而不是全面撤出；但當市場把注意力集中在 NVIDIA 財報，高評價 AI 資產就必須靠營收、資本支出與獲利展望繼續證明溢價。

通膨端沒有提供明顯舒緩。七月美國整體消費者物價年增約百分之三點三，核心年增約百分之二點四七。整體通膨高於核心，代表能源或其他波動項目仍可能干擾降息路徑；即使核心壓力相對低，利率快速下行的空間仍容易被重新評估。對台股而言，這會讓長天期評價敏感的電子成長股更依賴財報兌現，而非單純享受折現率下降。

另一條成本線索來自消費性科技產品：本地消息顯示記憶體等零組件短缺推升成本，部分終端產品準備大幅調價。單一產品調價不能代表整個科技循環，但它提醒市場，AI 伺服器需求強勁與消費電子承壓可以同時存在。台灣傳導因此不是「電子全面受惠」，而是先看 AI 伺服器、先進半導體與大型權值能否延續訂單能見度，再看記憶體、組裝與消費裝置供應鏈能否把成本轉嫁出去。

目前價格已反映市場願意等待 AI 財報，尚未充分反映的則是通膨黏性若延長高利率、同時零組件漲價侵蝕終端需求的組合風險。若 NVIDIA 財報與展望帶動成長股重新放量、後續通膨回落，且消費電子調價沒有壓低需求，這個「權值撐盤但追價空間收窄」的判斷就應降級；反之，若財測不及市場期待或利率預期再上修，台股高評價電子與成本轉嫁能力較弱的供應鏈會先面臨重新定價。"""


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
            "FROM t_relay_events WHERE id IN (%s,%s,%s,%s) ORDER BY id",
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
        "headline": "通膨與 AI 財報夾擊追價空間",
        "thesis": "美股小幅收低反映事件前觀望；台股大型電子仍有支撐，但通膨與成本壓力使族群分化加深。",
        "sentiment": "cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close_and_ai_earnings_focus", "event_id": 772093},
            {"role": "us_headline_cpi", "event_id": 772083},
            {"role": "us_core_cpi", "event_id": 772084},
            {"role": "consumer_technology_cost_pressure", "event_id": 770664},
        ],
        "tw_sector_transmission": [
            {"sector": "AI 伺服器、先進半導體與大型電子權值", "mechanism": "財報與資本支出展望決定高評價能否延續"},
            {"sector": "記憶體、組裝與消費裝置供應鏈", "mechanism": "零組件成本上升考驗終端需求與成本轉嫁"},
        ],
        "invalidation": [
            "NVIDIA 財報與展望帶動成長股重新放量",
            "後續通膨持續回落",
            "消費電子調價未壓低終端需求",
        ],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[]
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
        "market_snapshot_rows": 0,
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
        market_rows_used=0,
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
        checks["claim_verifier_ok"], checks["trust_gate_ok"], not checks["push_enabled"],
        not checks["pushed"], checks["structured_json_present"], not checks["garbled_text"],
        checks["style_ok"], checks["fixed_section_template"] is False,
        checks["external_provider_api_called"] is False, checks["trade_signal_count"] == 0,
    ]):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
