from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-09-01"
SLOT = "tw_close"
AUTOMATION_ID = "market-analysis-codex-guard-tw-close"
EVENT_IDS = [810814, 813528, 816258, 816370]

SUMMARY = """今天的收盤確認台股把盤前的高利率與能源疑慮暫時擺到第二順位，重新交易 AI 需求、電子權值與本地資金回補；也否定了前一日尾盤承接只是一日性技術反彈。加權指數開高走高，終場上漲820.25點、收46,948.72點，幾乎以全日最高作收。這不是風險消失，而是買盤目前願意用更高價格承擔風險，短線定價從防守轉為偏多。

## 資金把壓力推回場外

最直接的證據是價格、廣度與資金同向。上市股票上漲685家、下跌369家，三大法人買超561.38億元，成交值約1.08兆元。這組合比單靠權值股拉抬更有說服力：不只指數上漲，參與面也擴散，且法人由前一日賣方轉為買方，代表風險偏好確實修復。

第二條線索來自電子主軸。半導體類股上漲2.11%，電腦週邊上漲2.23%，台積電收2,440元、上漲1.45%。盤前已有 NVIDIA 與聯發科擴大合作的產業訊號，收盤則由先進製程、IC 設計、伺服器與高速傳輸等相關環節共同回應。市場交易的不是單一消息，而是 AI 算力需求仍能向台灣供應鏈延伸，足以暫時抵銷折現率偏高的壓力。

第三個重點是漲勢並非毫無分化。金融類股上漲1.44%，顯示資金並未只集中在高波動科技；但塑膠、生技與部分光電走弱，說明總經與產業成本疑慮沒有被全面消除。若油價維持高檔、長債殖利率再升，運輸、化工、耗能製造與高評價成長股仍可能重新承壓。

目前價格已反映電子權值回穩、AI 合作題材與法人回補，尚未完全確認的是這股買盤能否跨日延續。若後續法人持續站在買方、電子與非電子廣度保持均衡，且油價與殖利率沒有同步上行，今天可視為高檔整理後的再定價；反之，若量能快速萎縮、上漲家數明顯收窄，或油價與殖利率一起走高並壓回電子權值，今天接近最高點的收盤就可能只是事件驅動的短線擴張，偏多判斷應降級。"""


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
        "headline": "法人與電子廣度共振，台股收盤轉回偏多定價",
        "thesis": "台股收盤確認 AI 與本地資金回補暫時壓過利率、能源疑慮，但偏多判斷仍需跨日廣度驗證。",
        "sentiment": "cautiously_bullish",
        "confidence": "medium",
        "evidence": [
            {"role": "ai_taiwan_partnership", "event_id": 810814},
            {"role": "pre_open_cross_asset_risk", "event_id": 813528},
            {"role": "taiwan_close_price_breadth_sectors", "event_id": 816258},
            {"role": "institutional_net_buying", "event_id": 816370},
        ],
        "tw_sector_transmission": [
            {"sector": "先進製程、IC 設計、伺服器與高速傳輸", "mechanism": "AI 需求延伸與法人回補共同提高電子權值風險承擔"},
            {"sector": "金融", "mechanism": "資金擴散到非電子權值，使漲勢不只依賴單一科技主軸"},
            {"sector": "運輸、化工與耗能製造", "mechanism": "油價與利率若維持高檔，成本和評價壓力仍會回來"},
        ],
        "invalidation": [
            "法人買盤跨日延續且市場廣度維持",
            "量能快速萎縮或上漲家數明顯收窄",
            "油價與長債殖利率同步走高並壓回電子權值",
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
