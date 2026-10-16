"""Store the 2026-10-16 local-evidence Taiwan-close memo."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _tw_close_guard_20260907 import check_text
from _us_close_guard_20260917 import (
    MarketAnalysisRecord,
    MySqlEventStore,
    allowed_analysis_slots,
    load_settings,
    resolve_market_calendar_state,
    rows,
    verify_claim_coverage,
)


DAY = "2026-10-16"
EVENT_IDS = (1034915, 1034920, 1034935, 1035002)
SUMMARY = """今天收盤尚未確認海外半導體壓力是否已轉化為台股全面賣壓，也不能把本地信用部位資料更新解讀成風險偏好回升。本日收盤材料沒有完整的指數、成交廣度與法人買賣超明細，因此較合理的結論是維持低信心的風險邊界，而不是替行情下方向判斷。

前一個美國交易日，費城半導體指數下跌 0.88%，TSM ADR 下跌 1.80%。這表示海外晶片鏈的短線定價仍偏弱，對台灣電子權值、先進製程、封裝與伺服器供應鏈形成開盤後的評價壓力；但美國存託憑證與台灣現股的交易時段、投資人結構不同，不能直接當成今天台股收盤的漲跌證明。

資金成本也沒有提供估值明顯放鬆的訊號。美國十年期公債殖利率維持在 5.10%，意味著遠期獲利比重高的電子族群，仍須用接單能見度與現金流來承接評價。金融與高股利類股可能受到收益率比較影響，但債券評價與避險成本仍要分開看，不能把利率水準直接翻成全族群利多。

收盤後本地資料已涵蓋信用部位與外資持股結構等項目，但法人買賣超沒有形成可用的明細，指數與成交廣度亦未能交叉驗證。這不是法人買賣超為零，也不代表資金已撤離；它只限制了我們對今天收盤承接強度的判讀。若後續資料顯示電子廣度改善、法人方向轉為支持，且長端利率沒有再走高，偏保守的判斷就應下調；若晶片鏈續弱並伴隨本地成交收縮或企業展望下修，壓力才可能由估值延伸到獲利。"""


def main() -> None:
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and "tw_close" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    assert not rows(
        cursor,
        "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='tw_close'",
        (DAY,),
    ), "Existing row requires review"
    events = rows(
        cursor,
        "SELECT id,source,title,summary,published_at,raw_json FROM t_relay_events WHERE id IN (%s,%s,%s,%s)",
        EVENT_IDS,
    )
    assert {event["id"] for event in events} == set(EVENT_IDS)
    expected_tokens = {
        1034915: "change_percent=-0.88%",
        1034920: "change_percent=-1.80%",
        1034935: "value=5.1",
        1035002: "15 relay events aggregated",
    }
    for event in events:
        assert expected_tokens[event["id"]] in event["summary"]

    structured = {
        "schema_version": "codex-market-analysis-v1",
        "confidence": "low",
        "thesis": "海外半導體偏弱與高利率仍構成壓力，但本地收盤資料不足以確認台股方向。",
        "evidence_event_ids": list(EVENT_IDS),
        "tw_sector_transmission": [
            "海外晶片定價影響電子權值、先進製程、封裝與伺服器供應鏈評價",
            "長端利率限制高遠期獲利電子族群的評價空間",
        ],
        "invalidation": [
            "電子廣度改善、法人方向支持且長端利率未再走高",
            "晶片鏈續弱，並伴隨本地成交收縮或企業展望下修",
        ],
        "data_gaps": ["final_taiwan_index", "closing_breadth", "institutional_net_flow_detail"],
    }
    verifier = verify_claim_coverage(
        summary_text=SUMMARY,
        structured_payload=structured,
        events_payload=events,
        market_payload=[],
    )
    style = check_text(SUMMARY)
    assert verifier["ok"] and style["ok"], (verifier, style)
    raw = {
        "automation_id": "market-analysis-codex-guard-tw-close",
        "generator": "codex_automation",
        "display_title": DAY,
        "calendar": calendar.to_dict(),
        "dimension": "daily_tw_close",
        "evidence_event_ids": list(EVENT_IDS),
        "claim_verifier": verifier,
        "trust_gate": {"version": "market-analysis-trust-gate-v1", "ok": True, "reason": "claim_verifier_ok"},
        "style_checks": style,
        "external_provider_api_called": False,
        "generated_at": now.isoformat(),
        "close_confirmation": "unconfirmed_missing_complete_taiwan_close_data",
        "evidence_quality": "limited_evidence",
    }
    print(json.dumps({"dry_run": "--write" not in sys.argv, "verifier": verifier, "style": style}, ensure_ascii=False))
    if "--write" not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=DAY, analysis_slot="tw_close", scheduled_time_local="15:30",
        model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0,
        push_enabled=False, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False),
        structured_json=json.dumps(structured, ensure_ascii=False),
    ))
    reader = MySqlEventStore(load_settings(".env"))
    check = reader._cursor()
    row = rows(check, "SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s", (row_id,))[0]
    signals = rows(check, "SELECT COUNT(*) AS n FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["n"]
    raw_readback = json.loads(row["raw_json"])
    structured_readback = json.loads(row["structured_json"])
    verified = verify_claim_coverage(
        summary_text=row["summary_text"],
        structured_payload=structured_readback,
        events_payload=events,
        market_payload=[],
    )
    readback_style = check_text(row["summary_text"])
    assert row["summary_text"] == SUMMARY and verified["ok"] and readback_style["ok"]
    assert raw_readback["trust_gate"]["ok"] and not row["push_enabled"] and not row["pushed"]
    assert raw_readback["external_provider_api_called"] is False and "stock_watch" not in structured_readback and signals == 0
    print(json.dumps({"analysis_id": row_id, "claim_verifier": verified, "trust_gate": raw_readback["trust_gate"], "push_enabled": bool(row["push_enabled"]), "pushed": bool(row["pushed"]), "structured_json_present": bool(row["structured_json"]), "style_checks": readback_style, "garbled_text": False, "external_provider_api_called": raw_readback["external_provider_api_called"], "trade_signal_count": signals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
