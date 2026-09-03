from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-09-03"
SLOT = "tw_close"
AUTOMATION_ID = "market-analysis-codex-guard-tw-close"
EVENT_IDS = [829574, 834134, 834136, 834220]

SUMMARY = """今天收盤否定了盤前「美股回穩可帶動台股權值電子承接」的偏正面假設，也確認高檔市場對利率與科技股估值壓力仍很敏感。加權指數終場下跌307.06點、收45,857.66點，跌破46,000點；成交值放大至9,462.71億元，代表這不是量縮整理，而是資金在震盪中主動降低部分風險曝險。

## 美股回穩，沒有換來台股續彈

昨夜標普500與道瓊都由開盤位置回升，本來替亞洲科技股提供情緒支撐；但台股盤中從46,517.45點回落至45,839.36點附近，終場接近低檔，顯示海外股指止穩不足以抵銷本地高檔獲利了結與估值壓力。更關鍵的是三大法人合計賣超637.12億元，只有投信小幅回補，說明權值股局部走強並未改變整體資金偏防守的方向。

第二條證據來自跨市場定價。全球債券殖利率升至近20年高點的消息，意味企業融資與股票折現率仍受壓；同日日本市場也由AI相關類股下跌拖累日經指數收黑。兩者放在一起看，市場不是否定AI需求，而是提高對高評價科技股獲利兌現與資本效率的要求。台灣的傳導因此集中在半導體、PCB、載板與高本益比電子：訂單能見度仍重要，但題材本身已不足以抵消利率與籌碼壓力。

盤面也顯示資金沒有單純撤離所有大型股。台積電、聯發科與部分金控相對有撐，指數卻仍失守整數關卡，賣壓落在部分記憶體、塑化、光學及電子零組件。這種結構比較像高檔輪動失衡，而非景氣訊號全面翻空；金融股的相對支撐則要同時面對債券評價波動，不能直接視為風險已解除。

目前價格已反映短線科技股降溫與法人賣壓，尚未確認的是這次回落會不會擴大成趨勢性去風險。若殖利率停止上行、法人賣超快速收斂，且指數重新站回46,000點並由電子類股擴大市場廣度，今天的弱勢判斷就應降級；反之，若成交維持高檔、指數反彈無法收復關卡，亞洲AI鏈也持續同步走弱，市場將進一步重估高評價供應鏈。眼前較可信的結論是風險偏好轉弱，但還不是景氣反轉的充分證據。"""


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
        "headline": "美股回穩未能延續，台股高檔轉向風險重估",
        "thesis": "台股收盤否定盤前偏正面承接假設，確認利率、科技估值與法人賣壓重新主導高檔定價。",
        "sentiment": "cautiously_bearish",
        "confidence": "medium",
        "evidence": [
            {"role": "us_close_recovery", "event_id": 829574},
            {"role": "taiwan_close_and_institutional_selling", "event_id": 834134},
            {"role": "global_bond_yield_pressure", "event_id": 834136},
            {"role": "asia_ai_equity_weakness", "event_id": 834220},
        ],
        "tw_sector_transmission": [
            {"sector": "半導體、PCB、載板與高本益比電子", "mechanism": "殖利率與亞洲科技股轉弱提高估值與獲利兌現門檻"},
            {"sector": "記憶體、塑化、光學與電子零組件", "mechanism": "高檔輪動失衡與法人降風險使賣壓集中"},
            {"sector": "大型權值與金融", "mechanism": "局部支撐降低指數跌幅，但債券評價與資金流仍限制擴散"},
        ],
        "invalidation": [
            "殖利率停止上行且法人賣超快速收斂",
            "指數重新站回46000點並由電子類股擴大市場廣度",
            "成交維持高檔且亞洲AI鏈持續同步走弱",
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
