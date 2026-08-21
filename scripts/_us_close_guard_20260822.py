from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

ANALYSIS_DATE = "2026-08-22"
SLOT = "us_close"
AUTOMATION_ID = "market-analysis-codex-guard-us-close"
EVENT_IDS = [733994, 733995, 733997, 729625, 730709]
MARKET_IDS = [335, 336]

SUMMARY = """美股收盤留給台灣投資人的新訊號，不是單純的風險偏好回升，而是資金開始區分「景氣還撐得住」與「利率、能源風險仍壓著估值」兩件事。道瓊收高、標普近乎持平，顯示資金沒有全面撤退，但也沒有把成長股重新當成單一路徑；台股接下來更可能走產業輪動，而不是所有電子股一起擴張評價。最大的變數仍是公債殖利率與伊朗局勢是否再推高能源風險溢價。

## 收盤透露的三股力量

美國勞動市場的組合偏向「數量轉弱、價格黏著」：最新資料顯示非農就業人數較前月減少二萬三千人，失業率則由百分之四點二降至百分之四點一；同時民間平均時薪年增仍約百分之三點二。這不支持需求立即失速，卻也不利市場快速押注寬鬆，因為薪資韌性會讓通膨與聯準會路徑保留不確定性。

資產價格本身也在說同一件事。道瓊由開盤約五萬二千七百六十九點收至五萬三千二百七十七點，標普五百則由約七千六百六十六點收在七千六百七十四點附近。大型股指數分歧而非同步大漲，較像資金在重新平衡景氣、利率與評價，而不是確認新一輪全面多頭。

債券端仍是估值上限。當地報導指出，股債曾同步承壓，公債殖利率上升，財政部壓低政府融資成本的效果有限。若長債供給與財政疑慮沒有改善，即使企業需求尚有韌性，高久期科技股也很難只靠題材擴張本益比。另一方面，美伊經濟對抗仍在升高；只要衝突延伸到能源、運輸或制裁執行，油價風險就會經由通膨預期再回到利率市場。

## 台股會先反映輪動，而非齊漲

半導體、AI伺服器與先進封裝仍有需求敘事，但短線評價更受美債殖利率約束；台積電等大型權值股因此比較像指數風險偏好的放大器，而不是脫離利率獨立上行。若資金持續偏向現金流與景氣韌性，金融、傳產與部分具報價能力的電子材料可能相對有支撐；但航運、航空、塑化與耗能製造會對油價與運輸風險呈現不同方向的敏感度，不能把「能源題材」視為同一筆交易。

目前價格已部分反映美國需求沒有立即衰退，還沒有充分消化的是長債殖利率再上行，或伊朗風險轉成實際能源供給干擾。這個判斷的失效條件也很清楚：若殖利率回落、能源風險未落到供給端，而且科技股重新出現廣泛且有成交量支持的領漲，市場就可能從輪動重新轉回成長主導；反之，若股債再度同跌並伴隨油價急升，台股高評價電子與能源成本敏感產業的壓力會同步放大。"""


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
        cursor.execute("SELECT id,event_id,source,title,summary,published_at,created_at,raw_json FROM t_relay_events WHERE id IN (%s,%s,%s,%s,%s) ORDER BY id", tuple(EVENT_IDS))
        event_columns = ["id", "event_id", "source", "title", "summary", "published_at", "created_at", "raw_json"]
        events = json_safe([dict(zip(event_columns, row)) for row in cursor.fetchall()])
        cursor.execute("SELECT id,event_id,source,trade_date,market_session,symbol,label,open_price,last_price,recorded_price,created_at FROM t_market_index_snapshots WHERE id IN (%s,%s) ORDER BY id", tuple(MARKET_IDS))
        market_columns = ["id", "event_id", "source", "trade_date", "market_session", "symbol", "label", "open_price", "last_price", "recorded_price", "created_at"]
        market = json_safe([dict(zip(market_columns, row)) for row in cursor.fetchall()])
    finally:
        cursor.close()
    if len(events) != len(EVENT_IDS) or len(market) != len(MARKET_IDS):
        raise RuntimeError("required local evidence rows are missing")
    structured = {
        "schema_version": "codex-market-analysis-v1",
        "headline": "輪動接棒，利率與能源仍壓著估值",
        "thesis": "美股收盤顯示景氣韌性與利率、能源風險並存，台股較可能先走產業輪動。",
        "sentiment": "cautious", "confidence": "medium",
        "evidence": [
            {"role": "us_close_rotation", "market_snapshot_ids": MARKET_IDS},
            {"role": "labor_quantity", "event_ids": [733994, 733995]},
            {"role": "wage_pressure", "event_id": 733997},
            {"role": "rates_and_energy_risk", "event_ids": [729625, 730709]},
        ],
        "tw_sector_transmission": [
            {"sector": "半導體與AI供應鏈", "mechanism": "需求韌性提供基本面支撐，長債殖利率限制評價擴張"},
            {"sector": "金融與傳產", "mechanism": "資金輪動與利率環境帶來相對支撐，但景氣敏感度不同"},
            {"sector": "航運、航空、塑化與耗能製造", "mechanism": "能源與運輸風險對收入與成本的傳導方向不一"},
        ],
        "invalidation": ["殖利率回落且能源風險沒有轉成實際供給干擾", "科技股重新出現廣泛且有成交量支持的領漲"],
    }
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    forbidden = ["今日一句話", "三個檢查點", "市場押注與預期差", "國際消息到台股的傳導", "先看區間邊界", "現在只看", "今日主命題", "三個證據", "市場正在定價什麼", "台股配置", "今日個股觀察", "stock_watch", "入場", "停損", "止損", "目標價", "t_relay_events", "t_market_analyses", "claim_verifier", "market_context", "raw_json"]
    found_forbidden = [term for term in forbidden if term in SUMMARY]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", SUMMARY))
    style_checks = {"ok": not found_forbidden and not garbled, "template": "flexible-briefing-memo-v1", "garbled_text": garbled, "forbidden_terms": found_forbidden, "fixed_section_template": False}
    if not verifier["ok"] or not style_checks["ok"]:
        raise RuntimeError(json.dumps({"claim_verifier": verifier, "style_checks": style_checks}, ensure_ascii=False))
    raw = {
        "automation_id": AUTOMATION_ID, "generator": "codex_automation", "display_title": ANALYSIS_DATE,
        "calendar": calendar.to_dict(), "evidence_event_ids": EVENT_IDS, "market_snapshot_rows": len(market),
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style_checks, "external_provider_api_called": False,
    }
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=ANALYSIS_DATE, analysis_slot=SLOT, scheduled_time_local="05:00",
        model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1", summary_text=SUMMARY,
        events_used=len(events), market_rows_used=len(market), push_enabled=True, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False),
    ))
    verify_cursor = store._cursor()
    try:
        verify_cursor.execute(
            "SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s",
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
        "trust_gate_ok": stored_raw.get("trust_gate", {}).get("ok") is True,
        "trust_gate_reason": stored_raw.get("trust_gate", {}).get("reason"),
        "push_enabled": bool(stored[1]), "pushed": bool(stored[2]),
        "structured_json_present": bool(stored_structured),
        "garbled_text": bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", stored_summary)),
        "style_ok": stored_raw.get("style_checks", {}).get("ok") is True,
        "fixed_section_template": stored_raw.get("style_checks", {}).get("fixed_section_template"),
        "external_provider_api_called": stored_raw.get("external_provider_api_called"),
        "trade_signal_count": signal_count,
    }
    if not all([
        checks["claim_verifier_ok"], checks["trust_gate_ok"], checks["push_enabled"],
        not checks["pushed"], checks["structured_json_present"], not checks["garbled_text"],
        checks["style_ok"], checks["fixed_section_template"] is False,
        checks["external_provider_api_called"] is False, checks["trade_signal_count"] == 0,
    ]):
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))
    print(json.dumps(checks, ensure_ascii=True))


if __name__ == "__main__":
    main()
