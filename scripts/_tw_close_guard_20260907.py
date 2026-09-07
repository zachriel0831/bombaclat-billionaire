"""Store Codex-authored local briefing; default dry-run, --write persists."""
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

DATE = "2026-09-07"
IDS = [866307, 866323, 867174, 867431]
SUMMARY = """今天收盤後，仍不能確認台股已把早盤的電子股強勢轉成全天站穩的行情。上午報導呈現半導體帶動的風險偏好回升，但目前可核對的資訊缺少最終指數、成交值與法人買賣超，因此今天的判斷只能停在「科技題材獲得盤中承接」，尚不能升級為收盤確認全面轉強。

上午台股一度來到47,294.36點，台積電等大型半導體帶頭，買盤並向PCB與被動元件擴散。這條線索支持電子供應鏈的情緒改善：權值先帶動指數，相關零組件若持續有資金承接，才可能把少數大型股的漲勢擴展成較有廣度的行情。不過，早盤高點本身無法說明午後是否留住買盤，也不能替代收盤成交與漲跌家數。

總體條件仍需分開看。最近可用的聯準會政策利率上限為3.75%，只能作為既有資金成本背景，不能解讀成今天已出現寬鬆轉向；盤前西德州原油報價為91.48美元，對台灣運輸、石化下游與製造業仍是成本敏感因素。若油價再走高，企業能否轉嫁成本，以及通膨是否延後利率下行，會共同影響電子成長股的評價與非電子產業的利潤。這是風險傳導的條件推論，並非已確認今天收盤由油價主導。

法人資金也暫時不能替行情背書：目前的三大法人查詢沒有可用買賣超結果，不能把空資料視為零買賣超，更不能推定外資正在回補。盤中報價已呈現對半導體與零組件的樂觀反應；這份樂觀是否持久，仍取決於收盤承接、成交廣度及後續資金流能否相互印證。

若後續確認電子強勢保留到收盤、上漲範圍擴大且法人資金同向，才有理由提高對台灣科技鏈風險偏好的評估；若只是早盤衝高、尾盤回吐，或油價與資金成本壓力升高並伴隨電子廣度收縮，就應撤回「題材有持續承接」的假設。現階段保留判斷，比用上午行情替全天收盤下結論更符合證據。"""
STRUCTURED = {
    "schema_version": "codex-market-analysis-v1",
    "headline": "電子早盤走強，收盤承接仍待確認",
    "thesis": "盤中科技風險偏好改善，但完整收盤與法人結果缺席，不能確認全天轉強。",
    "confidence": "low", "sentiment": "neutral",
    "evidence": [{"event_id": i, "role": r} for i, r in zip(IDS, ["preopen_oil", "prior_policy_rate", "intraday_not_close", "institutional_data_unavailable"])],
    "tw_sector_transmission": [
        {"sector": "半導體與電子零組件", "mechanism": "盤中風險偏好擴散仍需收盤與廣度驗證"},
        {"sector": "運輸、石化下游與製造業", "mechanism": "能源成本與轉嫁能力影響利潤"}],
    "invalidation": ["尾盤回吐且電子廣度收縮", "油價與資金成本壓力上升"],
    "data_gaps": ["final_taiwan_close", "closing_turnover_and_breadth", "institutional_net_flows"],
}


def check_text(text):
    forbidden = ["今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導", "先看區間邊界", "現在只看", "今日主命題", "三個證據", "市場正在定價什麼", "台股配置", "今日個股觀察", "stock_watch", "推薦", "候選", "入場", "停損", "止損", "目標價", "t_relay_events", "raw_json"]
    bad = [x for x in forbidden if x in text]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢\ue397\uef94]", text))
    english = bool(re.search(r"(?m)^#{1,6}\s+[A-Za-z]", text))
    return {"ok": not bad and not garbled and not english, "template": "flexible-briefing-memo-v1", "forbidden_terms": bad, "garbled_text": garbled, "english_section_headings": english, "fixed_section_template": False}


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DATE and "tw_close" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    c = store._cursor()
    c.execute("SELECT id,source,title,summary,published_at,raw_json FROM t_relay_events WHERE id IN (%s,%s,%s,%s) ORDER BY id", tuple(IDS))
    events = [dict(zip(["id", "source", "title", "summary", "published_at", "raw"], row)) for row in c.fetchall()]
    for e in events:
        e["raw"] = json.loads(e["raw"])
    assert len(events) == len(IDS)
    assert events[-1]["raw"]["rows"][0]["total"] == 0
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=STRUCTURED, events_payload=events, market_payload=[])
    style = check_text(SUMMARY)
    assert verifier["ok"] and style["ok"], (verifier, style)
    raw = {"automation_id": "market-analysis-codex-guard-tw-close", "generator": "codex_automation", "display_title": DATE, "calendar": calendar.to_dict(), "evidence_event_ids": IDS, "claim_verifier": verifier, "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"}, "style_checks": style, "external_provider_api_called": False, "close_confirmation": "unavailable", "review_note": "Intraday evidence explicitly identified; no final close or institutional-flow assertion."}
    if "--write" not in sys.argv:
        print(json.dumps({"dry_run": True, "claim_verifier": verifier, "style_checks": style}, ensure_ascii=False))
        return
    c.execute("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='tw_close'", (DATE,))
    assert c.fetchone() is None, "Existing row requires review before overwrite"
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DATE, analysis_slot="tw_close", scheduled_time_local="15:30", model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1", summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=False, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(STRUCTURED, ensure_ascii=False)))
    c.execute("SELECT id,summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='tw_close'", (DATE,))
    row = c.fetchone()
    stored_raw, structured = json.loads(row[2]), json.loads(row[3])
    verified = verify_claim_coverage(summary_text=row[1], structured_payload=structured, events_payload=events, market_payload=[])
    c.execute("SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s", (row_id,))
    signals = c.fetchone()[0]
    checks = {"analysis_id": row[0], "claim_verifier": verified, "trust_gate": stored_raw["trust_gate"], "push_enabled": bool(row[4]), "pushed": bool(row[5]), "structured_json_present": bool(structured), "style_checks": check_text(row[1]), "external_provider_api_called": stored_raw.get("external_provider_api_called"), "stock_watch_present": "stock_watch" in structured, "trade_signal_count": signals, "close_confirmation": stored_raw["close_confirmation"]}
    assert row[1] == SUMMARY and verified["ok"] and checks["style_checks"]["ok"]
    assert stored_raw["trust_gate"]["ok"] and not row[4] and not row[5] and structured
    assert stored_raw["external_provider_api_called"] is False and not signals and "stock_watch" not in structured
    c.close()
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == "__main__":
    main()
