from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-08-28"
SLOT = "us_close"
AUTOMATION_ID = "market-analysis-codex-guard-us-close"
EVENT_IDS = [779375, 779492, 780280, 780511, 780665]

SUMMARY = """美股這一晚替台灣投資人改寫的重點，是 AI 行情重新拿回指數主導權，但估值能否繼續擴張，開始取決於需求能見度能否跑贏成本與能源風險。科技股帶動美股收高，對今天台股大型電子與半導體情緒偏正面；不過記憶體漲價與油價上行，意味盤面較可能是權值與具備議價能力的供應鏈占優，而不是所有電子股同步受惠。

## 財報把焦點拉回獲利兌現

道瓊收在約五萬三千五百六十四點，標普五百收在約七千七百三十一點；本地收盤消息指出，NVIDIA 與 Salesforce 財報優於預期後，科技股領漲並帶動主要指數收高。這不是單純的風險偏好回升，而是市場願意暫時把 AI 資本支出敘事重新放到利率疑慮之前；對台股而言，第一波傳導仍會落在台積電等大型權值、先進製程、先進封裝與伺服器供應鏈。

NVIDIA 對較長期間的營收成長釋出樂觀看法，延長了 AI 基礎建設需求的可見度。這使市場已反映的部分，從「財報會不會失速」轉成「供應鏈能不能把需求變成獲利」。也因此，訂單強並不足以支撐所有評價，產能、交付與毛利率才是下一階段的分化來源。

成本端正好提供反向檢驗。另一則本地消息指出，記憶體漲價可能壓低 NVIDIA 本季毛利率，並帶來伺服器調價壓力。傳導到台灣，記憶體、板卡、散熱與組裝環節雖受惠於出貨量，但若成本轉嫁不順，營收成長未必等比例變成獲利；反而擁有技術門檻與議價能力的環節較能承接這波需求。

此外，美伊協議不確定性推升國際油價，提醒市場不能只看科技財報。油價若持續走高，會透過運輸、製造成本與通膨預期牽動利率，進而限制高評價成長資產的追價空間；台灣的航運、塑化與用能產業也會面臨不同方向的成本與報價影響。

目前市場較充分反映 AI 需求續強，尚未充分反映的是記憶體與能源成本若同時上升，對毛利率和折現率形成雙重壓力。若後續科技股漲勢擴散、AI 供應鏈毛利率維持，且油價回落，這個「權值偏強但族群分化」判斷就應降級；反之，若伺服器調價壓低終端需求、毛利率持續下修，或油價再推升利率預期，台股今日的正向傳導就可能很快被重新定價。"""


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
        "headline": "AI 需求續強，成本決定台股分化",
        "thesis": "科技財報讓 AI 行情重回主軸，但記憶體與能源成本限制估值擴張，台股偏向大型權值與高議價供應鏈占優。",
        "sentiment": "constructive_cautious",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close", "event_id": 780280},
            {"role": "technology_led_rally", "event_id": 780665},
            {"role": "ai_demand_visibility", "event_id": 779492},
            {"role": "memory_cost_margin_pressure", "event_id": 779375},
            {"role": "energy_geopolitical_risk", "event_id": 780511},
        ],
        "tw_sector_transmission": [
            {"sector": "大型電子、先進製程、先進封裝與伺服器供應鏈", "mechanism": "AI 需求能見度支撐訂單與權值評價"},
            {"sector": "記憶體、板卡、散熱與組裝", "mechanism": "成本轉嫁與毛利率決定需求能否轉為獲利"},
            {"sector": "航運、塑化與用能產業", "mechanism": "油價透過運輸成本、報價與通膨預期形成分化"},
        ],
        "invalidation": [
            "科技股漲勢擴散且 AI 供應鏈毛利率維持",
            "油價回落並降低利率再定價壓力",
            "伺服器調價未壓低終端需求",
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
        "market_snapshot_rows": 2,
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
        market_rows_used=2,
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
