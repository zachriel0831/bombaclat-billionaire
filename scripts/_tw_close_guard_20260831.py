from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-08-31"
SLOT = "tw_close"
AUTOMATION_ID = "market-analysis-codex-guard-tw-close"
EVENT_IDS = [806191, 806194, 808546, 808597]

SUMMARY = """今天的收盤確認了美股半導體修正、利率偏鷹與能源風險確實壓低台股評價，但也否定了盤中重挫會直接演變成全面失速。加權指數盤中一度下跌881.24點，終場跌幅收斂至202.98點、收46,128.47點；這種大幅拉回代表低檔仍有承接，只是三大法人賣超267.56億元，顯示大型資金尚未回到主動承擔風險的狀態。今天比較合理的結論不是轉多，而是恐慌定價被修正成高檔震盪。

## 尾盤收復失土，資金仍在防守

第一條證據來自外部科技評價。前一個美股交易日費城半導體指數下跌約百分之三點四七，台股盤中電子權值同步承壓，說明高利率與成長股折現壓力已經傳入台灣。AI 與先進封裝需求並沒有因此消失，但市場開始更嚴格區分訂單能見度、毛利與現金流，半導體、伺服器與零組件不再容易全面同漲。

第二條證據是台股自身的價格與資金結構。指數從盤中低點明顯收斂跌幅，代表逢低承接存在；然而法人仍站在賣方，且成交值放大至約1.2兆元。由於今天同時有 MSCI 季度調整生效，量能包含被動資金換股，不能單純解讀成新一輪風險偏好回升。大型電子能否穩住仍決定指數彈性，金融與高股息資產則較像波動期間的資金停泊處，而不是成長主線已經換手完成。

第三條壓力來自能源。西德州原油盤前資料約每桶84.86美元、單日上漲約百分之一點七五；若能源價格維持高檔，會透過通膨預期與長債殖利率提高科技股評價門檻，也會增加航空、運輸與耗能製造的成本。對台灣而言，這使 AI 訂單支撐與折現率壓力同時存在，盤面較可能維持產業內部分化。

目前價格已反映部分費半回檔與政策偏鷹風險，尚未確認的是尾盤承接能否變成連續買盤。若後續法人賣壓縮小、電子族群廣度改善，且油價與長債殖利率回落，今天可重新解讀為高檔洗盤；反之，若指數再度跌破盤中承接區、法人賣超延續，或油價與殖利率同步走高，尾盤收斂就只是被動調整與短線回補，整體判斷應轉向更保守。"""


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
        "headline": "外部壓力獲確認，尾盤承接避免全面失速",
        "thesis": "台股收盤確認科技評價與能源壓力，但盤中跌幅大幅收斂，較像高檔震盪而非全面失速。",
        "sentiment": "neutral_cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "us_semiconductor_valuation_pressure", "event_id": 806191},
            {"role": "energy_inflation_pressure", "event_id": 806194},
            {"role": "taiwan_close_recovery_and_flow", "event_id": 808546},
            {"role": "institutional_net_selling", "event_id": 808597},
        ],
        "tw_sector_transmission": [
            {"sector": "大型電子、半導體與 AI 供應鏈", "mechanism": "需求支撐仍在，但高利率提高評價與獲利驗證門檻"},
            {"sector": "金融與高股息資產", "mechanism": "波動期間承接防守資金，但尚不能證明主線換手"},
            {"sector": "航空、運輸與耗能製造", "mechanism": "油價高檔透過成本與通膨利率預期形成壓力"},
        ],
        "invalidation": [
            "法人賣壓縮小且電子族群廣度改善",
            "油價與長債殖利率同步回落",
            "指數再度跌破盤中承接區且法人賣超延續",
        ],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY,
        structured_payload=structured,
        events_payload=events,
        market_payload=[],
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
        "dimension": "daily_tw_close",
        "evidence_event_ids": EVENT_IDS,
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style_checks,
        "external_provider_api_called": False,
    }
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=ANALYSIS_DATE,
        analysis_slot=SLOT,
        scheduled_time_local="15:30",
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
            "WHERE analysis_date=%s AND analysis_slot=%s", (ANALYSIS_DATE, SLOT),
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
        checks["claim_verifier_ok"], checks["trust_gate_ok"], not checks["push_enabled"],
        not checks["pushed"], checks["structured_json_present"], not checks["stock_watch_present"],
        not checks["garbled_text"], checks["style_ok"], checks["fixed_section_template"] is False,
        checks["external_provider_api_called"] is False, checks["trade_signal_count"] == 0,
    ]):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
