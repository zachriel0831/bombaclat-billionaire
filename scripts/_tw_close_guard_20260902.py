from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-09-02"
SLOT = "tw_close"
AUTOMATION_ID = "market-analysis-codex-guard-tw-close"
EVENT_IDS = [821996, 822157, 823925, 824507, 825024]

SUMMARY = """今天收盤確認，昨夜由中東衝突、油價與公債殖利率升高引發的風險降溫，已完整傳到台股；同時否定了前一日大漲後，電子權值與法人買盤可以立刻延續的判斷。加權指數開低走低，收在46,164.72點、下跌784點，且以全日低點作收。這種收法代表市場不是單純消化獲利，而是重新提高能源、利率與地緣風險的折價。

## 昨天的回補，今天被外部壓力反轉

最強的一條證據是跨市場方向一致：美股四大指數收黑，費城半導體指數下跌逾2%，同時油價上升、公債遭到拋售。對台灣而言，這會一面壓低高評價科技股的折現空間，一面抬高運輸、化工與耗能製造的成本預期。台股終場跌1.66%、成交量約9,184億元，並從盤中高點一路滑到最低點，顯示賣壓沒有在尾盤被承接回去。

第二條線索是權值與資金同步轉弱。台積電收2,385元、下跌2.25%，三大法人合計賣超1,150.33億元，外資、投信與自營商同站賣方。權值股下跌本來就會放大指數跌幅，但法人一致減碼，讓今天的訊號不宜只解讀成單一權值股拖累；市場正在回收昨天為 AI 與電子供應鏈付出的部分風險溢價。

匯率也沒有提供緩衝。新台幣收31.726元、貶9.3分，與股市和法人賣壓同向，反映資金面偏向防守。這對出口商的換匯利益可能較有支撐，卻不足以抵銷半導體評價下修；金融、傳產與內需族群也會分別承受債券評價、能源成本及市場風險偏好降溫的影響。

目前價格已快速反映費半回落、台積電壓力與法人賣超，但尚未確認這是短期風險事件，還是高檔趨勢開始轉弱。若油價與長債殖利率停止同步上行、法人賣壓明顯收斂，且電子權值不再收於低點，今天的跌勢較可能是急速重定價；反之，若匯率續貶、法人連續大幅賣超，並伴隨半導體與非電子族群同步縮弱，則昨天的反彈將更像一次性回補，盤勢應繼續以防守解讀。"""


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
        "headline": "外部利率與能源壓力傳入，台股回吐前日風險溢價",
        "thesis": "收盤確認全球油價、殖利率與半導體壓力已傳到台股，前一日的風險偏好修復未能延續。",
        "sentiment": "cautiously_bearish",
        "confidence": "medium",
        "evidence": [
            {"role": "global_rates_oil_semiconductor_pressure", "event_id": 821996},
            {"role": "pre_open_cross_asset_context", "event_id": 822157},
            {"role": "taiwan_fx_close", "event_id": 823925},
            {"role": "taiwan_price_close", "event_id": 824507},
            {"role": "institutional_selling", "event_id": 825024},
        ],
        "tw_sector_transmission": [
            {"sector": "半導體與電子權值", "mechanism": "費半回落與殖利率升高壓低高評價科技股的風險承擔"},
            {"sector": "運輸、化工與耗能製造", "mechanism": "油價上升提高成本與通膨預期"},
            {"sector": "金融、傳產與內需", "mechanism": "債券評價、匯率與風險偏好降溫造成不同程度壓力"},
        ],
        "invalidation": [
            "油價與長債殖利率停止同步上行",
            "法人賣壓明顯收斂且電子權值不再收於低點",
            "匯率續貶、法人連續大幅賣超並伴隨市場廣度縮弱",
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
    stored_raw = json.loads(stored[4]); stored_structured = json.loads(stored[5])
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
