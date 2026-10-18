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

DAY = "2026-10-19"
FACTS = {
    1035218: ("value=98.12", "2026-10-18T23:10:05+00:00"),
    1035217: ("change_percent=+0.08%", "2026-10-18T23:09:59+00:00"),
    1035219: ("change_percent=+0.42%", "2026-10-18T23:09:52+00:00"),
    1035238: ("value=4;", "2026-10-18"),
}
SUMMARY = """今天盤前，市場交易的重點是能源與避險需求會否重新推高通膨風險，而不是單一產業消息。台股基調先偏保守：若原物料成本與美元同時偏強，出口電子的評價會先受到折現率與風險溢酬約束；最大不確定性是這波跨資產變化只屬假期流動性下的短暫波動，還是會在開盤後擴散為更廣泛的風險重估。

可讀的本地價格訊號仍偏向防守。西德州原油報 98.12 美元，雖較前值下跌 0.91%，仍處高位；美元指數小升 0.08%，黃金期貨上漲 0.42%。三者放在一起，代表市場尚未放棄避險與通膨保護需求。聯準會目標區間上緣維持 4%，也表示利率條件沒有立刻轉為寬鬆；當油價或美元延續走強時，資金更容易提高對成本、匯率與折現率的要求。

這條傳導先落在台灣的成本與評價兩端。能源價格若回升，運輸、化工與高耗能製造的成本壓力會增加；美元偏強則有利出口報價的換匯條件，但也常伴隨全球資金偏向保留流動性。半導體、伺服器與電子供應鏈仍是指數權重的主要傳導器，開盤後若電子成交無法擴散，市場容易先把海外風險溢酬反映在權值族群，而不是立即解讀為基本面轉弱。

目前價格已反映部分能源與避險溢酬，但尚不能判定其持續時間。若油價續回落、美元轉弱，且台股電子成交與類股廣度改善，偏保守基調可下調；若油價再度走高並帶動美元與黃金同步上行，則代表通膨與風險溢酬仍可能壓抑評價。假期後首個交易日的量能與類股廣度，會比盤前單一價格更能確認方向。"""


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
        confidence="low",
        thesis="能源與避險需求仍在，台股盤前偏保守；假期後量能與類股廣度決定是否擴散。",
        evidence_event_ids=list(FACTS),
        tw_sector_transmission=["能源成本與製造毛利", "美元與出口換匯條件", "電子權值的風險溢酬"],
        invalidation=["油價回落、美元轉弱且電子成交擴散", "油價走高並帶動美元與黃金同步上行"],
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
