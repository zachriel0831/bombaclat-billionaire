"""Local evidence-only pre-open memo; dry-run unless --apply is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-29'
TOKENS = {1033951: 'change_percent=-1.61%', 1033956: 'change_percent=+0.50%',
          1033971: 'value=5.24;', 1033954: 'value=93.28;'}
SUMMARY = '''台股休市後重新開盤，眼前要消化的是海外半導體分化，以及利率與能源成本對獲利的要求。隔夜半導體指數走弱，台積電在美國的股價卻相對有撐，盤前宜偏審慎，但還不足以判定電子需求全面降溫。最大的未知，是權值企業的韌性能否擴散到供應鏈，還是只在少數大型企業身上成立。

指數承壓，權值支撐的廣度仍待確認

最新隔夜行情顯示，費城半導體指數下跌 1.61%，台積電美國存託憑證則上漲 0.50%。兩者方向不同，說明半導體不能只用單一漲跌結論概括：權值企業可能支撐台灣大盤的情緒，其他電子族群仍可能面臨評價調整。這組價格只能證明表現分化，無法單獨證明訂單增加，也不能把美國存託憑證的漲幅直接套成台灣現股的開盤幅度。先進製程、封裝及伺服器供應鏈能否承接這份相對韌性，仍要由企業展望、交付與毛利率驗證。

利率使這個分化更有意義。最新美國十年期公債殖利率日頻資料為 5.24%，代表企業與投資人評估遠期現金流時，仍面對不能忽略的資金成本。這是利率水準，並非今晨突然上升的幅度，也不是央行政策利率。對台灣電子業，需求成長能否轉成現金流，比單靠題材更關鍵；對金融業，債券評價與再投資收益可能方向不同，不能把較高殖利率直接視為整個族群的利多或利空。

成本端也還沒有提供明顯緩衝。今晨西德州原油期貨報每桶 93.28 美元，較前值上升。這是盤前報價，不是今日結算價，亦不足以確認漲勢將持續；但若能源成本維持壓力，台灣運輸、物流及耗能製造的利潤便取決於轉嫁能力。電子業也可能透過運費與通膨預期間接受影響，石化則須把原料成本與產品售價拆開看，不能只憑油價上漲推定獲利改善。

目前價格已呈現的是半導體內部分化，尚未確認的是台灣開盤後的承接廣度，以及企業獲利能否消化利率與能源負擔。若半導體轉穩、台灣電子表現擴散，並有穩健訂單與利潤支持，同時殖利率或油價壓力緩和，偏審慎的判斷便應調回中性。反過來，若權值支撐消退、企業下修展望，且資金與能源成本同步增加，壓力就可能由估值延伸至獲利。美股行情、日頻利率與今晨期貨的觀察時間不同；它們提供開盤前的條件判斷，還不能證明台灣資金已流入或流出。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1033951,1033956,1033971,1033954)')
    assert {e['id'] for e in events} == set(TOKENS)
    for event in events:
        assert TOKENS[event['id']] in event['summary']
        assert event['published_at'].startswith('2026-09-28')
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='海外半導體分化，台股偏審慎；權值韌性能否擴散及成本能否消化仍待確認。',
        evidence_event_ids=list(TOKENS),
        tw_sector_transmission=['電子權值與供應鏈承接廣度', '金融債券評價及再投資收益', '運輸及製造能源成本'],
        invalidation=['電子表現擴散且獲利穩健、利率或油價壓力緩和', '權值支撐消退且展望下修、資金及能源成本增加'])
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
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=True, pushed=False,
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
