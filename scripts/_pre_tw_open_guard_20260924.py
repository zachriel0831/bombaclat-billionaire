"""Local evidence-only pre-open memo; dry-run unless --apply is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _pre_tw_open_guard_20260923 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-24'
TOKENS = {1000421: 'change_percent=-1.23%', 1000436: 'change_percent=-1.58%',
          1000441: 'value=5.11;', 1000424: 'value=92.24;'}
SUMMARY = '''市場正在重新衡量成長股願意承受多少資金成本：海外半導體與長天期公債同步走弱，讓台股盤前偏向審慎，電子權值及相關供應鏈的評價先面臨考驗。最大的未知，是這次壓力只停留在價格調整，還是會延伸到企業融資、投資與獲利預期；目前的價格證據不足以直接宣告需求轉差。

股票與長債同跌，支撐要回到獲利

前一個美股交易日，費城半導體指數下跌 1.23%，追蹤長天期美國公債的基金下跌 1.58%。兩者同向走弱，意味著當晚長債沒有替成長股提供價格上的緩衝，也與折現壓力的解讀相容。不過，僅憑這組價格不能斷定賣壓全由利率引起，更不能把長債基金跌幅直接換算成殖利率變化。

最新美國十年期公債殖利率為 5.11%，提供了另一個資金成本的參照。這是日頻利率水準，並非今晨即時跳升幅度，也不等於央行政策利率。對台灣先進製程、封裝及伺服器供應鏈，遠期獲利若要維持目前評價，就更需要訂單能見度、毛利率與現金流支撐。海外半導體回落會先影響情緒與估值，是否傷及營運仍要另行驗證；金融業也須區分債券評價壓力與較長期的再投資收益，不能把高利率簡化成一致利多。

能源尚未替成本端解圍

今晨西德州原油期貨報每桶 92.24 美元，較前值微升。這是盤前期貨報價，不是今日結算價；它至少尚未提供能源成本持續下降的確認。若油價重新走高，台灣運輸與高耗能製造可能先承受燃料、原料與運費壓力，電子業則可能透過物流成本及通膨預期間接受影響。石化業仍須看產品售價能否跟上原料變化，航空業則受燃料合約與匯率左右，不能只憑油價方向判定獲利。

目前已反映在價格上的，是海外半導體與長債同步承壓；尚待重新定價的，是企業獲利能否抵銷資金成本，以及能源波動會不會侵蝕利潤。若台灣電子承接擴散、企業展望保持韌性，且長債止穩、油價回落，盤前偏審慎的判斷就應調回中性。反過來，若半導體弱勢延續、殖利率進一步走高，並伴隨能源成本上升，壓力便可能從評價擴大到獲利。美股收盤、日頻利率與今晨期貨屬不同時間點，這些訊號用來檢驗開盤後的承接，不能當作台灣資金已流出的證明。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1000421,1000436,1000441,1000424)')
    assert {e['id'] for e in events} == set(TOKENS)
    for event in events:
        assert TOKENS[event['id']] in event['summary']
        assert str(event['published_at']).startswith('2026-09-23')
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='半導體與長債同步承壓，台股偏審慎，獲利能否抵銷資金成本仍待確認。',
        evidence=[dict(event_id=i) for i in TOKENS],
        tw_sector_transmission=['半導體及電子供應鏈評價與獲利', '金融債券評價及再投資收益', '運輸及製造能源成本'],
        invalidation=['企業展望穩健且電子承接擴散、長債止穩與油價回落', '半導體弱勢延續且利率及能源成本升高'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style))
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation',
        display_title=DAY, calendar=cal.to_dict(), evidence_event_ids=list(TOKENS),
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat())
    print(json.dumps(dict(dry_run='--apply' not in sys.argv, characters=len(SUMMARY), verifier=verifier, style=style)))
    if '--apply' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='pre_tw_open',
        scheduled_time_local='07:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=4, market_rows_used=0, push_enabled=True, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    reader = MySqlEventStore(load_settings('.env'))
    rc = reader._cursor()
    row = rows(rc, 'SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    signals = rows(rc, 'SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n']
    assert row['summary_text'] == SUMMARY and json.loads(row['raw_json']) == raw and json.loads(row['structured_json']) == structured
    assert row['push_enabled'] == 1 and not row['pushed'] and signals == 0
    assert style_check(row['summary_text'])['ok'] and raw['external_provider_api_called'] is False
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=1, pushed=False, structured_json_present=True, style_checks=style_check(row['summary_text']),
        external_provider_api_called=False, trade_signal_count=signals)))


if __name__ == '__main__':
    main()
