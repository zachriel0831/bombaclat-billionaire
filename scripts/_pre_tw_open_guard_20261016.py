"""Store a dated Codex memo from readable local facts; dry-run unless --apply."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _us_close_guard_20260917 import (
    rows,
    MySqlEventStore,
    MarketAnalysisRecord,
    load_settings,
    style_check,
    verify_claim_coverage,
    resolve_market_calendar_state,
    allowed_analysis_slots,
)

DAY = "2026-10-16"
FACTS = {
    1034915: ("change_percent=-0.88%", "2026-10-15T21:15:59+00:00"),
    1034920: ("change_percent=-1.80%", "2026-10-15T20:00:02+00:00"),
    1034916: ("change_percent=-2.43%", "2026-10-15T20:15:01+00:00"),
    1034935: ("value=5.1", "2026-10-15T00:00:00"),
}
SUMMARY = """今天盤前，市場交易的是科技風險偏好尚未全面退潮，但半導體權值的壓力仍在。台股基調偏保守，電子開盤較可能先反映海外晶片鏈走弱；最大不確定性是賣壓只集中在少數大型科技股，還是會擴散成對企業獲利與資金成本的重新定價。波動率回落讓恐慌沒有升高，但不等於半導體壓力已經解除。

美股科技內部出現分歧。費城半導體指數下跌 0.88%，台積電 ADR 下跌 1.80%，顯示晶片鏈短線情緒較弱；同時波動率指數下跌 2.43%，說明整體避險需求沒有同步惡化。這個組合比較像是估值與類股輪動的調整，尚不足以推論整體景氣轉差。對台灣而言，先進製程、封裝、伺服器與設備鏈容易承接半導體指數的開盤定價壓力，但後續能否止穩，仍要看成交是否擴散及企業展望能否承接。

利率仍是估值的邊界。美國十年期公債殖利率為 5.10%，使遠期獲利比重較高的電子類股仍須面對折現率約束。若利率維持高檔，市場會更挑剔訂單能見度、資本支出回報與現金流；金融與高股利類股則可能因收益率比較而相對受關注，但也不能把殖利率水準直接等同於所有金融業的利多。

目前價格已反映部分半導體壓力，尚不能量化市場已消化多少未來獲利風險。若半導體指數與台積電 ADR 止穩、台股電子成交擴散，且長端利率沒有再上行，偏保守的基調可下調；若晶片鏈續弱並伴隨殖利率走高，則代表壓力從權值股延伸至評價面。海外波動率回落只是風險情緒的背景，今天台股的量能與類股廣度仍須等開盤後確認。"""


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and "pre_tw_open" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cursor = store._cursor()
    assert not rows(
        cursor,
        "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'",
        (DAY,),
    ), "Existing row requires review"
    events = rows(
        cursor,
        "SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)",
        tuple(FACTS),
    )
    assert {event["id"] for event in events} == set(FACTS)
    for event in events:
        token, stamp = FACTS[event["id"]]
        assert token in event["summary"] and event["published_at"] == stamp
    structured = dict(
        schema_version="codex-market-analysis-v1",
        confidence="medium",
        thesis="半導體權值偏弱而整體避險未升高，台股盤前偏保守，利率仍約束電子評價。",
        evidence_event_ids=list(FACTS),
        tw_sector_transmission=["半導體與伺服器供應鏈開盤定價", "電子資本支出與折現率", "金融收益率比較"],
        invalidation=["半導體與台積電 ADR 止穩、台股電子成交擴散", "晶片鏈續弱且長端利率走高"],
    )
    verifier = verify_claim_coverage(
        summary_text=SUMMARY,
        structured_payload=structured,
        events_payload=events,
        market_payload=[],
    )
    style = style_check(SUMMARY)
    assert verifier["ok"] and style["ok"], (verifier, style)
    raw = dict(
        automation_id="market-analysis-codex-guard-pre-open",
        generator="codex_automation",
        display_title=DAY,
        calendar=calendar.to_dict(),
        evidence_event_ids=list(FACTS),
        claim_verifier=verifier,
        trust_gate=dict(version="market-analysis-trust-gate-v1", ok=True, reason="claim_verifier_ok"),
        style_checks=style,
        external_provider_api_called=False,
        generated_at=now.isoformat(),
        evidence_freshness={str(key): stamp for key, (_, stamp) in FACTS.items()},
        evidence_limits=["Readable individual local facts used; garbled collector summaries excluded", "Taiwan opening flows unconfirmed"],
    )
    print(json.dumps(dict(dry_run="--apply" not in sys.argv, characters=len(SUMMARY), verifier=verifier, style=style)))
    if "--apply" not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=DAY, analysis_slot="pre_tw_open", scheduled_time_local="07:30",
        model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=True, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False),
    ))
    reader = MySqlEventStore(load_settings(".env"))
    check = reader._cursor()
    row = rows(check, "SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s", (row_id,))[0]
    signals = rows(check, "SELECT COUNT(*) AS n FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["n"]
    assert row["summary_text"] == SUMMARY and json.loads(row["raw_json"]) == raw and json.loads(row["structured_json"]) == structured
    assert row["push_enabled"] == 1 and not row["pushed"] and signals == 0
    assert "stock_watch" not in row["structured_json"]
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier["ok"], trust_gate=raw["trust_gate"], push_enabled=1, pushed=False, structured_json_present=True, style_checks=style_check(row["summary_text"]), external_provider_api_called=False, trade_signal_count=signals)))


if __name__ == "__main__":
    main()
