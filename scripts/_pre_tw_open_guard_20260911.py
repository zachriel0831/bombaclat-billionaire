"""Local-only memo; dry-run by default, --apply stores the missing row."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260909 import (
    MarketAnalysisRecord, MySqlEventStore, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-11'
IDS = [895270, 895273, 895290, 892889]
SUMMARY = '''市場眼前交易的是能源與資金成本的壓力，能否蓋過電子供應鏈的需求韌性。我的台股盤前判斷偏審慎，半導體與設備仍有需求支點，但今天更可能先面對估值承壓；最大不確定性是油價壓力持續多久，以及企業能否把增加的成本轉嫁出去。需求成長與股價承接，今天需要分開確認。

半導體先接受壓力測試

最新美股行情顯示，費城半導體指數下跌 2.66%。這是台灣電子權值與供應鏈較直接的情緒參照，卻不能單憑跌幅判定訂單已轉弱，也無法確認外資今天會如何調整台股部位。它較明確的意義是：市場對半導體獲利成長的定價正在承受賣壓，先進製程、封裝與設備即使維持成長，也需要更扎實的毛利與現金流來支撐估值。

今晨西德州原油期貨報價為每桶 103.77 美元。這是盤前期貨報價，並非結算價；對台灣而言，能源與運輸支出若持續偏高，航空及高耗能製造較直接受壓，電子製造也可能透過物流與材料成本受到影響。石化則要看產品報價能否跟上原料，不能把油價上漲直接等同於獲利改善。

美國財政部最新日資料顯示，十年期公債殖利率為 4.95%。這個水準意味著遠期獲利仍面對資金成本約束，但單筆日資料不足以拆解通膨預期、政策預期與期限溢價。我的推論是，若能源壓力拖慢通膨降溫，市場對寬鬆的期待就可能受到挑戰，台灣高估值電子將同時接受成本與評價的檢驗；金融業則須把利差機會與債券評價風險一起看。

出口提供緩衝，還要確認利潤留得下來

經濟日報引述台灣機械公會，8 月機械出口年增 19%，受惠半導體與AI伺服器供應鏈需求。這筆已發生的出口數據支持設備需求韌性，卻不能保證之後每個月份延續相同增速，更不能把全年創高展望當成已實現成果。對台灣設備、電源與散熱等供應鏈，接下來值得確認的是訂單能否變成獲利，而非僅用營收成長抵銷所有成本疑慮。

半導體下跌已顯示風險進入價格，但不能據此認定能源衝擊已充分反映，也不能把跌幅全部歸因於油價。若油價回落、長端利率壓力緩和，且台灣電子承接與出口需求維持，這份偏審慎的判斷就應轉得更正面；若成本壓力持續，又看到訂單或毛利轉弱，市場可能從調整估值進一步轉向下修獲利。今天的重點是確認壓力是否擴散到企業基本面。上述期貨、指數、公債日資料與月出口的時間口徑不同，適合用來辨認壓力與緩衝，不能當作同一時刻的因果證明。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DAY and 'pre_tw_open' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    c.execute("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,))
    assert c.fetchone() is None, 'Review existing row; preserve delivery state.'
    c.execute('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)', tuple(IDS))
    events = [dict(zip(['id','event_id','source','title','summary','published_at'], row)) for row in c.fetchall()]
    assert len(events) == 4
    assert all('2026-09-10' <= str(e['published_at'])[:10] <= DAY for e in events)
    by_id = {e['id']: e for e in events}
    for event_id, token in zip(IDS, ['change_percent=-2.66%', 'value=103.77;', 'value=4.95;', '年增19%']):
        assert token in by_id[event_id]['summary'], (event_id, token)
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium', sentiment='cautious',
        headline='成本與估值壓力考驗設備需求韌性', thesis='台股偏審慎，出口需求仍有支點，能源與利率限制估值。',
        evidence=[dict(event_id=i) for i in IDS],
        tw_sector_transmission=['半導體與設備估值承壓','航空與高耗能製造成本壓力','金融利差與債券評價拉鋸'],
        invalidation=['油價與利率回落，電子承接及出口需求維持','成本續升且訂單或毛利轉弱'],
        evidence_limitations=['期貨、指數、公債日資料與月出口時間口徑不同'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style))
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation', display_title=DAY,
        calendar=calendar.to_dict(), evidence_event_ids=IDS, claim_verifier=verifier,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False)
    print(json.dumps(dict(dry_run=True, claim_verifier=verifier, style_checks=style, characters=len(SUMMARY))))
    if '--apply' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='pre_tw_open',
        scheduled_time_local='07:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=4, market_rows_used=0, push_enabled=True, pushed=False,
        raw_json=json.dumps(raw,ensure_ascii=False), structured_json=json.dumps(structured,ensure_ascii=False)))
    c.execute('SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s',(row_id,))
    row = c.fetchone()
    c.execute('SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s',(row_id,))
    signals = c.fetchone()[0]
    assert row[0] == SUMMARY and json.loads(row[1]) == raw and json.loads(row[2]) == structured
    assert row[3] == 1 and row[4] == 0 and signals == 0 and style_check(row[0])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=row[3], pushed=row[4], structured_json_present=True, style_checks=style_check(row[0]),
        external_provider_api_called=False, trade_signal_count=signals)))


if __name__ == '__main__':
    main()
