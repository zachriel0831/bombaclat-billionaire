"""Store a local-evidence close memo; dry-run unless --write is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)
from _tw_close_guard_20260907 import check_text

DAY = '2026-09-30'
TOKENS = {1034038: 'change_percent=+1.32%', 1034043: 'change_percent=+0.90%',
          1034058: 'value=5.26;', 1034112: 'trade_date=2026-09-30'}
SUMMARY = '''今天收盤後，仍無法確認台股是否把隔夜半導體回升轉成全天承接，也沒有足夠證據推翻盤前的審慎判斷。海外電子價格提供支撐、資金成本仍牽制估值，這兩股力量的拉鋸依然是可用的分析起點；但今日最終指數、成交廣度與有效法人買賣超尚待確認，不能據此宣告台股已全面轉強或轉弱。

隔夜費城半導體指數上漲 1.32%，台積電美國存託憑證上漲 0.90%。這組同向價格訊號，說明海外半導體與大型晶圓製造企業獲得較好的市場評價，卻沒有直接證明訂單或獲利加速。對台灣而言，台積電作為電子權值的傳導例子，能影響市場對先進製程與封裝鏈的期待；設備、伺服器及零組件能否接棒，仍取決於交付、毛利與接單能見度。海外漲幅不能直接換成台灣現股今天的表現。

利率則讓這份期待面臨另一道檢驗。前一日美國財政部日頻資料記錄十年期公債殖利率為 5.26%。這是既有殖利率水準，並非今天亞洲時段突然上升的幅度，也不是央行政策利率。在較高折現要求下，遠期成長必須由現金流支撐，電子需求延續不一定同時帶來估值擴張。金融業也要分開看新增投資收益與既有債券評價，並考慮持有期限及避險成本，不能把利率水準概括成整個族群的利多。

收盤判斷最缺的，是台灣價格與資金能否互相印證。今天可核對的法人查詢仍未提供有效買賣超，因此不能認定外資回補，也不能把查無資料當成零買賣超。即使後續看到權值撐住指數，仍須確認電子承接是否擴散；少數大型股走穩，與整體風險偏好改善，是不同強度的結論。

海外价格已呈現半導體回升，但台灣市場究竟反映了多少，現階段仍不能回答。接下來可能改變評價的，是獲利實現程度與資金成本的組合：若完整收盤資料顯示电子強勢擴散、法人交易同向，並伴隨企業展望穩定與利率壓力緩和，審慎看法便應上修；若回升無法延續、供應鏈獲利下修且殖利率壓力增加，估值修復就可能失去支撐。這些是判斷成立或失效的條件，尚非今天收盤已發生的結果。'''.replace('价格', '價格').replace('电子', '電子')


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and (now.hour, now.minute) >= (15, 30)
    assert 'tw_close' in allowed_analysis_slots(cal)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='tw_close'", (DAY,))
    events = rows(cur, 'SELECT id,source,title,summary,published_at,raw_json FROM t_relay_events WHERE id IN (%s,%s,%s,%s)', tuple(TOKENS))
    assert {e['id'] for e in events} == set(TOKENS)
    for event in events:
        assert TOKENS[event['id']] in event['summary']
        if event['id'] != 1034112:
            assert event['published_at'].startswith('2026-09-29')
    flow = next(e for e in events if e['id'] == 1034112)
    assert json.loads(flow['raw_json'])['rows'][0]['total'] == 0
    assert not rows(cur, "SELECT id FROM t_relay_events WHERE published_at >= %s AND source NOT LIKE 'market_context:%%' AND title REGEXP '收盤|法人' LIMIT 1", (DAY,))
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='隔夜半導體回升與資金成本拉鋸，台灣收盤承接尚不能確認。',
        evidence_event_ids=list(TOKENS),
        tw_sector_transmission=['電子權值向先進製程、封裝與伺服器鏈傳導', '利率影響電子折現與金融債券評價'],
        invalidation=['收盤電子廣度及法人交易同向且獲利穩定、利率緩和', '半導體回升消退、獲利下修且利率壓力增加'],
        data_gaps=['final_taiwan_close', 'closing_turnover_and_breadth', 'institutional_net_flows'])
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
