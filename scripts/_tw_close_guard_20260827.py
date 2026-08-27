from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-08-27"
SLOT = "tw_close"
AUTOMATION_ID = "market-analysis-codex-guard-tw-close"
EVENT_IDS = [773052, 775834, 775895]

SUMMARY = """今天的台股收盤確認了 AI 獲利動能仍能吸引資金回流，但也否定了「財報超預期就足以推動指數單邊突破」的樂觀版本。加權指數早盤一度衝上46,401.78點，終場只上漲142.6點、收45,975.22點；三大法人買超643.07億元、成交值放大至9,246.83億元，顯示資金沒有撤退，卻在高檔明顯換手。今天較合理的解讀是偏多但分化，而不是全面追價。

## 好消息落地後，市場改看承接力

輝達最新一季營收達962.2億美元、年增106%，並提出1,080億美元的下一季營收展望，延續 AI 基礎建設需求仍強的敘事。這項訊號確實傳到台股早盤，但台積電尾盤翻黑、指數自高點收斂，表示財報利多已先被部分定價；接下來市場要驗證的不是需求故事是否存在，而是記憶體、先進封裝、伺服器與高速傳輸等供應鏈，能否把需求轉成更廣泛且可持續的獲利改善。

盤面廣度仍比單靠權值拉抬健康：集中與櫃買合計上漲1,027家、下跌822家，法人買盤也延續。這讓電子零組件、光電、PCB與部分傳產輪動有支撐，但權值股未能守住早盤強勢，提醒資金更像在題材間重新分配，而非毫無價格敏感度地擴張風險。金融與高評價科技還要面對美國十年期公債殖利率約4.66%的資金成本；利率沒有明顯下行前，基本面利多仍可能被估值壓力抵銷一部分。

目前已反映的是 AI 龍頭財報優於預期與法人回補，仍可能重估的是供應鏈獲利廣度及外部利率壓力。若後續成交維持、法人買盤延續，而且指數能縮小開高走低的落差，今天的收盤可視為利多換手後仍有承接；反之，若量能放大卻無法守住高點、權值與上漲家數同步轉弱，或長債殖利率再升，這個偏多判斷就應降級為財報事件帶動的短期輪動。"""


def json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def main() -> None:
    now_local = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now_local)
    if now_local.date().isoformat() != ANALYSIS_DATE or SLOT not in allowed_analysis_slots(calendar):
        raise RuntimeError(f"calendar does not allow {ANALYSIS_DATE} {SLOT}")

    store = MySqlEventStore(load_settings(".env"))
    store.initialize()
    cur = store._cursor()
    try:
        placeholders = ",".join(["%s"] * len(EVENT_IDS))
        cur.execute(
            f"SELECT id,event_id,source,title,summary,published_at,created_at,raw_json "
            f"FROM t_relay_events WHERE id IN ({placeholders}) ORDER BY id",
            tuple(EVENT_IDS),
        )
        columns = ["id", "event_id", "source", "title", "summary", "published_at", "created_at", "raw_json"]
        events = json_safe([dict(zip(columns, row)) for row in cur.fetchall()])
    finally:
        cur.close()
    if len(events) != len(EVENT_IDS):
        raise RuntimeError("required local evidence rows are missing")

    structured = {
        "schema_version": "codex-market-analysis-v1",
        "headline": "AI 利多有承接，早盤突破未獲收盤確認",
        "thesis": "台股確認 AI 財報利多與法人回補仍有支撐，但高檔換手、權值收斂及長債利率限制全面追價。",
        "sentiment": "cautious_positive",
        "confidence": "medium_high",
        "evidence": [
            {"role": "taiwan_close_flow_and_breadth", "event_id": 775834},
            {"role": "ai_earnings_demand", "event_id": 775895},
            {"role": "long_rate_constraint", "event_id": 773052},
        ],
        "tw_sector_transmission": [
            {"sector": "記憶體、先進封裝、伺服器、高速傳輸", "mechanism": "AI 需求與財測支撐訂單預期，但需由供應鏈獲利廣度確認"},
            {"sector": "金融與高評價科技", "mechanism": "長債殖利率維持高檔，限制評價擴張空間"},
        ],
        "invalidation": [
            "量能放大但指數持續無法守住高點",
            "法人買盤中斷且市場廣度轉弱",
            "長債殖利率再升並壓抑高評價科技",
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

    verify_cur = store._cursor()
    try:
        verify_cur.execute(
            "SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json "
            "FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s",
            (ANALYSIS_DATE, SLOT),
        )
        stored = verify_cur.fetchone()
        verify_cur.execute("SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s", (row_id,))
        signal_count = int(verify_cur.fetchone()[0])
    finally:
        verify_cur.close()
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
    required = [
        checks["claim_verifier_ok"], checks["trust_gate_ok"], not checks["push_enabled"],
        not checks["pushed"], checks["structured_json_present"], not checks["stock_watch_present"],
        not checks["garbled_text"], checks["style_ok"], checks["fixed_section_template"] is False,
        checks["external_provider_api_called"] is False, checks["trade_signal_count"] == 0,
    ]
    if not all(required):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
