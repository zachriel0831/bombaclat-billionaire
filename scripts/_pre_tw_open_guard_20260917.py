"""Store the 2026-09-17 local-evidence pre-open memo; dry-run by default."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _us_close_guard_20260909 import (
    MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-17'
IDS = [946440, 946445, 946457, 946443]
SUMMARY = '''盤前市場交易的是「半導體相對有撐，但整體風險偏好沒有同步回來」。我的台股判斷是中性偏審慎：先進製程與相關供應鏈可能得到海外半導體行情支撐，指數卻未必全面受惠。最大不確定性，是這份支撐能否擴散到其他電子環節，還是被資金成本與能源風險抵消。

半導體的亮點，還不是全面轉強

前一個美股交易日，費城半導體指數上漲 0.63%，台積電美國存託憑證上漲 1.23%；同時，追蹤標普五百的基金下跌 0.44%。這三個價格放在一起看，較像資金選擇性承接半導體，而非整個股市風險偏好上升。台灣先進製程、封裝與伺服器供應鏈因此有評價上的支撐，但股價反應仍須與實際接單、產能利用率及毛利率分開檢驗。單晚漲跌不能證明新訂單已經到手，也不能推斷台股開盤後資金會照單全收。

成本端暫緩，壓力尚未解除

今晨盤前的西德州原油期貨報每桶 102.01 美元，較前值下跌 0.41%。這是盤中期貨報價，不是當日結算價；小幅回落可以減少立即追價的壓力，卻不足以確認能源成本趨勢反轉。對台灣航空、運輸與高耗能製造，關鍵仍是燃料及原料成本能否轉嫁；石化還要比較產品售價與原料成本，不能只看油價方向。電子業則可能經由運費、材料與通膨預期，間接受到資金成本影響。這條傳導目前是風險情境，不能直接寫成利率已經上升。

接下來看分歧是否收斂

目前市場價格已呈現半導體強於大盤的分歧，尚無證據顯示整體獲利預期因此改善。若後續大型科技與台灣電子權值股跟上，企業展望維持，且油價壓力持續緩和，中性偏審慎的判斷就應修正；若半導體承接退去、企業毛利承壓，或能源價格再度上行，估值與成本壓力可能同時放大。以上只反映台股開盤前可見的海外價格，不能當成今日台股走勢的結論。'''


def rows(cursor, sql, params=()):
    cursor.execute(sql, params)
    return [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    cursor = store._cursor()
    assert not rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row needs review'
    events = rows(cursor, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (946440,946445,946457,946443)')
    assert {e['id'] for e in events} == set(IDS)
    tokens = {946440: 'change_percent=+0.63%', 946445: 'change_percent=+1.23%',
              946457: 'change_percent=-0.44%', 946443: 'value=102.01;'}
    for event in events:
        assert tokens[event['id']] in event['summary']
    assert 'change_percent=-0.41%' in next(e['summary'] for e in events if e['id'] == 946443)
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        headline='半導體有撐，整體風險偏好仍待確認',
        thesis='台股中性偏審慎，海外半導體韌性能否擴散仍待確認。',
        evidence=[dict(event_id=i) for i in IDS],
        tw_sector_transmission=['先進製程與相關供應鏈評價', '運輸與高耗能製造成本', '電子業材料與資金成本'],
        invalidation=['電子權值承接擴散、企業展望維持且油價壓力緩和',
                      '半導體承接退去、毛利承壓或能源價格再上行'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style), ensure_ascii=False)
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation',
        display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=IDS,
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat())
    print(json.dumps(dict(dry_run='--apply' not in sys.argv, claim_verifier=verifier,
                          style_checks=style, characters=len(SUMMARY)), ensure_ascii=False))
    if '--apply' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='pre_tw_open',
        scheduled_time_local='07:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=True, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    print(json.dumps(dict(analysis_id=row_id)))


if __name__ == '__main__':
    main()
