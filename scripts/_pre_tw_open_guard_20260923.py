"""Local evidence-only pre-open memo; dry-run unless --apply is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _pre_tw_open_guard_20260918 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-23'
TOKENS = {992859: 'change_percent=+2.06%', 992876: 'change_percent=-0.02%',
          992879: 'value=4.96;', 992862: 'value=89.68;'}
SUMMARY = '''市場正在交易半導體的相對強勢與能源成本緩和，還沒有形成全面風險偏好回升。台股盤前偏向電子權值及相關供應鏈有支撐，但整體判斷仍宜中性看待；最大的未知，是海外科技行情能否穿過偏高的資金成本，轉成台灣更廣的承接與企業獲利。

半導體先行，大盤還在原地

前一個美股交易日，費城半導體指數上漲 2.06%，追蹤標普五百的基金則下跌 0.02%，接近持平。這組分歧支持資金選擇性承接半導體的解讀，卻不足以證明整體景氣或資金環境同步改善。對台灣先進製程、封裝、伺服器及設備供應鏈，海外評價可先提供情緒支撐，後續仍須由出貨、產能利用率與毛利率驗證。若台股開盤後只有少數權值股反映利多，其他電子環節沒有跟上，這份支撐就仍然集中。

資金成本是另一道門檻。最新美國十年期公債殖利率為 4.96%；這是一個利率水準，不能直接寫成當晚殖利率上升，也無法單靠它判斷央行下一步。它提醒的是，即使成長預期改善，較遠期獲利仍須接受資金成本的折現。對台灣電子業，訂單成長與市場願意給的評價應分開檢驗；金融業則還要區分債券評價、利息收入與匯率影響，不能把單一利率數字當作整個產業的利多或利空。

油價讓成本端稍有喘息

今晨西德州原油期貨報每桶 89.68 美元，較前值回落。這是盤前當時的期貨報價，並非今日結算價。若回落能持續，運輸及高耗能製造的成本疑慮有機會減輕，電子業也可能經由物流、材料與通膨預期間接受益。不過，實際燃料合約、匯率和成品油供需會影響傳導速度；石化業更須比較產品售價與原料成本，原油下跌不保證利差擴大。能源價格對供應與地緣消息敏感，單次回落還不能當成成本問題已經解決。

目前價格已呈現半導體優於大盤，還能再定價的，是企業能否交出足以支持評價的獲利，以及能源緩和能否真正降低成本。若台灣電子供應鏈的承接擴散、企業展望保持韌性，且利率與油價不再增加壓力，中性的判斷才有理由轉向更正面；若半導體優勢消退、殖利率走高或油價反彈，就需下修電子相對有撐的期待。海外交易結果、日頻利率與今晨期貨屬不同時間點，不能由這些價格直接推論今日台灣資金已全面回流。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (992859,992876,992879,992862)')
    assert {e['id'] for e in events} == set(TOKENS)
    for event in events:
        assert TOKENS[event['id']] in event['summary']
        assert str(event['published_at']).startswith('2026-09-22')
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='半導體相對有撐但大盤近乎持平，台灣電子須通過資金成本與獲利檢驗。',
        evidence=[dict(event_id=i) for i in TOKENS],
        tw_sector_transmission=['半導體及電子供應鏈評價', '金融債券評價與利息收入', '運輸及製造能源成本'],
        invalidation=['半導體優勢消退', '殖利率走高或油價回升'])
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
