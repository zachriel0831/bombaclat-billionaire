"""Local evidence-only close memo; dry-run unless --write is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)
from _tw_close_guard_20260907 import check_text

DAY = '2026-09-29'
TOKENS = {1033951: 'change_percent=-1.61%', 1033956: 'change_percent=+0.50%',
          1033971: 'value=5.24;', 1034025: 'no same-day flow/disclosure events found'}
SUMMARY = '''截至今天收盤後，仍無法確認台股是否消化了海外半導體的分化，也無法判定盤前的審慎看法已被行情推翻。可核對的資料缺少今日最終指數、成交廣度與法人買賣超，因此目前能成立的是「權值韌性與資金成本互相拉扯」的條件判斷，而不是台股已轉強或轉弱的收盤結論。

隔夜的分化值得保留，但不能冒充今天的答案。前一個美國交易日，費城半導體指數下跌 1.61%，台積電美國存託憑證的常規交易時段報價則上漲 0.50%。這組價格反映大型晶圓製造企業與半導體整體表現不同，支持把權值與產業廣度拆開看。它沒有證明台灣現股今天同步上漲，也無法單靠價格證明訂單改善；美國存託憑證的表現，更不能直接套成台灣現股的漲跌幅。

對台灣電子鏈，這個差異的意義在於：即使台積電作為大型權值具備相對韌性，先進封裝、設備與伺服器供應鏈仍須各自接受接單、交付及利潤的檢驗。若後續收盤資料顯示電子承接擴散、更多族群參與，才較支持風險偏好改善；若僅少數權值撐住指數，則不能把指數穩定當成整體企業獲利前景轉佳。

另一個已知條件是資金價格。前一日美國財政部日頻資料記錄十年期公債殖利率為 5.24%。這是既有利率水準，不是今天亞洲時段的變動，也不是央行政策利率。對仰賴未來成長的電子企業，資金成本會影響投資人願意給予的估值；需求即使延續，也需要現金流與獲利支撐。金融業則可能同時面對較高再投資收益與債券評價壓力，不能把殖利率水準直接翻譯成全產業的利多。

眼前海外價格已呈現半導體內部分化，但台灣市場究竟反映了多少，仍須今日完整收盤與資金資料才能回答。尤其法人資料缺席不能解讀為買賣超歸零，也不能推論外資回補或撤離。價格表現、股票買賣超與跨境資金流是不同證據，只有方向相互印證，才適合提高判斷信心。

後續再定價的關鍵，是企業獲利能否抵銷資金成本，以及權值支撐能否擴散。若台灣電子收盤廣度改善、法人交易提供支持，且利率壓力緩和，審慎看法就應上修；若權值韌性消退、電子弱勢擴大，並伴隨企業下修展望或資金成本增加，則壓力可能由估值延伸至獲利。在今日收盤證據補齊前，這些都只是待驗證的情境；目前無法確認或否定台股全天的承接強度。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and (now.hour, now.minute) >= (15, 30)
    assert 'tw_close' in allowed_analysis_slots(cal)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='tw_close'", (DAY,))
    events = rows(cur, 'SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1033951,1033956,1033971,1034025)')
    assert {e['id'] for e in events} == set(TOKENS)
    for event in events:
        assert TOKENS[event['id']] in event['summary']
    # Abort for editorial review if new same-day closing evidence arrives.
    assert not rows(cur, "SELECT id FROM t_relay_events WHERE published_at >= %s AND (source LIKE 'market_context:twse_flow%%' OR source LIKE 'market_context:tpex_flow%%' OR (source NOT LIKE 'market_context:%%' AND title REGEXP '收盤|法人')) LIMIT 1", (DAY,))
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='今日收盤證據不足，尚不能確認或否定權值韌性是否擴散；利率仍是估值條件。',
        evidence_event_ids=list(TOKENS),
        tw_sector_transmission=['電子權值與供應鏈廣度分開驗證', '資金成本與電子現金流', '金融再投資收益及債券評價'],
        invalidation=['電子廣度改善、法人支持且利率壓力緩和', '權值轉弱、電子弱勢擴大且展望下修或資金成本上升'],
        data_gaps=['final_taiwan_close', 'closing_turnover_and_breadth', 'institutional_net_flows'],
        evidence_limitations=['海外價格為前一美國交易日；利率為前一日日頻資料', '收盤情境事件明確缺少同日資金及揭露資料'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = check_text(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    raw = dict(automation_id='market-analysis-codex-guard-tw-close', generator='codex_automation',
        display_title=DAY, calendar=cal.to_dict(), evidence_event_ids=list(TOKENS),
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        close_confirmation='unconfirmed_missing_same_day_close', evidence_quality='limited-evidence')
    print(json.dumps(dict(dry_run='--write' not in sys.argv, characters=len(SUMMARY), verifier=verifier, style=style)))
    if '--write' not in sys.argv:
        return
    row_id = writer.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='tw_close',
        scheduled_time_local='15:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=False, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    reader = MySqlEventStore(load_settings('.env'))
    rc = reader._cursor()
    row = rows(rc, 'SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    signals = rows(rc, 'SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n']
    assert row['summary_text'] == SUMMARY and json.loads(row['raw_json']) == raw and json.loads(row['structured_json']) == structured
    assert row['push_enabled'] == 0 and not row['pushed'] and signals == 0
    assert 'stock_watch' not in row['structured_json'] and check_text(row['summary_text'])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=0, pushed=False, structured_json_present=True, style_checks=check_text(row['summary_text']),
        external_provider_api_called=json.loads(row['raw_json'])['external_provider_api_called'], trade_signal_count=signals)))


if __name__ == '__main__':
    main()
