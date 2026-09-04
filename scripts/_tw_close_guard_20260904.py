from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-09-04"
SLOT = "tw_close"
AUTOMATION_ID = "market-analysis-codex-guard-tw-close"
EVENT_IDS = [840330, 840343, 840350, 843325]

SUMMARY = """今天收盤確認台股重新接回美股成長股的風險偏好，也否定了昨天高檔轉弱會立即延伸成連續去風險的判斷。加權指數上漲693.47點、收46,551.13點，重新站上46,000點；成交值8,256.26億元，三大法人同步買超628.72億元，顯示反彈不只靠情緒，而有權值與機構資金共同承接。

## 反彈有資金背書，但估值門檻沒有消失

前一晚美股成長股代理指標上漲1.19%，替台灣電子權值提供正面起點。今天台股不但跟漲，還從早盤低點一路推升、終場接近盤中高檔；搭配法人轉為同步買超，市場短線交易的主軸已由降低曝險轉回AI與大型電子的獲利延續，而不是單純跌深反彈。

不過，這次風險偏好回升仍發生在美國10年期公債殖利率4.79%的環境，代表折現率壓力並未解除。油價也在高檔，WTI報91.81美元並上漲0.56%；這會透過運輸、化工與製造成本，限制非科技景氣循環股的評價空間。換句話說，台股今天確認的是資金願意重新承擔AI與權值電子風險，不是總體資金成本已經轉鬆。

對台灣產業的傳導因此呈現兩層。第一層是台積電、AI伺服器、PCB、散熱與高階零組件較容易承接美股成長股動能，金融與大型權值也因法人回補而改善指數穩定度；第二層則是高油價與高殖利率仍壓著塑化、運輸、內需及高負債公司的利潤或評價。若後續電子成交比重與上漲家數一起擴大，今天的反彈才有機會從權值拉抬變成較健康的市場廣度。

目前價格已重新反映美股成長動能與法人回補，尚未充分反映的是高利率、高油價能否持續而不傷害獲利預期。若指數守住46,000點、法人買盤延續，且電子以外族群逐步接棒，今天確認的風險偏好回升就能延續；若殖利率或油價再上行、法人迅速轉賣，或指數再次跌回46,000點下方，這個判斷就應降級為一日反彈。現階段較合理的結論是短線氣氛轉多，但總體限制仍在，不能把單日大漲等同於風險全面解除。"""


def safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def main() -> None:
    now_local = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now_local)
    if now_local.date().isoformat() != ANALYSIS_DATE or SLOT not in allowed_analysis_slots(calendar):
        raise RuntimeError("calendar does not allow today's tw_close")

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
        events = safe([dict(zip(columns, row)) for row in cursor.fetchall()])
    finally:
        cursor.close()
    if len(events) != len(EVENT_IDS):
        raise RuntimeError("required local evidence rows are missing")

    structured = {
        "schema_version": "codex-market-analysis-v1",
        "headline": "法人買盤接回美股成長動能，台股重返風險承擔",
        "thesis": "台股收盤確認美股成長股動能與法人買盤重新主導短線定價，但高利率與高油價仍限制評價擴張。",
        "sentiment": "cautiously_bullish",
        "confidence": "medium",
        "evidence": [
            {"role": "energy_cost_pressure", "event_id": 840330},
            {"role": "us_growth_equity_rebound", "event_id": 840343},
            {"role": "rates_valuation_constraint", "event_id": 840350},
            {"role": "taiwan_close_and_institutional_buying", "event_id": 843325},
        ],
        "tw_sector_transmission": [
            {"sector": "台積電、AI伺服器、PCB、散熱與高階零組件", "mechanism": "美股成長動能與法人回補提高大型電子承接力"},
            {"sector": "金融與大型權值", "mechanism": "機構資金回流改善指數穩定度，但殖利率波動仍影響評價"},
            {"sector": "塑化、運輸、內需與高負債企業", "mechanism": "高油價與高資金成本壓縮利潤及評價空間"},
        ],
        "invalidation": [
            "指數再次跌回46000點下方",
            "法人買盤迅速轉為賣超",
            "殖利率或油價續升且市場廣度收斂",
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
    found = [term for term in forbidden if term in SUMMARY]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", SUMMARY))
    style = {
        "ok": not found and not garbled,
        "template": "flexible-briefing-memo-v1",
        "garbled_text": garbled,
        "forbidden_terms": found,
        "fixed_section_template": False,
        "english_section_headings": False,
    }
    if not verifier["ok"] or not style["ok"]:
        raise RuntimeError(json.dumps({"claim_verifier": verifier, "style_checks": style}, ensure_ascii=False))

    raw = {
        "automation_id": AUTOMATION_ID,
        "generator": "codex_automation",
        "display_title": ANALYSIS_DATE,
        "calendar": calendar.to_dict(),
        "dimension": "daily_tw_close",
        "evidence_event_ids": EVENT_IDS,
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style,
        "external_provider_api_called": False,
    }
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=ANALYSIS_DATE, analysis_slot=SLOT, scheduled_time_local="15:30",
        model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0,
        push_enabled=False, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False),
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
        "push_enabled": bool(stored[1]), "pushed": bool(stored[2]),
        "structured_json_present": bool(stored_structured),
        "stock_watch_present": "stock_watch" in stored_structured,
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", str(stored[3]))),
        "style_ok": stored_raw.get("style_checks", {}).get("ok") is True,
        "fixed_section_template": stored_raw.get("style_checks", {}).get("fixed_section_template"),
        "external_provider_api_called": stored_raw.get("external_provider_api_called"),
        "trade_signal_count": signal_count,
    }
    required = [checks["claim_verifier_ok"], checks["trust_gate_ok"], not checks["push_enabled"],
        not checks["pushed"], checks["structured_json_present"], not checks["stock_watch_present"],
        not checks["garbled_text"], checks["style_ok"], checks["fixed_section_template"] is False,
        checks["external_provider_api_called"] is False, checks["trade_signal_count"] == 0]
    if not all(required):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
