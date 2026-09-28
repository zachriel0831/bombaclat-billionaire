"""Local evidence-only, limited-freshness memo; dry-run unless --write."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-29'
EVENT_IDS = [1033577, 1033335, 1030909]
SUMMARY = """這個美股收盤時點，台灣投資人需要重新衡量的是資金成本、能源政策與電子需求之間的拉扯。目前可確認的消息仍停留在前一日白天，尚不足以判定最新美股收盤如何改變台股的風險偏好。因此，對台灣市場先維持審慎、但不把半導體需求一併看弱的判斷；這是一份有待隔夜行情確認的情境分析。

經濟日報轉述彭博指出，美債殖利率曲線幾近發出警訊，市場敘事可能由升息轉向對經濟停滯的擔憂。重點在於利率提高的影響可能從估值延伸到需求：企業融資與消費負擔若持續增加，獲利成長便需要更扎實的支持。不過，報導描述的是風險訊號接近形成，不能據此宣告衰退已經發生，也不能推斷最新一晚殖利率的方向。對台灣電子出口鏈而言，接單能見度與客戶資本支出是否延續，比單靠利率敘事更能辨認需求變化。

能源端也有政策變數。自由時報報導，美國政府正考慮限制柴油出口；考慮中的措施還不是已實施的禁令。如果限制真的落地，美國以外市場的成品油供應與運輸成本可能承壓，即使原油價格沒有同步上升，企業仍可能感受到成本差異。台灣陸運、物流及耗能製造需要留意燃料成本的傳導，煉油與石化則須分別檢驗原料、產品售價及需求，不能把供應限制直接等同整個產業受惠。目前也不足以確認這項政策已反映多少在價格中。

半導體需求提供另一個方向。經濟日報引述供應鏈消息，台積電先進製程產能預訂增加，並加快擴充。這支持人工智慧與高速運算需求仍有韌性的解讀，但報導中的預訂與擴產並非已實現營收，更不等於整體電子業同步改善。傳導到台灣，先進製程、設備與相關供應鏈的業務機會仍須由交付進度、產能利用率及毛利率驗證；若資金成本偏高，需求成長與估值壓力可能同時存在。

接下來的再定價，取決於需求能否抵銷成本與利率壓力。若出口限制未實施、能源成本緩和，而電子訂單持續轉成營收，審慎看法就應調整；若政策收緊、燃料成本上升，又伴隨客戶削減支出，對台灣企業獲利的壓力便會加深。美元、殖利率與半導體收盤表現能否互相印證，才有助於判斷資金是否接受這些訊息。在最新隔夜價格尚未確認前，不宜把前一日新聞直接寫成美股收盤的因果結論。"""


def main():
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and 'us_close' in allowed_analysis_slots(calendar)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1033577,1033335,1030909)')
    assert {e['id'] for e in events} == set(EVENT_IDS)
    assert all(e['published_at'][:10] == '2026-09-28' for e in events)
    market = rows(cur, "SELECT id FROM t_market_index_snapshots WHERE trade_date='2026-09-28' AND market_session='close'")
    assert not market, 'Fresh close evidence is now available; revise the memo before storing'
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='隔夜價格未確認，暫以利率、能源政策與半導體需求評估台灣傳導。',
        evidence_event_ids=EVENT_IDS, market_snapshot_ids=[],
        tw_sector_transmission=['電子出口與估值', '物流及製造成本', '先進製程及設備需求'],
        invalidation=['能源壓力緩和且訂單轉為營收', '政策收緊且客戶削減支出'],
        limitations=['Latest U.S. session close unavailable; news predates that session'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    push = not calendar.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation',
        display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=EVENT_IDS,
        market_snapshot_ids=[], claim_verifier=verifier,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        evidence_freshness=dict(status='limited', current_us_close_available=False, news_date='2026-09-28'),
        style_checks=style, external_provider_api_called=False)
    print(json.dumps(dict(dry_run=True, claim_verifier=verifier, style_checks=style, push_enabled=push), ensure_ascii=False))
    if '--write' not in sys.argv:
        return
    row_id = writer.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='us_close',
        scheduled_time_local='05:00', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=push, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    reader = MySqlEventStore(load_settings('.env'))
    rc = reader._cursor()
    row = rows(rc, 'SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    signals = rows(rc, 'SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n']
    assert row['summary_text'] == SUMMARY and json.loads(row['raw_json']) == raw and json.loads(row['structured_json']) == structured
    assert bool(row['push_enabled']) == push and not row['pushed'] and signals == 0
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=push, pushed=False, structured_json_present=True, style_checks=style_check(row['summary_text']),
        external_provider_api_called=json.loads(row['raw_json'])['external_provider_api_called'], trade_signal_count=signals,
        characters=len(SUMMARY)), ensure_ascii=False))


if __name__ == '__main__':
    main()
