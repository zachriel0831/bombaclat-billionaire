from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-08-25"
SLOT = "tw_close"
AUTOMATION_ID = "market-analysis-codex-guard-tw-close"
EVENT_IDS = [759552, 759553, 759555, 759574]

SUMMARY = """今天的台股收盤確認了低檔承接與大型權值的韌性，卻沒有確認風險偏好已全面回來。指數盤中一度重挫逾500點，終場反而上漲407.14點、漲幅0.91%，但三大法人仍賣超53.36億元；這種價格轉強、法人未同步轉買的組合，比較像劇烈震盪後的回補與選擇性承接，而不是資金無條件追價。最大變數仍是美國長債與地緣風險會不會把折現率重新推高。

## 尾盤拉回來，廣度仍要再確認

台股由低點一路拉抬逾900點，收在45,169.46點，成交量略增至6,960.55億元。這證明月線附近有買盤願意接手，也讓電子、金融與塑化能在收盤前改善；不過，同一天美國科技股承壓，費城半導體指數下跌2.7%，顯示全球資金對高評價科技的要求正在提高。台股能逆著外部科技壓力收紅，是相對強勢，但若缺少法人回流與產業廣度配合，還不能直接外推為新一輪全面多頭。

另一條壓力來自利率與地緣政治。美國擴大長天期公債回購，只能暫時緩和債市緊張；若財政疑慮持續，長債殖利率仍可能抬高成長股的折現率。美國對伊朗加強經濟施壓，加上美加貿易摩擦，也可能先反映在能源、運輸與美元，再傳到企業成本與風險溢價。這使今日的尾盤反攻更像市場拒絕立即恐慌，尚不是對外部風險解除警報。

傳到台灣產業，半導體與AI供應鏈仍有出口與需求主線支撐，但市場已開始區分能把需求轉成訂單、獲利與現金流的環節，和只靠遠期想像撐估值的題材。台積電等大型權值可以穩住指數，伺服器、零組件與製造服務則要看後續訂單是否擴散；金融股對長債波動與資金成本更敏感，塑化、航運及航空則分別承受能源價格與運價變化，不能把同一個地緣事件解讀成一致利多或利空。

目前收盤已反映低檔有人承接，尚未完全反映的是長債壓力、能源風險與法人籌碼能否改善。若接下來法人轉為連續買超、科技與非科技族群同步擴散，且美債殖利率與能源價格沒有一起上行，今日收盤就可升級為較廣泛的風險偏好回升；反之，若指數再度跌破本次盤中防線、費半弱勢延續，或美元、油價與長債殖利率同步走高，「韌性大於全面轉強」仍是較穩健的解讀。"""


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
        "headline": "尾盤韌性獲確認，廣泛風險偏好仍待驗證",
        "thesis": "台股拒絕盤中恐慌，但法人籌碼與外部科技、利率壓力尚未確認全面轉強。",
        "sentiment": "cautious_positive",
        "confidence": "medium",
        "evidence": [
            {"role": "taiwan_close_reversal_and_flow", "event_id": 759553},
            {"role": "semiconductor_and_geopolitical_pressure", "event_id": 759552},
            {"role": "us_long_bond_liquidity", "event_id": 759555},
            {"role": "taiwan_ai_export_cycle", "event_id": 759574},
        ],
        "tw_sector_transmission": [
            {"sector": "半導體、AI伺服器與電子零組件", "mechanism": "需求主線仍在，但外部科技弱勢與折現率提高估值門檻"},
            {"sector": "金融、塑化、航運與航空", "mechanism": "長債、能源與運價對資金成本和營運成本形成不同方向的影響"},
        ],
        "invalidation": [
            "法人轉為連續買超且產業廣度擴散",
            "美債殖利率與能源價格未同步上行",
            "費城半導體指數弱勢沒有延續",
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

    verify_cursor = store._cursor()
    try:
        verify_cursor.execute(
            "SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json FROM t_market_analyses "
            "WHERE analysis_date=%s AND analysis_slot=%s",
            (ANALYSIS_DATE, SLOT),
        )
        stored = verify_cursor.fetchone()
        verify_cursor.execute("SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s", (row_id,))
        signal_count = int(verify_cursor.fetchone()[0])
    finally:
        verify_cursor.close()
    if not stored:
        raise RuntimeError("analysis row missing after upsert")

    stored_raw = json.loads(stored[4])
    stored_structured = json.loads(stored[5])
    stored_summary = str(stored[3])
    checks = {
        "analysis_id": int(stored[0]),
        "claim_verifier_ok": stored_raw.get("claim_verifier", {}).get("ok") is True,
        "claim_support_rate": stored_raw.get("claim_verifier", {}).get("support_rate"),
        "trust_gate_ok": stored_raw.get("trust_gate", {}).get("ok") is True,
        "trust_gate_reason": stored_raw.get("trust_gate", {}).get("reason"),
        "push_enabled": bool(stored[1]),
        "pushed": bool(stored[2]),
        "structured_json_present": bool(stored_structured),
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", stored_summary)),
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
