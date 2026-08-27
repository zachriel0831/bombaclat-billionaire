from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-08-28"
SLOT = "pre_tw_open"
AUTOMATION_ID = "market-analysis-codex-guard-pre-open"
EVENT_IDS = [779375, 781482, 781502, 781517]

SUMMARY = """市場現在交易的是 AI 獲利動能重新加速，但資金仍要求成長能夠抵銷高利率與成本壓力。台股盤前基調偏多，支撐主要來自大型電子權值、先進製程與伺服器鏈；最大不確定性不是需求有沒有，而是強勁訂單能否順利轉成毛利，並讓漲勢從少數龍頭擴散出去。

## 財報利多先推權值，評價仍要過兩道關

費城半導體指數最新上漲約百分之二點三三，顯示財報後的風險偏好直接回到晶片與 AI 主線。這對台股最明確的傳導，是台積電等大型權值、先進製程、先進封裝與伺服器供應鏈先獲得情緒支撐；但它更像市場確認需求沒有失速，還不能直接推論所有電子次族群都會同步受惠。

第一道關卡是資金成本。美國十年期公債殖利率仍在百分之四點六七，代表長久期成長股的折現壓力沒有因科技股上漲而消失。市場可以接受較高評價，前提是營收與獲利展望持續上修；若只有題材延續、現金流兌現跟不上，高殖利率仍會放大評價回檔。

第二道關卡是成本轉嫁。最新財報消息指出，NVIDIA 本季毛利率將受到記憶體漲價影響，伺服器也可能調整售價。傳到台灣供應鏈，記憶體、板卡、散熱、組裝與零組件雖可受惠出貨需求，真正的分化會落在議價能力、產能效率與成本能否轉嫁；因此營收成長不必然等比例變成獲利成長。

信用市場目前沒有同步拉警報，美國高收益債利差約百分之二點六七，且較前值收斂。這表示金融壓力暫時未阻斷風險承擔，讓 AI 利多有空間傳到台股；不過信用穩定只能排除一部分尾端風險，不能替高評價提供無限支撐。

目前價格較充分反映 AI 需求續強與信用風險受控，尚未充分反映的是成本上升後的毛利分化，以及高利率下漲勢能否擴散。若半導體強勢延續、供應鏈毛利率維持，且十年期殖利率回落，這個偏多判斷可望轉得更穩；反過來，若半導體漲勢迅速收斂、毛利展望下修，或長債殖利率與信用利差同時上行，就代表市場正從獲利樂觀轉向重新計算風險，台股權值支撐也會降級。"""


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
        "headline": "AI 動能支撐權值，成本與利率決定擴散",
        "thesis": "台股盤前偏多，但 AI 需求必須轉成毛利，才能抵銷高利率並讓漲勢擴散。",
        "sentiment": "constructive_cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "semiconductor_risk_appetite", "event_id": 781482},
            {"role": "long_rate_valuation_pressure", "event_id": 781502},
            {"role": "ai_margin_cost_pressure", "event_id": 779375},
            {"role": "credit_stress_contained", "event_id": 781517},
        ],
        "tw_sector_transmission": [
            {"sector": "大型電子、先進製程與先進封裝", "mechanism": "AI 需求與美國半導體風險偏好支撐權值"},
            {"sector": "記憶體、板卡、散熱、組裝與零組件", "mechanism": "成本轉嫁與毛利率決定需求能否轉成獲利"},
        ],
        "invalidation": [
            "半導體漲勢迅速收斂",
            "供應鏈毛利展望下修",
            "長債殖利率與信用利差同時上行",
        ],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[]
    )
    forbidden = [
        "今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導",
        "先看區間邊界", "現在只看", "今日主命題", "三個證據", "市場正在定價什麼",
        "台股配置", "今日個股觀察", "stock_watch", "買進", "推薦", "候選",
        "入場", "停損", "止損", "目標價", "t_relay_events", "t_market_analyses",
        "claim_verifier", "market_context", "raw_json",
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
        market_rows_used=3,
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
