"""Store a local-evidence close memo; dry-run unless --write is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)
from _tw_close_guard_20260907 import check_text

DAY = '2026-10-01'
TOKENS = {1034137: 'change_percent=+0.23%', 1034138: 'change=-0.537;',
          1034158: 'value=5.29;', 1034212: 'trade_date=2026-10-01'}
SUMMARY = '''收盤時間已過，今天仍沒有足夠證據確認台股把隔夜科技股的支撐轉成全天買盤，也無法據此否定盤前的審慎基調。可以延續的判斷是：電子需求期待仍須面對資金成本的考驗；不能延續的捷徑，是把海外指數走勢直接當成台灣收盤結果。最終指數、成交廣度與法人方向尚未能相互核對，台股全面轉強或轉弱都不宜在此刻下定論。

海外科技的支撐並不平均。美國週三那斯達克 100 指數上漲 0.23%，費城半導體指數卻微幅下跌、近乎持平。這組差異支持選擇性的科技定價，沒有證明半導體已全面接棒。傳到台灣，先進製程、封裝與伺服器供應鏈仍要靠訂單、交付與毛利把成長期待兌現；台積電等大型電子權值可以牽動指數，但少數權值承接與整體產業風險偏好改善，需要不同強度的證據。

利率讓這道檢驗更嚴格。美國週三十年期公債殖利率日頻資料為 5.29%，代表既有資金成本水準，並非今天台灣交易時段的升幅。當投資人要求較高報酬，遠期獲利需要更扎實的現金流支撐，需求成長也未必足以推動估值同步擴張。電子業的擴產與資金周轉因此要一起看；金融業則要分開衡量新增投資收益、既有債券評價及避險成本，不能只由殖利率水準推論整個族群受惠。

至於今日法人交易，目前可核對的查詢沒有有效買賣超結果。這代表方向尚未確認，不代表買賣超為零，更不能當成外資回補的證據。即使之後確認權值股撐住大盤，也還需要收盤成交與上漲範圍，才能判斷資金是否擴散到電子供應鏈及非電子產業。

海外價格已呈現科技指數小漲、半導體未明顯跟進的分歧；台灣究竟消化了多少利率壓力，仍是未解問題。後續若完整收盤證據顯示電子承接擴散、法人方向同向，且企業獲利展望穩定、殖利率壓力緩和，就有理由上修審慎判斷。反過來，若科技支撐消退，伴隨獲利下修或融資條件收緊，估值承壓的解釋便會更有分量。以上是會改變判斷的條件，尚不是今天收盤已確認的事實。'''


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
        if event['id'] != 1034212:
            assert event['published_at'].startswith('2026-09-30')
    flow = next(e for e in events if e['id'] == 1034212)
    assert json.loads(flow['raw_json'])['rows'][0]['total'] == 0
    assert not rows(cur, "SELECT id FROM t_relay_events WHERE published_at >= %s AND source NOT LIKE 'market_context:%%' AND title REGEXP '收盤|法人' LIMIT 1", (DAY,))
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='海外科技分歧與資金成本牽制估值，台灣收盤承接尚不能確認。',
        evidence_event_ids=list(TOKENS),
        tw_sector_transmission=['電子權值向先進製程、封裝與伺服器鏈傳導', '利率影響電子折現與金融債券評價'],
        invalidation=['收盤電子廣度及法人交易同向且獲利穩定、利率緩和', '科技支撐消退、獲利下修且利率壓力增加'],
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
