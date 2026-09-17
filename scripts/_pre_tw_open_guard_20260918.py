"""Store today's local-evidence pre-open memo; dry-run by default."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _us_close_guard_20260909 import (
    MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-18'
IDS = [954878, 954879, 954884, 954882]
SUMMARY = '''昨夜市場交易的是科技與半導體的風險偏好回升，台股盤前偏向電子權值有撐；但這能否擴散到更廣的類股，仍比單晚漲幅更重要。最大的變數是能源成本與資金成本若再上行，科技股評價能否承受。

海外價格先給電子業一個支點

前一個美股交易日，那斯達克 100 指數上漲 1.73%，費城半導體指數上漲 3.14%，台積電美國存託憑證上漲 3.00%。科技與半導體同步走強，顯示市場願意重新承接成長題材，對台灣先進製程、封裝及伺服器供應鏈的盤前情緒有利。不過，美股價格反映的是海外交易時段的預期，還不能推論台灣企業的新訂單或今日台股的實際漲幅。若盤後只有少數權值股支撐指數，仍屬集中行情，不能解讀成整體需求改善。

油價回落，成本疑慮還在

今晨可見的西德州原油期貨報每桶 101.2 美元，較前值下跌 0.70%。這是期貨當時的報價，不是當日結算價；短線回落有助緩和運輸與高耗能產業的成本擔憂，卻不足以確認能源壓力已解除。對電子業，油價主要透過運費、材料與通膨預期影響獲利及評價，傳導速度不同於半導體股價。台灣航空、運輸與石化業還要分別看燃料成本、產品價格及轉嫁能力，不能只憑油價方向判斷受益。

接下來看承接能否變寬

目前較明確的是海外資金願意替大型科技與半導體重新定價，尚未證明台股各產業同步改善。若台灣電子權值之外的供應鏈也跟上，企業展望維持，且油價持續緩和，偏正面的盤前判斷才更有基礎；若半導體熱度退去、其他類股缺乏承接，或能源與利率壓力再起，就應收回對擴散行情的預期。以上只使用盤前可見的本機資料，開盤後仍須以實際價格與成交結構重新檢驗。'''


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
    events = rows(cursor, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)', IDS)
    assert {e['id'] for e in events} == set(IDS)
    tokens = {954878: 'change_percent=+1.73%', 954879: 'change_percent=+3.14%',
              954884: 'change_percent=+3.00%', 954882: 'value=101.2;'}
    for event in events:
        assert tokens[event['id']] in event['summary']
    assert 'change_percent=-0.70%' in next(e['summary'] for e in events if e['id'] == 954882)
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        headline='科技與半導體回溫，留意成本和擴散程度',
        thesis='台股盤前偏正面，但科技承接能否擴散仍待確認。',
        evidence=[dict(event_id=i) for i in IDS],
        tw_sector_transmission=['先進製程、封裝及伺服器供應鏈評價', '運輸與高耗能產業成本', '電子業材料與資金成本'],
        invalidation=['電子權值之外的供應鏈擴散且油價緩和', '半導體承接退去或能源與利率壓力再起'])
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
