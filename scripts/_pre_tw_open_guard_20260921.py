"""Local evidence-only pre-open memo; dry-run unless --apply is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _pre_tw_open_guard_20260918 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-21'
TOKENS = {963317: 'change_percent=+0.63%', 963319: 'change_percent=-0.47%',
          963316: 'change_percent=-0.65%', 977062: 'value=95.87;'}
SUMMARY = '''市場目前較像是在替大型科技的成長韌性定價，同時保留對資金成本的戒心。台股盤前判斷偏向電子權值有支撐、整體行情仍需確認擴散；最大的變數，是科技股的相對強勢能否抵銷長天期利率壓力，而非僅靠少數大型股撐住指數。

科技有撐，承接仍不平均

上週五，追蹤那斯達克大型股的基金上漲 0.63%，小型股基金卻下跌 0.47%。這組分歧支持資金偏向大型成長股的解讀，卻不足以證明整體企業景氣同步轉強。對台灣而言，海外科技評價可先傳到先進製程、封裝與伺服器供應鏈的情緒；接下來仍要由訂單能見度、獲利與台股開盤後的成交結構接棒。若權值股有表現，中小型供應鏈卻缺乏承接，就不能把指數上漲直接當成需求全面改善。

同一交易日，長天期美國公債基金下跌 0.65%。長債價格走弱通常對應殖利率上行壓力，提醒我們：科技股走強與資金成本下降並未必然同行。基金價格本身不能精確拆出通膨、期限溢酬或政策預期各占多少，但對需要較長時間兌現獲利的企業，折現率壓力仍會影響評價。台灣電子供應鏈即使成長敘事完整，也需要現金流和毛利率支持；金融業則須分別看債券評價與利息收入，不能把利率變化視為一致利多。

今晨油價提供的只是局部緩衝

今晨西德州原油期貨報每桶 95.87 美元，較前值小幅回落。這是當時報價，並非今日結算價；對航空、運輸與高耗能製造，若回落延續，有助減輕成本疑慮。石化業仍須比較原料和產品價格，電子業也要看運費、材料與匯率，油價下降不會立即等比例轉成獲利。

目前價格已呈現大型科技相對占優，尚未確認的是台灣能否出現更廣的承接，以及資金成本會不會再拖累評價。若長債止穩、油價維持緩和，台股供應鏈與非電子類股也同步改善，對行情擴散的信心才有理由提高；若科技優勢消退、長債續弱或油價反彈，盤前偏正面的電子判斷便需下修。美股部分仍是上週五交易結果，與今晨期貨報價屬不同時段；開盤後應重新檢驗，不能把它們當成同步確認。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (963317,963319,963316,977062)')
    assert len(events) == 4
    for event in events:
        assert TOKENS[event['id']] in event['summary']
        assert ('2026-09-20T23:10' if event['id'] == 977062 else '2026-09-18T20:00') in str(event['published_at'])
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        headline='大型科技有撐，資金成本與行情擴散仍待確認',
        evidence=[dict(event_id=i) for i in TOKENS],
        tw_sector_transmission=['先進製程、封裝及伺服器評價', '金融債券評價與利息收入', '運輸與製造能源成本'],
        invalidation=['科技優勢消退', '長債續弱或油價反彈'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style))
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation',
        display_title=DAY, calendar=cal.to_dict(), evidence_event_ids=list(TOKENS),
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat())
    print(json.dumps(dict(dry_run='--apply' not in sys.argv, characters=len(SUMMARY), verifier=verifier, style=style)))
    if '--apply' in sys.argv:
        print(store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='pre_tw_open',
            scheduled_time_local='07:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
            summary_text=SUMMARY, events_used=4, market_rows_used=0, push_enabled=True, pushed=False,
            raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False))))


if __name__ == '__main__':
    main()
