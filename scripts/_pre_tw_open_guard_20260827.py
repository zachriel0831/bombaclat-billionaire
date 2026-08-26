from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-08-27"
SLOT = "pre_tw_open"
AUTOMATION_ID = "market-analysis-codex-guard-pre-open"
EVENT_IDS = [772979, 772999, 773014, 773025]

SUMMARY = """市場目前交易的是「景氣與 AI 動能仍撐住風險偏好，但高利率不允許評價無限擴張」。台股盤前基調中性偏多，較有利大型電子權值與 AI、先進半導體鏈穩住指數；最大不確定性仍是 AI 龍頭財報能否接住市場期待，以及長債殖利率會不會再往上重估。

## 風險偏好還在，追價需要獲利兌現

費城半導體指數最新上漲約百分之零點二，顯示資金沒有在重要財報前全面撤離科技鏈；但漲幅有限，也代表市場已先反映一部分 AI 成長敘事，接下來必須靠訂單、資本支出與獲利展望證明高評價。這對台股的直接傳導是大型電子與先進製程仍有撐盤能力，但題材擴散到所有零組件的力道可能不平均。

另一端，美國十年期公債殖利率仍在百分之四點六六。這個水準會持續抬高長久期成長股的折現壓力，使半導體利多更依賴基本面，而不是單靠資金成本下降。同時，美國高收益債利差約百分之二點七，信用市場尚未顯示明顯避險壓力；兩者放在一起看，比較像「金融條件偏緊但未失控」，不是景氣衰退交易全面升溫。

油價則提供一點成本緩衝：西德州原油最新約八十三點九美元、較前值下跌約百分之二點八三。若跌勢延續，運輸、塑化下游與一般製造的成本壓力可略為舒緩，也降低能源再度推升通膨的迫切性；不過目前油價絕對水準仍不低，還不足以單獨扭轉利率判斷。

台股今天較合理的解讀不是電子全面轉強，而是權值半導體先承接美國科技風險偏好，金融與傳產則分別消化高利率和能源成本變化。價格已反映信用風險受控與 AI 需求仍強，尚未充分反映的是財報若只符合、沒有超越期待，以及殖利率再上行對評價的壓縮。

如果後續 AI 財報與展望明顯優於預期、半導體漲勢擴散，同時十年期殖利率回落，這個「中性偏多但追價受限」的判斷就應轉強；反過來，若半導體轉跌、信用利差擴大或長債殖利率續升，代表資金開始從等待驗證轉向降低風險，台股權值支撐也會變得不可靠。"""


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
        "headline": "風險偏好未斷，高利率限制追價",
        "thesis": "台股中性偏多，AI 與大型電子權值仍有支撐，但高利率使評價必須靠獲利兌現。",
        "sentiment": "cautiously_bullish",
        "confidence": "medium",
        "evidence": [
            {"role": "semiconductor_risk_appetite", "event_id": 772979},
            {"role": "long_rate_valuation_pressure", "event_id": 772999},
            {"role": "credit_stress_contained", "event_id": 773014},
            {"role": "oil_cost_relief", "event_id": 773025},
        ],
        "tw_sector_transmission": [
            {"sector": "AI、先進半導體與大型電子權值", "mechanism": "美國科技風險偏好提供支撐，但高殖利率要求獲利兌現"},
            {"sector": "金融、運輸、塑化下游與一般製造", "mechanism": "分別消化高利率與油價回落帶來的成本變化"},
        ],
        "invalidation": [
            "半導體轉跌且風險偏好未能擴散",
            "美國高收益債利差明顯擴大",
            "十年期公債殖利率續升並壓縮成長股評價",
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
        market_rows_used=4,
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
        "stock_watch_present": "stock_watch" in stored_structured,
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", stored_summary)),
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
