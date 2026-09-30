"""Local evidence-only October 1 pre-open memo; dry-run by default."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-10-01'
TOKENS = {1034137: 'change_percent=+0.23%', 1034138: 'change=-0.537;',
          1034158: 'value=5.29;', 1034141: 'value=90.16;'}
SUMMARY = """盤前較值得重視的，是大型科技股仍有支撐，半導體卻沒有同步擴張漲勢，資金成本也尚未鬆綁。這組價格訊號比較像選擇性的成長定價，因此台股基調維持中性偏審慎。最大的未知，是電子需求能否轉成足以支撐估值的獲利，以及台灣開盤後的承接能否擴散。

科技指數微升，產業接棒仍待確認

最新美國週三行情中，那斯達克 100 指數上漲 0.23%，費城半導體指數則微幅下跌、近乎持平。兩者分歧意味著，科技指數的上行尚不足以證明半導體需求全面加速。價格提供的是投資人願意支付多少估值的線索，訂單、交付與毛利率才決定這份期待能否兌現。傳到台灣，先進製程、封裝、設備及伺服器供應鏈仍須各自檢驗營收成長與現金流，不能把大型科技股的小幅上漲直接換算成整條產業鏈的獲利改善。

另一個約束來自利率。美國週三十年期公債殖利率日頻資料為 5.29%，這是利率水準，不是單晚跳升幅度，也不是央行政策利率。較高的折現要求，會提高遠期成長轉成當下估值的門檻。對需要持續擴產的電子業，需求能見度與融資條件必須一起看；對金融業，新增投資收益、既有債券評價和避險成本的方向可能不同，不能概括為整個產業受惠。

今晨西德州原油期貨報每桶 90.16 美元。這個報價提供能源成本背景，卻不能單憑水準判定地緣衝突升高或緩和，也不等同企業實際採購成本。若後續油價持續走高，運輸、物流及耗能製造的成本轉嫁能力就更重要；石化業則須同時看產品售價與原料成本，原油方向本身不足以決定利潤。

目前能確認的是科技指數小漲、半導體表現平淡，尚不能確認市場已充分消化高利率或未來獲利變化。若台灣電子表現擴散、企業展望與現金流保持韌性，且殖利率壓力緩和，審慎基調就應調整；若科技支撐消退、半導體轉弱，又伴隨獲利下修或能源成本上行，估值與利潤的雙重壓力便可能重新主導。海外股價、日頻利率及盤前期貨各有觀察時點，這份傳導判斷仍需台灣開盤後的成交廣度與資金流向驗證。"""


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1034137,1034138,1034158,1034141)')
    assert {e['id'] for e in events} == set(TOKENS)
    for event in events:
        assert TOKENS[event['id']] in event['summary']
        assert event['published_at'].startswith('2026-09-30')
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='科技指數微升但半導體未接棒，台股中性偏審慎；獲利及承接廣度仍待驗證。',
        evidence_event_ids=list(TOKENS),
        tw_sector_transmission=['電子供應鏈需求與估值', '金融收益與債券評價', '運輸製造能源成本'],
        invalidation=['電子表現擴散且展望穩健、利率壓力緩和', '回升消退且獲利下修、利率或油價上行'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
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
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=1, pushed=False, structured_json_present=True, style_checks=style_check(row['summary_text']),
        external_provider_api_called=False, trade_signal_count=signals)))


if __name__ == '__main__':
    main()
