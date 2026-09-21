"""Local evidence-only pre-open memo; dry-run unless --apply is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _pre_tw_open_guard_20260918 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-22'
TOKENS = {983912: 'change_percent=+2.83%', 983913: 'change_percent=+4.29%',
          983928: 'change_percent=+0.68%', 983916: 'value=92.06;'}
SUMMARY = '''市場正在交易科技成長的風險偏好回升，長債走強與今晨油價小幅回落，也讓評價與成本壓力有了喘息空間。台股盤前偏向電子權值及半導體供應鏈有支撐；最大的未知，是海外價格改善能否轉成台灣更廣的承接與企業獲利，而非只停留在評價反彈。

電子行情先得到海外支撐

前一個美股交易日，那斯達克 100 指數上漲 2.83%，費城半導體指數上漲 4.29%。半導體漲幅更大，支持資金對科技供應鏈重新提高評價的解讀，卻不能單憑股價推論新訂單已經增加。對台灣先進製程、封裝、伺服器與設備業而言，海外評價可先改善盤前情緒，接著仍要靠出貨、毛利率和現金流接棒。若開盤後只有權值股反映利多，其他供應鏈未能跟上，這份支撐就仍是局部的。

同一交易日，長天期美國公債基金上漲 0.68%。長債價格回升通常意味長端殖利率壓力緩和，對獲利較晚兌現的成長企業有利；但基金價格無法單獨拆出政策預期、期限溢酬與資金避險的影響，更不能當成央行已轉向寬鬆。台灣電子業可能先受惠於折現壓力減輕，金融業則要分別看債券評價、利息收入及匯率，不能把長債走強一概當成所有金融股的利多。

能源緩衝仍須時間確認

今晨西德州原油期貨報每桶 92.06 美元，較前值小幅回落。這是盤前當時的期貨報價，並非今日結算價；若回落延續，航空、運輸及高耗能製造的成本疑慮可望減輕，電子業也可能經由材料與物流費用間接受益。石化業仍須比較產品售價和原料成本的變化，油價下降不保證利差同步擴大。能源價格也容易受供應與地緣局勢反覆影響，單次報價尚不足以確認通膨壓力持續消退。

目前已反映在價格上的，是科技與半導體的承接回升；還能再定價的，是成本緩和能否持續，以及企業能否把需求轉成獲利。若長債維持穩定、能源壓力不再上升，台灣電子以外類股也出現承接，偏正面的判斷才有更廣基礎；若半導體優勢快速消退、長債反向走弱或油價回升，就需要下修這份盤前期待。美股交易結果與今晨期貨屬不同時段，台股開盤後的成交結構仍是下一個驗證，不能由海外單晚上漲直接推論台灣資金已全面回流。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (983912,983913,983928,983916)')
    assert {e['id'] for e in events} == set(TOKENS)
    for event in events:
        assert TOKENS[event['id']] in event['summary']
        assert str(event['published_at']).startswith('2026-09-21T')
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='科技承接與成本壓力緩和支持台灣電子，仍需行情擴散與獲利確認。',
        evidence=[dict(event_id=i) for i in TOKENS],
        tw_sector_transmission=['半導體及電子供應鏈評價', '金融債券評價與利息收入', '運輸及製造能源成本'],
        invalidation=['半導體優勢消退', '長債走弱或油價回升'])
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
