"""Store the local-evidence closing memo; dry-run unless --write is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)
from _tw_close_guard_20260907 import check_text

DAY = '2026-10-06'
TOKENS = {1034629: 'change_percent=+0.87%', 1034630: 'change_percent=+0.27%',
          1034645: 'change_percent=-0.48%', 1034704: 'trade_date=2026-10-06'}
SUMMARY = '''今天台股收盤是否確認了海外科技股帶來的支撐，目前仍缺乏完整價量與法人結果，無法判定。可以成立的判斷是：隔夜美股成長股走強，但半導體沒有領漲，長天期債券又承受價格壓力，台灣電子的需求期待與估值條件仍在拉扯。這份收盤觀察因此維持低信心；尚未取得確認，既不等於台股已轉弱，也不能當成資金全面回流的證明。

美國週一那斯達克百大指數上漲 0.87%，費城半導體指數上漲 0.27%。兩者同向，但晶片漲幅較小，顯示這一晚的科技股支撐不能直接解讀為半導體全面領先。對台灣而言，先進製程、封裝及伺服器鏈仍可能受海外風險偏好帶動；台積電等大型權值則是指數傳導的重要節點。然而，海外價格走強並未回答本地成交是否擴散，更無法替供應鏈的接單、毛利與現金流作保證。

同一個美國交易日，長天期公債基金價格下跌 0.48%。這項價格訊號提醒我們，股票上漲並沒有伴隨長債同步走強，不能把行情直接歸因於資金成本全面鬆綁。基金價格也不能換算成單一公債殖利率的確切變動。若折現壓力持續，電子業需要更扎實的獲利成長才能支撐估值；金融業則須分開看債券評價、新增投資收益與避險成本，不能只憑利率方向判斷整個族群受惠。

台灣今日法人交易的可核對回應尚無有效買賣超結果，這是資訊尚缺，不是買賣超為零。收盤成交與上漲廣度也未能交叉確認，因此不能說外資已回補，或把盤前取得的個別權值行情當成今日收盤。在完整結果出現前，海外科技支撐只能提供傳導方向，無法證明電子與非電子產業已獲得同樣的資金承接。

目前價格已呈現海外科技上漲、長債走弱的組合，但這組合不足以量出未來獲利已被反映多少。接下來的重估空間，取決於本地承接能否擴散，以及獲利成長能否抵銷資金成本。若完整收盤資料顯示電子廣度改善、法人方向同向，且企業展望穩定、長債壓力緩和，才有理由提高台灣傳導的信心；若晶片相對疲弱延續，並伴隨本地成交收縮、獲利下修或融資條件轉緊，海外科技支撐台股的假設就需要撤回。這些是修正判斷的證據條件，並非今日收盤已確認的事實。'''


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
        assert event['published_at'].startswith(DAY if event['id'] == 1034704 else '2026-10-05')
    flow = next(e for e in events if e['id'] == 1034704)
    assert json.loads(flow['raw_json'])['rows'][0]['total'] == 0
    assert not rows(cur, "SELECT id FROM t_relay_events WHERE published_at >= %s AND source NOT LIKE 'market_context:%%' AND title REGEXP '收盤|法人' LIMIT 1", (DAY,))
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='隔夜科技股支撐與長債壓力並存，台灣收盤承接尚未確認。',
        evidence_event_ids=list(TOKENS),
        tw_sector_transmission=['海外科技價格向電子權值、先進製程與伺服器鏈傳導', '長債壓力影響電子估值與金融債券評價'],
        invalidation=['本地廣度與法人同向、獲利穩定且長債壓力緩和', '晶片相對疲弱、本地成交收縮或獲利下修'],
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
    verified = verify_claim_coverage(summary_text=row['summary_text'], structured_payload=json.loads(row['structured_json']), events_payload=events, market_payload=[])
    assert verified['ok'] and row['push_enabled'] == 0 and not row['pushed'] and signals == 0
    assert 'stock_watch' not in row['structured_json'] and check_text(row['summary_text'])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verified['ok'], trust_gate=raw['trust_gate'],
        push_enabled=0, pushed=False, structured_json_present=True, style_checks=check_text(row['summary_text']),
        external_provider_api_called=json.loads(row['raw_json'])['external_provider_api_called'], trade_signal_count=signals)))


if __name__ == '__main__':
    main()
